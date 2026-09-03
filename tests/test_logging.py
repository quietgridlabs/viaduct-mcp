"""Logging helpers — fingerprints and the tools/call access log."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from viaduct_mcp.logging_setup import access_log_middleware, token_fingerprint


def test_token_fingerprint_is_stable_and_short():
    assert token_fingerprint("") == "-"
    a = token_fingerprint("c4pat_secret")
    b = token_fingerprint("c4pat_secret")
    assert a == b
    assert len(a) == 12
    assert a != token_fingerprint("c4pat_other")
    assert "secret" not in a


@pytest.mark.asyncio
async def test_access_log_records_tool_ok(caplog):
    async def ok(_ctx):
        return {"ok": True}

    ctx = SimpleNamespace(
        method="tools/call",
        params={"name": "c4_whoami", "arguments": {}},
        request_id="1",
        request=None,
    )
    with caplog.at_level(logging.INFO, logger="viaduct_mcp"):
        result = await access_log_middleware(ctx, ok)  # type: ignore[arg-type]

    assert result == {"ok": True}
    assert any("tool ok name=c4_whoami" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_access_log_records_tool_error(caplog):
    async def boom(_ctx):
        raise RuntimeError("nope")

    ctx = SimpleNamespace(
        method="tools/call",
        params={"name": "c4_search", "arguments": {"projectId": "p1", "query": "x"}},
        request_id="2",
        request=None,
    )
    with (
        caplog.at_level(logging.WARNING, logger="viaduct_mcp"),
        pytest.raises(RuntimeError, match="nope"),
    ):
        await access_log_middleware(ctx, boom)  # type: ignore[arg-type]

    assert any(
        "tool error name=c4_search project=p1" in r.message for r in caplog.records
    )


@pytest.mark.asyncio
async def test_quiet_methods_are_silent(caplog):
    async def ok(_ctx):
        return None

    ctx = SimpleNamespace(
        method="tools/list",
        params=None,
        request_id="3",
        request=None,
    )
    with caplog.at_level(logging.DEBUG, logger="viaduct_mcp"):
        await access_log_middleware(ctx, ok)  # type: ignore[arg-type]

    assert not any("tools/list" in r.message for r in caplog.records)
