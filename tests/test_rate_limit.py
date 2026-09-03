"""Sliding-window rate limiter for tools/call."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from mcp.shared.exceptions import MCPError

from viaduct_mcp.rate_limit import RATE_LIMIT_CODE, SlidingWindowLimiter, make_rate_limit_middleware


def test_allows_up_to_limit_then_blocks():
    limiter = SlidingWindowLimiter(limit=3, window_sec=60.0)
    now = 1000.0
    assert limiter.allow("a", now=now)[0] is True
    assert limiter.allow("a", now=now + 1)[0] is True
    assert limiter.allow("a", now=now + 2)[0] is True
    allowed, retry = limiter.allow("a", now=now + 3)
    assert allowed is False
    assert retry > 0
    # Other callers are independent.
    assert limiter.allow("b", now=now + 3)[0] is True


def test_window_expiry_frees_slots():
    limiter = SlidingWindowLimiter(limit=1, window_sec=10.0)
    assert limiter.allow("a", now=0.0)[0] is True
    assert limiter.allow("a", now=5.0)[0] is False
    assert limiter.allow("a", now=10.1)[0] is True


@pytest.mark.asyncio
async def test_middleware_raises_mcp_error():
    limiter = SlidingWindowLimiter(limit=1, window_sec=60.0)
    mw = make_rate_limit_middleware(limiter)

    async def ok(_ctx):
        return {"ok": True}

    ctx = SimpleNamespace(method="tools/call", params={"name": "c4_whoami"}, request=None)
    assert await mw(ctx, ok) == {"ok": True}  # type: ignore[arg-type]

    with pytest.raises(MCPError) as ei:
        await mw(ctx, ok)  # type: ignore[arg-type]
    assert ei.value.code == RATE_LIMIT_CODE
    assert "rate limit exceeded" in ei.value.message


@pytest.mark.asyncio
async def test_middleware_ignores_non_tool_methods():
    limiter = SlidingWindowLimiter(limit=1, window_sec=60.0)
    mw = make_rate_limit_middleware(limiter)
    calls = 0

    async def ok(_ctx):
        nonlocal calls
        calls += 1
        return None

    ctx = SimpleNamespace(method="tools/list", params=None, request=None)
    await mw(ctx, ok)  # type: ignore[arg-type]
    await mw(ctx, ok)  # type: ignore[arg-type]
    assert calls == 2
