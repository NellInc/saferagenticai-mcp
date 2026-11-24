"""Namespace-only expiry. Never accepts a namespace, path or age from input."""
import datetime
import json
from pathlib import Path
import re
import subprocess
import sys
import time

NAMESPACE = "saferagenticai-mcp"
VERSION = "0.4.3"


def journal_directories():
    machine = Path("/etc/machine-id").read_text().strip()
    if not re.fullmatch(r"[0-9a-f]{32}", machine):
        raise ValueError()
    paths = [Path(base) / (machine + "." + NAMESPACE)
             for base in ("/var/log/journal", "/run/log/journal")]
    if any(path.is_symlink() for path in paths):
        raise ValueError()
    existing = [str(path) for path in paths if path.is_dir()]
    if not existing:
        raise RuntimeError()
    return existing


def run(check_only=False):
    try:
        directories = journal_directories()
        if not check_only:
            for action in ("--rotate", "--sync"):
                subprocess.run([
                    "/usr/bin/journalctl", "--namespace=" + NAMESPACE, action,
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
            for directory in directories:
                subprocess.run([
                    "/usr/bin/journalctl", "--directory=" + directory,
                    "--vacuum-time=30d", "--vacuum-size=250M", "--quiet",
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        # Only timestamps are requested. A record older than target + 24 hours
        # is an operational failure, not an excuse to delete any shared store.
        for directory in directories:
            result = subprocess.run([
                "/usr/bin/journalctl", "--directory=" + directory, "--no-pager",
                "--output=json", "--output-fields=__REALTIME_TIMESTAMP", "--lines=1", "--reverse",
                "--until=@" + str(int(time.time() - 31 * 86400)),
            ], check=True, capture_output=True, text=True, timeout=120)
            expired = any(json.loads(line).get("__REALTIME_TIMESTAMP") for line in result.stdout.splitlines())
            if expired:
                raise RuntimeError()
    except (subprocess.SubprocessError, OSError, ValueError, RuntimeError):
        return 1
    return 0


def main():
    allowed = sys.argv[1:] in ([], ["--check-only"])
    status = run(check_only=bool(sys.argv[1:])) if allowed else 1
    print(json.dumps({
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "severity": "error" if status else "info",
        "event": "retention_check_failed" if status else "retention_check_passed",
        "server_version": VERSION, "error_class": "other" if status else "none",
    }, separators=(",", ":")))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
