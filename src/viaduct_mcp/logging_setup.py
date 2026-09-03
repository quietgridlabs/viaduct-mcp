"""Process logging: stderr only, Docker-friendly, no secrets.

Stdout is the MCP wire protocol on stdio, so everything observable goes to
stderr. Docker's json-file driver picks that up; ``docker compose logs -f``
then shows tool calls and upstream failures without extra plumbing.
"""

from __future__ import annotations

import hashlib
import logging
import sys
import time
from collections.abc import Mapping
from typing import Any

from mcp.server.context import CallNext, HandlerResult, ServerRequestContext

from .session import token_from_headers

logger = logging.getLogger("viaduct_mcp")

# Long enough to tell callers apart in logs, short enough not to invert.
_TOKEN_FP_LEN = 12

# Methods that are noise at INFO (handshake / discovery).
_QUIET_METHODS = frozenset(
    {
        "initialize",
        "notifications/initialized",
        "notifications/cancelled",
        "ping",
        "tools/list",
        "resources/list",
        "resources/templates/list",
        "prompts/list",
    }
)


def token_fingerprint(token: str) -> str:
    """Stable non-reversible id for a bearer token. Empty → ``-``."""
    if not token:
        return "-"
    return hashlib.sha256(token.encode()).hexdigest()[:_TOKEN_FP_LEN]


def configure_logging(level: str) -> None:
    """Install a single stderr handler. Safe to call once at process start."""
    root = logging.getLogger()
    resolved = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )

    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(resolved)

    # Ours at the requested level; libraries quieter unless DEBUG.
    logging.getLogger("viaduct_mcp").setLevel(resolved)
    for name in ("httpx", "httpcore", "mcp", "uvicorn.access"):
        logging.getLogger(name).setLevel(logging.WARNING if resolved > logging.DEBUG else resolved)
    # Keep uvicorn's own startup line visible.
    logging.getLogger("uvicorn.error").setLevel(resolved)


def _headers_from_ctx(ctx: ServerRequestContext[Any, Any]) -> Mapping[str, str] | None:
    request = ctx.request
    if request is None:
        return None
    headers = getattr(request, "headers", None)
    return headers if headers is not None else None


def caller_fingerprint(ctx: ServerRequestContext[Any, Any]) -> str:
    """Fingerprint of the bearer on this request, or ``-``."""
    return token_fingerprint(token_from_headers(_headers_from_ctx(ctx)))


def _tool_bits(params: Mapping[str, Any] | None) -> tuple[str, str]:
    """(tool_name, projectId-or-dash) from a tools/call params blob."""
    if not params:
        return "?", "-"
    name = str(params.get("name") or "?")
    args = params.get("arguments")
    project = "-"
    if isinstance(args, Mapping):
        raw = args.get("projectId")
        if raw:
            project = str(raw)
    return name, project


async def access_log_middleware(
    ctx: ServerRequestContext[Any, Any],
    call_next: CallNext,
) -> HandlerResult:
    """Log every tools/call."""
    method = ctx.method

    if method in _QUIET_METHODS:
        return await call_next(ctx)

    if method != "tools/call":
        logger.debug("mcp method=%s request_id=%s", method, ctx.request_id)
        return await call_next(ctx)

    tool, project = _tool_bits(ctx.params)
    caller = caller_fingerprint(ctx)
    started = time.perf_counter()
    try:
        result = await call_next(ctx)
    except Exception as exc:
        ms = (time.perf_counter() - started) * 1000
        logger.warning(
            "tool error name=%s project=%s caller=%s ms=%.0f err=%s",
            tool,
            project,
            caller,
            ms,
            exc,
        )
        raise

    ms = (time.perf_counter() - started) * 1000
    logger.info(
        "tool ok name=%s project=%s caller=%s ms=%.0f",
        tool,
        project,
        caller,
        ms,
    )
    return result
