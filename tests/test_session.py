"""Token resolution — the part that must never get a shared server wrong."""

from __future__ import annotations

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from viaduct_mcp.client import C4ApiError, C4Client
from viaduct_mcp.config import Settings
from viaduct_mcp.session import (
    compact,
    require_editable,
    resolve_project_id,
    token_from_headers,
)


def settings(**over) -> Settings:
    base = dict(
        api_url="https://c4.example",
        default_project_id="",
        transport="streamable-http",
        host="0.0.0.0",
        port=8080,
        timeout_seconds=5.0,
        log_level="INFO",
        rate_limit_per_minute=0,
    )
    base.update(over)
    return Settings(**base)


class FakeCtx:
    def __init__(self, headers):
        self.headers = headers


def test_bearer_is_parsed_case_insensitively():
    assert token_from_headers({"authorization": "Bearer abc"}) == "abc"
    assert token_from_headers({"Authorization": "bearer abc"}) == "abc"
    assert token_from_headers({"authorization": "abc"}) == "abc"
    assert token_from_headers({}) == ""
    assert token_from_headers(None) == ""


def test_token_comes_from_request_authorization():
    from viaduct_mcp.session import client_for

    client = client_for(
        settings(), FakeCtx({"authorization": "Bearer c4pat_caller"})
    )
    assert client._token == "c4pat_caller"


def test_missing_authorization_never_falls_back_to_an_ambient_token():
    """A shared credential would serve one caller's data to another."""
    from viaduct_mcp.session import client_for

    with pytest.raises(RuntimeError, match="No API token"):
        client_for(settings(), FakeCtx({}))
    with pytest.raises(RuntimeError, match="No API token"):
        client_for(settings(), FakeCtx(None))


def test_project_id_prefers_the_argument_then_the_default():
    assert resolve_project_id(settings(default_project_id="d"), "explicit") == "explicit"
    assert resolve_project_id(settings(default_project_id="d"), None) == "d"
    with pytest.raises(ToolError, match="projectId required"):
        resolve_project_id(settings(), None)


def test_compact_drops_unset_fields_so_a_patch_never_blanks_one():
    assert compact(a=1, b=None, c=False, d="") == {"a": 1, "c": False, "d": ""}


class FakeClient:
    def __init__(self, access):
        self._access = access

    async def get(self, _path, **_kw):
        return self._access


async def test_require_editable_refuses_view_only():
    assert await require_editable(FakeClient({"canEdit": True}), "p1") == "p1"
    with pytest.raises(ToolError, match="view-only"):
        await require_editable(FakeClient({"canEdit": False}), "p1")
    with pytest.raises(ToolError, match="is view"):
        await require_editable(FakeClient({"canEdit": False, "access": "view"}), "p1")


def test_client_rejects_missing_config_up_front():
    with pytest.raises(RuntimeError, match="C4_API_URL"):
        C4Client("", "token")
    with pytest.raises(RuntimeError, match="No API token"):
        C4Client("https://c4.example", "")


def test_api_error_carries_the_status_and_is_truncated():
    err = C4ApiError(404, "GET", "/api/projects/x", "y" * 900)
    assert err.status == 404
    assert "GET /api/projects/x" in str(err)
    assert len(str(err)) < 500
