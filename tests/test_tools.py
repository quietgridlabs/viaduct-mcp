"""End-to-end over the MCP surface with the upstream API mocked.

These call the tools the way a client does — by name, with a JSON payload — so
a schema that does not match its handler fails here rather than in Cursor.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from viaduct_mcp.config import Settings
from viaduct_mcp.server import build_server

API = "https://c4.example"

MODEL = {
    "systems": [{"id": "s1", "name": "Banking"}],
    "containers": [
        {"id": "c1", "name": "API", "sequenceDiagrams": [{"id": "d1", "name": "Login"}]}
    ],
    "components": [{"id": "e1", "name": "Charge"}],
    "codeElements": [],
    "dataFlows": [
        {
            "id": "f1",
            "name": "Checkout",
            "steps": [{"id": "st1", "from": {"id": "e1", "type": "component"},
                       "to": {"id": "c1", "type": "container"}}],
        }
    ],
}


def stdio_settings(**over) -> Settings:
    base = dict(
        api_url=API,
        default_project_id="p1",
        transport="stdio",
        host="0.0.0.0",
        port=8080,
        timeout_seconds=5.0,
        log_level="INFO",
        rate_limit_per_minute=0,
    )
    base.update(over)
    return Settings(**base)


class AuthCtx:
    """Stand-in for MCP Context with client Authorization headers."""

    def __init__(self, token: str = "c4pat_test"):
        self.headers = {"authorization": f"Bearer {token}"}


@pytest.fixture
def server():
    return build_server(stdio_settings())


async def call(server, name, args=None, *, token: str = "c4pat_test"):
    """The text of the single content block every tool here answers with."""
    result = await server.call_tool(name, args or {}, context=AuthCtx(token))
    blocks = getattr(result, "content", result)
    if isinstance(blocks, tuple):
        blocks = blocks[0]
    if isinstance(blocks, list) and blocks:
        return getattr(blocks[0], "text", str(blocks[0]))
    return str(blocks)


async def test_all_tools_are_registered(server):
    names = {t.name for t in await server.list_tools()}
    assert len(names) == 29
    assert "c4_whoami" in names and "c4_delete_data_flow_step" in names
    # The change-set pair is what an implementing agent reads instead of the
    # whole-project context; losing either silently sends it back to the dump.
    assert "c4_list_change_sets" in names
    assert "c4_get_implementation_bundle" in names
    # Progress is how a change set stops being a one-way handoff.
    assert "c4_report_progress" in names
    assert "c4_set_change_set_status" in names


@respx.mock
async def test_whoami_forwards_the_bearer_token(server):
    route = respx.get(f"{API}/api/me").mock(
        return_value=httpx.Response(200, json={"user": {"username": "demo"}})
    )
    out = await call(server, "c4_whoami")
    assert json.loads(out)["user"]["username"] == "demo"
    assert route.calls.last.request.headers["authorization"] == "Bearer c4pat_test"


@respx.mock
async def test_project_context_asks_for_markdown(server):
    route = respx.get(f"{API}/api/projects/p1/context").mock(
        return_value=httpx.Response(
            200, text="# Banking", headers={"content-type": "text/markdown"}
        )
    )
    out = await call(server, "c4_project_context", {"includeDocs": False})
    assert out == "# Banking"
    request = route.calls.last.request
    assert request.headers["accept"] == "text/markdown"
    assert request.url.params["docs"] == "0"
    assert request.url.params["sequences"] == "1"


@respx.mock
async def test_get_element_joins_the_model_and_its_docs(server):
    respx.get(f"{API}/api/projects/p1").mock(
        return_value=httpx.Response(
            200, json={"project": {"id": "p1", "name": "B", "model": MODEL}}
        )
    )
    respx.get(f"{API}/api/projects/p1/docs").mock(
        return_value=httpx.Response(200, json={"docs": [{"id": "doc1"}]})
    )
    args = {"ownerType": "container", "ownerId": "c1"}
    payload = json.loads(await call(server, "c4_get_element", args))
    assert payload["entity"]["name"] == "API"
    assert payload["docs"] == [{"id": "doc1"}]


@respx.mock
async def test_a_missing_element_is_an_error_not_an_empty_answer(server):
    respx.get(f"{API}/api/projects/p1").mock(
        return_value=httpx.Response(200, json={"project": {"id": "p1", "model": MODEL}})
    )
    with pytest.raises(Exception, match="Element not found"):
        await call(server, "c4_get_element", {"ownerType": "system", "ownerId": "ghost"})


@respx.mock
async def test_search_covers_both_the_model_and_the_docs(server):
    respx.get(f"{API}/api/projects/p1").mock(
        return_value=httpx.Response(200, json={"project": {"model": MODEL}})
    )
    respx.get(f"{API}/api/projects/p1/docs").mock(
        return_value=httpx.Response(
            200,
            json={"docs": [{"id": "d", "title": "Banking runbook", "owner_type": "system",
                            "owner_id": "s1", "markdown": ""}]},
        )
    )
    payload = json.loads(await call(server, "c4_search", {"query": "banking"}))
    assert [h["id"] for h in payload["elements"]] == ["s1"]
    assert payload["docs"][0]["ownerType"] == "system"


@respx.mock
async def test_a_write_is_refused_without_edit_access(server):
    respx.get(f"{API}/api/projects/p1/access").mock(
        return_value=httpx.Response(200, json={"canEdit": False, "access": "view"})
    )
    created = respx.post(f"{API}/api/projects/p1/elements")
    with pytest.raises(Exception, match="forbidden"):
        await call(server, "c4_create_element", {"kind": "system", "name": "New"})
    assert not created.called, "must not reach the API after a refusal"


@respx.mock
async def test_create_element_sends_only_the_fields_given(server):
    respx.get(f"{API}/api/projects/p1/access").mock(
        return_value=httpx.Response(200, json={"canEdit": True, "access": "owner"})
    )
    route = respx.post(f"{API}/api/projects/p1/elements").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    await call(server, "c4_create_element", {"kind": "system", "name": "New", "tags": ["a"]})
    body = json.loads(route.calls.last.request.content)
    assert body == {"kind": "system", "name": "New", "tags": ["a"]}


@respx.mock
async def test_a_broker_topic_is_created_as_a_channel_with_its_schemas(server):
    """A topic is not an endpoint: no method/request/response, but protocol,
    schemaFormat and the three schema sides reach the API unchanged."""
    respx.get(f"{API}/api/projects/p1/access").mock(
        return_value=httpx.Response(200, json={"canEdit": True, "access": "owner"})
    )
    route = respx.post(f"{API}/api/projects/p1/elements").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    await call(
        server,
        "c4_create_element",
        {
            "kind": "channel",
            "name": "ALFA_SECURITY_SUBSCRIPTIONS_EVENTS",
            "containerId": "c1",
            "protocol": "kafka",
            "schemaFormat": "json-schema",
            "keySchema": "@format json-schema\n\nnull",
            "valueSchema": "@format json-schema\n@name SubscriptionCdcEvent\n\n{}",
            "headersSchema": "@format json-schema\n\n{}",
            "compatibility": "backward",
        },
    )
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "kind": "channel",
        "name": "ALFA_SECURITY_SUBSCRIPTIONS_EVENTS",
        "containerId": "c1",
        "protocol": "kafka",
        "schemaFormat": "json-schema",
        "keySchema": "@format json-schema\n\nnull",
        "valueSchema": "@format json-schema\n@name SubscriptionCdcEvent\n\n{}",
        "headersSchema": "@format json-schema\n\n{}",
        "compatibility": "backward",
    }


@respx.mock
async def test_a_channel_contract_can_be_patched_on_its_own(server):
    respx.get(f"{API}/api/projects/p1/access").mock(
        return_value=httpx.Response(200, json={"canEdit": True, "access": "owner"})
    )
    route = respx.patch(f"{API}/api/projects/p1/elements/component/e1").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    await call(
        server,
        "c4_update_element",
        {
            "ownerType": "component",
            "ownerId": "e1",
            "valueSchema": "@format avro\n@name Renamed\n\n{}",
        },
    )
    body = json.loads(route.calls.last.request.content)
    assert body == {"valueSchema": "@format avro\n@name Renamed\n\n{}"}


async def test_a_topic_spelling_the_server_does_not_settle_on_is_refused(server):
    """The Node side normalises a handful of aliases, but an outright unknown
    protocol would silently fall back to kafka — better to fail in the schema."""
    with pytest.raises(Exception, match="protocol"):
        await call(
            server,
            "c4_create_element",
            {"kind": "channel", "name": "T", "containerId": "c1", "protocol": "carrier-pigeon"},
        )


@respx.mock
async def test_a_broker_edge_carries_which_way_it_is_used(server):
    respx.get(f"{API}/api/projects/p1/access").mock(
        return_value=httpx.Response(200, json={"canEdit": True, "access": "owner"})
    )
    route = respx.post(f"{API}/api/projects/p1/connections").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    await call(
        server,
        "c4_upsert_connection",
        {"sourceId": "c1", "targetId": "c2", "channelRole": "consume"},
    )
    body = json.loads(route.calls.last.request.content)
    assert body == {"sourceId": "c1", "targetId": "c2", "channelRole": "consume"}


@respx.mock
async def test_a_flow_step_can_point_at_a_channel(server):
    respx.get(f"{API}/api/projects/p1/access").mock(
        return_value=httpx.Response(200, json={"canEdit": True, "access": "owner"})
    )
    route = respx.post(f"{API}/api/projects/p1/data-flows/f1/steps").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    await call(
        server,
        "c4_upsert_data_flow_step",
        {"flowId": "f1", "stepId": "st1", "channelIds": ["ch1"]},
    )
    body = json.loads(route.calls.last.request.content)
    assert body == {"stepId": "st1", "channelIds": ["ch1"]}


@respx.mock
async def test_a_flow_step_is_sent_as_from_even_though_the_tool_says_from_(server):
    """The tool parameter is `from_` because `from` is a Python keyword; the
    API contract is unchanged and still receives `from`."""
    respx.get(f"{API}/api/projects/p1/access").mock(
        return_value=httpx.Response(200, json={"canEdit": True})
    )
    route = respx.post(f"{API}/api/projects/p1/data-flows/f1/steps").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    await call(
        server,
        "c4_upsert_data_flow_step",
        {
            "flowId": "f1",
            "from_": {"id": "e1", "type": "component"},
            "to": {"id": "c1", "type": "container"},
            "branchKind": "alternative",
        },
    )
    body = json.loads(route.calls.last.request.content)
    assert body["from"] == {"id": "e1", "type": "component"}
    assert body["to"] == {"id": "c1", "type": "container"}
    assert body["branchKind"] == "alternative"
    assert "from_" not in body


@respx.mock
async def test_nested_flow_steps_keep_the_from_alias(server):
    respx.get(f"{API}/api/projects/p1/access").mock(
        return_value=httpx.Response(200, json={"canEdit": True})
    )
    route = respx.post(f"{API}/api/projects/p1/data-flows").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    await call(
        server,
        "c4_upsert_data_flow",
        {
            "name": "Checkout",
            "steps": [
                {"from": {"id": "e1", "type": "component"}, "to": {"id": "c1", "type": "container"}}
            ],
        },
    )
    body = json.loads(route.calls.last.request.content)
    assert body["steps"][0]["from"] == {"id": "e1", "type": "component"}


@respx.mock
async def test_upstream_failures_surface_with_their_status(server):
    respx.get(f"{API}/api/me").mock(return_value=httpx.Response(401, text="unauthorized"))
    with pytest.raises(Exception, match="401"):
        await call(server, "c4_whoami")


async def test_project_id_is_required_when_there_is_no_default():
    bare = build_server(stdio_settings(default_project_id=""))
    with pytest.raises(Exception, match="projectId required"):
        await call(bare, "c4_project_access")


@respx.mock
async def test_report_progress_sends_the_criterion_and_ref(server):
    """The registration test never runs a tool body, so a plain call-signature
    mistake in one sailed through it. These exercise the request itself."""
    respx.get(f"{API}/api/projects/p1/access").mock(
        return_value=httpx.Response(200, json={"canEdit": True, "access": "owner"})
    )
    route = respx.post(f"{API}/api/projects/p1/change-sets/cs_1/progress").mock(
        return_value=httpx.Response(
            201, json={"changeSet": {"id": "cs_1", "status": "implementing"}}
        )
    )
    out = await call(
        server,
        "c4_report_progress",
        {
            "changeSetId": "cs_1",
            "summary": "UI employee card matches design",
            "criterionId": "ac_1",
            "ref": "65b7fa0",
        },
    )
    assert json.loads(out)["changeSet"]["status"] == "implementing"
    sent = json.loads(route.calls.last.request.content)
    assert sent == {
        "summary": "UI employee card matches design",
        "criterionId": "ac_1",
        "ref": "65b7fa0",
    }


@respx.mock
async def test_report_progress_omits_unset_fields(server):
    respx.get(f"{API}/api/projects/p1/access").mock(
        return_value=httpx.Response(200, json={"canEdit": True, "access": "owner"})
    )
    route = respx.post(f"{API}/api/projects/p1/change-sets/cs_1/progress").mock(
        return_value=httpx.Response(201, json={"changeSet": {"id": "cs_1"}})
    )
    await call(server, "c4_report_progress", {"changeSetId": "cs_1", "summary": "general note"})
    assert json.loads(route.calls.last.request.content) == {"summary": "general note"}


@respx.mock
async def test_set_change_set_status_patches_the_change_set(server):
    respx.get(f"{API}/api/projects/p1/access").mock(
        return_value=httpx.Response(200, json={"canEdit": True, "access": "owner"})
    )
    route = respx.patch(f"{API}/api/projects/p1/change-sets/cs_1").mock(
        return_value=httpx.Response(200, json={"changeSet": {"id": "cs_1", "status": "done"}})
    )
    await call(server, "c4_set_change_set_status", {"changeSetId": "cs_1", "status": "done"})
    assert json.loads(route.calls.last.request.content) == {"status": "done"}


async def test_set_change_set_status_refuses_a_status_that_is_not_one(server):
    with pytest.raises(Exception, match="status must be one of"):
        await call(
            server, "c4_set_change_set_status", {"changeSetId": "cs_1", "status": "finished"}
        )


@respx.mock
async def test_implementation_bundle_reads_the_change_set_scoped_endpoint(server):
    route = respx.get(f"{API}/api/projects/p1/change-sets/cs_1/bundle").mock(
        return_value=httpx.Response(200, json={"changeSetId": "cs_1", "intent": "Build it"})
    )
    out = await call(server, "c4_get_implementation_bundle", {"changeSetId": "cs_1"})
    assert json.loads(out)["intent"] == "Build it"
    assert route.calls.call_count == 1
