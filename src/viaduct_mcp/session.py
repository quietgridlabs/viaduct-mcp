"""Per-call plumbing: which token, which project, and may we write.

The token always comes from the request ``Authorization`` header — the same
one the user puts in their MCP client config. The server never holds a shared
or ambient credential.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError

from .client import C4Client
from .config import Settings

_BEARER_PREFIX = "bearer "


def token_from_headers(headers: Any) -> str:
    """The bearer token on this request, or empty when there is none."""
    if not headers:
        return ""
    # Starlette headers are case-insensitive; a plain dict may not be.
    raw = headers.get("authorization") or headers.get("Authorization") or ""
    if not raw:
        return ""
    if raw.lower().startswith(_BEARER_PREFIX):
        return raw[len(_BEARER_PREFIX) :].strip()
    return raw.strip()


def _headers_from_ctx(ctx: Context | None) -> Any:
    if ctx is None:
        return None
    try:
        return ctx.headers
    except ValueError:
        # Real Context outside a request — no transport headers available.
        return None


def client_for(settings: Settings, ctx: Context | None) -> C4Client:
    """Build a client for one tool call."""
    token = token_from_headers(_headers_from_ctx(ctx))
    return C4Client(settings.require_api_url(), token, settings.timeout_seconds)


def resolve_project_id(settings: Settings, project_id: str | None) -> str:
    resolved = (project_id or settings.default_project_id or "").strip()
    if not resolved:
        raise ToolError("projectId required (or set C4_DEFAULT_PROJECT_ID)")
    return resolved


async def require_editable(client: C4Client, project_id: str) -> str:
    """Fail before writing when the caller only has view access."""
    access = await client.get(f"/api/projects/{project_id}/access")
    if not access.get("canEdit"):
        raise ToolError(
            f"forbidden: project {project_id} is {access.get('access') or 'view-only'}; "
            "edit access required"
        )
    return project_id


def compact(**fields: Any) -> dict[str, Any]:
    """Body with the unset fields dropped, so a patch never blanks a field."""
    return {k: v for k, v in fields.items() if v is not None}
