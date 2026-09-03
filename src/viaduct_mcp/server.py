"""Server assembly: one MCPServer, both transports."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from . import __version__
from .config import Settings, load_settings
from .logging_setup import (
    access_log_middleware,
    configure_logging,
    logger,
)
from .rate_limit import SlidingWindowLimiter, make_rate_limit_middleware
from .tools import register_all

__all__ = ["build_server", "configure_logging", "logger"]

INSTRUCTIONS = """\
Viaduct holds C4 architecture models: systems, containers, components and code,
plus their documentation, PlantUML sequence diagrams and Magic flows.

Contracts come in two shapes. A request/response call is kind='endpoint' with
method, request and response. A broker topic or queue is kind='channel' under
its broker container, with protocol, schemaFormat and separate key, value and
headers schemas — never model a topic as an endpoint.

Read before you write. c4_project_context gives the whole picture in one call;
c4_search finds a specific element. Creating an element that already exists is
idempotent by name within its parent, but a duplicate flow is not — list flows
first and update the one that is there.

Write tools need edit access on the project and will say so if it is missing.
"""


def build_server(settings: Settings | None = None) -> MCPServer:
    resolved = settings or load_settings()

    server = MCPServer(
        name="viaduct",
        title="Viaduct",
        version=__version__,
        instructions=INSTRUCTIONS,
        website_url="https://c4.quietgridlabs.com",
    )
    register_all(server, resolved)
    # Outermost-first among ours: access log wraps the rate limiter so refusals
    # still show up as ``tool error`` lines.
    server.middleware.append(access_log_middleware)
    if resolved.rate_limit_per_minute > 0:
        limiter = SlidingWindowLimiter(resolved.rate_limit_per_minute)
        server.middleware.append(make_rate_limit_middleware(limiter))
        logger.info(
            "rate limit enabled limit=%s/min per caller",
            resolved.rate_limit_per_minute,
        )

    if resolved.is_http:

        @server.custom_route("/healthz", methods=["GET"])
        async def healthz(_request):  # pragma: no cover - trivial
            from starlette.responses import JSONResponse

            return JSONResponse({"ok": True, "version": __version__})

    return server
