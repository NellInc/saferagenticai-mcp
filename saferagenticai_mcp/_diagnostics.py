"""Payload-free diagnostics for the dedicated executable, never on import.

The protocol owns stdio stdout. Diagnostic records contain only fixed event
categories and bounded metadata. Free-form Python output is replaced by a
suppression event; native writes to diagnostic descriptors are discarded.
The emitting handler holds a private duplicate of the original stderr sink.
"""
from __future__ import annotations

import datetime
import io
import json
import logging
import os
import sys
import threading

EVENTS = frozenset({
    "startup", "shutdown", "application_event", "protocol_event",
    "protocol_validation", "http_event", "runtime_warning",
    "runtime_exception", "unstructured_output_suppressed",
})
ERRORS = frozenset({
    "ValueError", "TypeError", "KeyError", "IndexError", "RuntimeError",
    "OSError", "PermissionError", "FileNotFoundError", "TimeoutError",
    "MemoryError", "RecursionError", "AssertionError", "SystemExit",
    "KeyboardInterrupt", "ExceptionGroup", "ValidationError",
})


class DiagnosticFormatter(logging.Formatter):
    def __init__(self, version: str):
        super().__init__()
        self.version = version

    def format(self, record: logging.LogRecord) -> str:
        # Deliberately never call getMessage(), formatException() or str(exc).
        event = record.__dict__.get("diagnostic_event")
        if not isinstance(event, str) or event not in EVENTS:
            if record.name == "py.warnings":
                event = "runtime_warning"
            elif record.name.startswith("mcp.shared."):
                event = "protocol_validation"
            elif record.name.startswith("mcp."):
                event = "protocol_event"
            elif record.name.startswith("uvicorn"):
                event = "http_event"
            else:
                event = "application_event"
        level = ("critical" if record.levelno >= 50 else "error" if record.levelno >= 40
                 else "warning" if record.levelno >= 30 else "info" if record.levelno >= 20
                 else "debug")
        error = "none"
        if record.exc_info and record.exc_info[0]:
            name = record.exc_info[0].__name__
            error = name if name in ERRORS else "other"
        return json.dumps({
            "timestamp": datetime.datetime.fromtimestamp(record.created, datetime.timezone.utc).isoformat(),
            "severity": level, "event": event, "server_version": self.version,
            "error_class": error,
        }, separators=(",", ":"))


class _DiagnosticStream:
    """File-like quarantine: never forward or buffer the supplied content."""
    encoding = "utf-8"
    errors = "replace"

    def __init__(self, handler: logging.Handler, fd: int):
        self.handler, self.fd = handler, fd
        self.buffer = self

    def write(self, value):
        if value:
            record = logging.LogRecord("saferagenticai.diagnostics", logging.WARNING,
                                       "", 0, "", (), None)
            record.diagnostic_event = "unstructured_output_suppressed"
            self.handler.handle(record)
        return len(value)

    def flush(self):
        self.handler.flush()

    def isatty(self):
        return False

    def fileno(self):
        return self.fd


def configure_diagnostics(*, version: str, http: bool) -> None:
    """Own the diagnostic sinks of this dedicated process before SDK startup.

    This is intentionally irreversible within the process. Call only from main,
    never from build_http_app or another embedding/library entry point.
    """
    sink = io.TextIOWrapper(os.fdopen(os.dup(2), "wb", buffering=0),
                            encoding="utf-8", errors="replace", write_through=True)
    handler = logging.StreamHandler(sink)
    handler.setFormatter(DiagnosticFormatter(version))
    # Python's own logging fallback must not dump record contents on failure.
    logging.raiseExceptions = False
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    # Includes already-imported SDK loggers with their own emitting handlers.
    for logger in list(logging.Logger.manager.loggerDict.values()):
        if isinstance(logger, logging.Logger):
            logger.handlers.clear()
            logger.propagate = True
            logger.disabled = False
            logger.setLevel(logging.NOTSET)
    logging.lastResort = handler
    logging.captureWarnings(True)

    with open(os.devnull, "wb") as quarantine:
        os.dup2(quarantine.fileno(), 2)
        if http:
            os.dup2(quarantine.fileno(), 1)
    sys.stderr = sys.__stderr__ = _DiagnosticStream(handler, 2)
    if http:
        sys.stdout = sys.__stdout__ = _DiagnosticStream(handler, 1)

    def exception(kind, value, traceback):
        root.error("", exc_info=(kind, value, traceback),
                   extra={"diagnostic_event": "runtime_exception"})

    sys.excepthook = exception
    threading.excepthook = lambda args: exception(args.exc_type, args.exc_value, args.exc_traceback)
    sys.unraisablehook = lambda args: exception(args.exc_type, args.exc_value, args.exc_traceback)
    root.info("", extra={"diagnostic_event": "startup"})
