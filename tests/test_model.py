"""The pure projections. These carry the behaviour ported from the Node server,
so they are where a silent divergence would show up first."""

from __future__ import annotations

from viaduct_mcp.model import (
    find_in_model,
    participant_name,
    search_model,
    summarize_data_flow,
)

MODEL = {
    "systems": [{"id": "s1", "name": "Banking", "description": "Core"}],
    "containers": [
        {
            "id": "c1",
            "name": "API",
            "technology": "java",
            "sequenceDiagrams": [{"id": "d1", "name": "Login", "plantUmlSource": "@startuml"}],
        }
    ],
    "components": [
        {"id": "e1", "name": "Charge", "method": "POST", "endpoint": "/charge", "kind": "endpoint"}
    ],
    "codeElements": [{"id": "k1", "name": "ChargeService"}],
    "dataFlows": [
        {
            "id": "f1",
            "name": "Checkout",
            "description": "money moves",
            "steps": [
                {
                    "id": "st1",
                    "name": "submit",
                    "from": {"id": "e1", "type": "component"},
                    "to": {"id": "c1", "type": "container"},
                },
                {
                    "id": "st2",
                    "from": {"id": "c1", "type": "container"},
                    "to": {"id": "gone", "type": "container"},
                    "parallelGroupId": "g1",
                    "branchKind": "alternative",
                },
            ],
        }
    ],
}


def test_find_in_model_walks_the_right_collection():
    assert find_in_model(MODEL, "container", "c1")["name"] == "API"
    assert find_in_model(MODEL, "code", "k1")["name"] == "ChargeService"
    assert find_in_model(MODEL, "system", "nope") is None


def test_search_matches_across_fields_and_is_case_insensitive():
    assert [h["id"] for h in search_model(MODEL, "BANKING")] == ["s1"]
    assert [h["id"] for h in search_model(MODEL, "/charge")] == ["e1"]
    # Sequence source is part of the haystack, as in the Node server.
    assert [h["id"] for h in search_model(MODEL, "@startuml")] == ["c1"]


def test_search_reports_flows_with_a_step_count():
    hits = search_model(MODEL, "checkout")
    assert hits == [
        {
            "ownerType": "dataFlow",
            "id": "f1",
            "name": "Checkout",
            "description": "money moves",
            "stepCount": 2,
        }
    ]


def test_search_finds_a_flow_by_its_step_text():
    assert [h["id"] for h in search_model(MODEL, "submit")] == ["f1"]


def test_participant_name_falls_back_to_the_id():
    assert participant_name(MODEL, {"id": "c1", "type": "container"}) == "API"
    assert participant_name(MODEL, {"id": "gone", "type": "container"}) == "gone"
    assert participant_name(MODEL, None) == ""


def test_summarize_resolves_names_and_indexes_steps():
    summary = summarize_data_flow(MODEL, MODEL["dataFlows"][0])
    assert summary["stepCount"] == 2
    first, second = summary["steps"]
    assert first["index"] == 0
    assert first["from"]["name"] == "Charge"
    assert first["to"]["name"] == "API"
    assert second["index"] == 1
    assert second["to"]["name"] == "gone"


def test_branch_kind_only_appears_on_grouped_steps():
    """Absent, not null — `JSON.stringify` drops undefined and the Node server's
    output has no such key, so writing one would diverge on the wire."""
    summary = summarize_data_flow(MODEL, MODEL["dataFlows"][0])
    ungrouped, grouped = summary["steps"]
    assert "branchKind" not in ungrouped
    assert "parallelGroupId" not in ungrouped
    assert grouped["branchKind"] == "alternative"
    assert grouped["parallelGroupId"] == "g1"


def test_search_hits_omit_fields_the_element_does_not_have():
    hit = search_model(MODEL, "banking")[0]
    assert hit["name"] == "Banking"
    for absent in ("kind", "endpoint", "method"):
        assert absent not in hit, f"{absent} should be omitted, not null"


def test_a_grouped_step_without_a_kind_defaults_to_parallel():
    model = {**MODEL, "dataFlows": [
        {"id": "f2", "name": "x", "steps": [
            {"id": "s", "from": {"id": "c1", "type": "container"},
             "to": {"id": "c1", "type": "container"}, "parallelGroupId": "g"}
        ]}
    ]}
    assert summarize_data_flow(model, model["dataFlows"][0])["steps"][0]["branchKind"] == "parallel"


def test_empty_model_does_not_explode():
    assert search_model({}, "anything") == []
    assert find_in_model({}, "system", "x") is None
