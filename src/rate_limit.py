"""Per-caller rate limit for tools/call (HTTP deployments).

In-memory sliding window keyed by token fingerprint. Fine for a single
process; with multiple replicas each process has its own counters — that is
the same tradeoff as ``stateless_http``. Set ``C4_MCP_RATE_LIMIT=0`` to disable.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.shared.exceptions import MCPError

from .logging_setup import caller_fingerprint

logger = logging.getLogger("viaduct_mcp")

# Implementation-defined JSON-RPC server error ( -32000 … -32099 ).
RATE_LIMIT_CODE = -32029


class SlidingWindowLimiter:
    """``limit`` hits per ``window_sec``, tracked per key."""

    def __init__(self, limit: int, window_sec: float = 60.0) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if window_sec <= 0:
            raise ValueError("window_sec must be positive")
        self.limit = limit
        self.window_sec = window_sec
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, *, now: float | None = None) -> tuple[bool, float]:
        """Return ``(allowed, retry_after_seconds)``. ``retry_after`` is 0 when allowed."""
        t = time.monotonic() if now is None else now
        cutoff = t - self.window_sec
        with self._lock:
            bucket = self._hits.get(key)
            if bucket is None:
                bucket = deque()
                self._hits[key] = bucket
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.limit:
                retry = self.window_sec - (t - bucket[0])
                return False, max(retry, 0.0)
            bucket.append(t)
            return True, 0.0

    def reset(self) -> None:
        """Drop all state — tests only."""
        with self._lock:
            self._hits.clear()


def make_rate_limit_middleware(
    limiter: SlidingWindowLimiter,
) -> Callable[
    [ServerRequestContext[Any, Any], CallNext],
    Awaitable[HandlerResult],
]:
    """Refuse ``tools/call`` when the caller is over the window."""

    async def rate_limit_middleware(
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
    ) -> HandlerResult:
        if ctx.method != "tools/call":
            return await call_next(ctx)

        caller = caller_fingerprint(ctx)
        allowed, retry_after = limiter.allow(caller)
        if not allowed:
            retry = max(1, int(retry_after + 0.999))
            logger.warning(
                "rate limited caller=%s limit=%s/%ss retry_after=%s",
                caller,
                limiter.limit,
                int(limiter.window_sec),
                retry,
            )
            raise MCPError(
                RATE_LIMIT_CODE,
                f"rate limit exceeded: {limiter.limit} tool calls per "
                f"{int(limiter.window_sec)}s; retry after {retry}s",
                data={"retry_after_seconds": retry, "limit": limiter.limit},
            )
        return await call_next(ctx)

    return rate_limit_middleware
