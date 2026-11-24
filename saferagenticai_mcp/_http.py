"""Streamable HTTP transport — additive. stdio remains the default transport.

Enabled by setting ``MCP_TRANSPORT=http``. Binds the loopback interface by
default: a reverse proxy (e.g. Caddy) is expected to terminate TLS and be the
only public-facing component. The MCP tools are transport-agnostic and are not
touched here — this module only provides an alternate run harness for hosted
deployments.

Env:
  MCP_HTTP_HOST  (default 127.0.0.1)  — bind address; keep loopback behind a proxy
  MCP_HTTP_PORT  (default 8080)       — port the ASGI server listens on
  MCP_DOMAIN_VERIFICATION_TOKEN      — optional public OpenAI domain challenge

Extra deps (see the ``http`` optional-dependencies group): ``uvicorn``, ``starlette``.
"""

from __future__ import annotations

import contextlib
import os
import re

from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route
from starlette.types import Receive, Scope, Send


def build_http_app(server: Server, *, domain_verification_token: str | None = None) -> Starlette:
    """Wrap a low-level MCP ``Server`` in a Starlette ASGI app over Streamable HTTP.

    Stateless mode (a fresh transport per request, no persisted sessions) avoids
    the idle-session / held-event-stream exhaustion class of DoS. ``debug=False``
    ensures Starlette never renders a stack trace to a client (CWE-209).
    """
    if domain_verification_token is not None and (
        not isinstance(domain_verification_token, str)
        or re.fullmatch(r"[A-Za-z0-9_-]{32,256}", domain_verification_token) is None
    ):
        raise ValueError("Domain verification requires one 32..256-character public base64url token")

    manager = StreamableHTTPSessionManager(
        app=server,
        event_store=None,
        json_response=True,
        stateless=True,
    )

    async def handle_mcp(scope: Scope, receive: Receive, send: Send) -> None:
        # Stateless mode has no session, so GET (the server->client SSE stream)
        # and DELETE (teardown) are meaningless — and a GET holds an idle
        # event-stream open indefinitely (a connection-exhaustion DoS). Accept
        # only POST; reject the rest with a clean JSON-RPC 405. Defense in depth:
        # the front proxy should also restrict methods, but the app must be safe
        # when run alone.
        if scope.get("type") == "http" and scope.get("method") != "POST":
            response = JSONResponse(
                {"jsonrpc": "2.0",
                 "error": {"code": -32600, "message": "Only POST is supported"},
                 "id": None},
                status_code=405,
                headers={"Allow": "POST"},
            )
            await response(scope, receive, send)
            return
        await manager.handle_request(scope, receive, send)

    async def health(_request):
        return JSONResponse({"status": "ok"})

    async def domain_challenge(_request):
        # This public ownership proof is fixed at startup. Never echo request
        # input or expose a file/configuration lookup through this route.
        return PlainTextResponse(domain_verification_token, headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        })

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette):
        # run() sets up the manager's task group; it must live for the app's
        # lifetime and may only be entered once per instance.
        async with manager.run():
            yield

    # Mount at /mcp. A bare `/mcp` request 307-redirects to `/mcp/`; this is the
    # reference MCP behaviour and SDK/httpx clients follow it transparently.
    routes = [Route("/health", health, methods=["GET"]), Mount("/mcp", app=handle_mcp)]
    if domain_verification_token is not None:
        routes.append(Route("/.well-known/openai-apps-challenge", domain_challenge, methods=["GET"]))
    return Starlette(
        debug=False,
        routes=routes,
        lifespan=lifespan,
    )


def run_http(server: Server) -> None:
    """Serve ``server`` over Streamable HTTP (blocking). Import uvicorn lazily so
    stdio-only installs never require it."""
    import uvicorn

    host = os.environ.get("MCP_HTTP_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_HTTP_PORT", "8080"))
    uvicorn.run(
        build_http_app(server, domain_verification_token=os.environ.get("MCP_DOMAIN_VERIFICATION_TOKEN")),
        host=host,
        port=port,
        log_level="info",
        log_config=None,
        access_log=False,
    )
