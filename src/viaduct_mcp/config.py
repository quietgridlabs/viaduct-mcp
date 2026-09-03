"""Runtime configuration, read once at import.

Transports differ in how the process is reached (stdio vs HTTP), not in how
credentials arrive: the API token is always the request ``Authorization``
header from the MCP client config.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

Transport = Literal["stdio", "streamable-http"]

DEFAULT_TIMEOUT_SECONDS = 30.0
# Shared HTTP only — agents can be chatty; 0 disables.
DEFAULT_HTTP_RATE_LIMIT_PER_MINUTE = 120


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


@dataclass(frozen=True)
class Settings:
    api_url: str
    """Base URL of the Viaduct API, no trailing slash."""

    default_project_id: str
    transport: Transport
    host: str
    port: int
    timeout_seconds: float
    log_level: str
    rate_limit_per_minute: int
    """Max tools/call per caller fingerprint per minute. 0 = off."""

    @property
    def is_http(self) -> bool:
        return self.transport == "streamable-http"

    def require_api_url(self) -> str:
        if not self.api_url:
            raise RuntimeError("Missing env C4_API_URL")
        return self.api_url


def load_settings() -> Settings:
    raw_transport = _env("C4_MCP_TRANSPORT", "stdio").lower()
    if raw_transport not in ("stdio", "streamable-http"):
        raise RuntimeError(
            f"C4_MCP_TRANSPORT must be 'stdio' or 'streamable-http', got {raw_transport!r}"
        )

    try:
        port = int(_env("C4_MCP_PORT", "8080"))
    except ValueError as exc:
        raise RuntimeError("C4_MCP_PORT must be a number") from exc

    try:
        timeout = float(_env("C4_MCP_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS)))
    except ValueError as exc:
        raise RuntimeError("C4_MCP_TIMEOUT must be a number of seconds") from exc

    # stdio: one process per person — no shared abuse surface, default off.
    # HTTP: shared process — default on unless explicitly set.
    rate_default = (
        str(DEFAULT_HTTP_RATE_LIMIT_PER_MINUTE) if raw_transport == "streamable-http" else "0"
    )
    try:
        rate_limit = int(_env("C4_MCP_RATE_LIMIT", rate_default))
    except ValueError as exc:
        raise RuntimeError("C4_MCP_RATE_LIMIT must be an integer (0 disables)") from exc
    if rate_limit < 0:
        raise RuntimeError("C4_MCP_RATE_LIMIT must be >= 0")

    return Settings(
        api_url=_env("C4_API_URL").rstrip("/"),
        default_project_id=_env("C4_DEFAULT_PROJECT_ID"),
        transport=raw_transport,  # type: ignore[arg-type]
        host=_env("C4_MCP_HOST", "0.0.0.0"),
        port=port,
        timeout_seconds=timeout,
        log_level=_env("C4_MCP_LOG_LEVEL", "info").upper(),
        rate_limit_per_minute=rate_limit,
    )
