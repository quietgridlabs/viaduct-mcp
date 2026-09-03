"""Pure projections over a Viaduct model.

Ported from the Node server one-for-one, including the quirks: search is a
case-insensitive substring over a joined haystack, and a flow step only reports
a branch kind when it actually belongs to a group. Keeping the behaviour
identical is the point — this is a replacement, not a redesign.
"""

from __future__ import annotations

from typing import Any

OwnerType = str

_COLLECTION_BY_TYPE = {
    "system": "systems",
    "container": "containers",
    "component": "components",
    "code": "codeElements",
}


def _collection(model: dict[str, Any], owner_type: str) -> list[dict[str, Any]]:
    key = _COLLECTION_BY_TYPE.get(owner_type, "codeElements")
    return model.get(key) or []


def find_in_model(
    model: dict[str, Any], owner_type: str, owner_id: str
) -> dict[str, Any] | None:
    for element in _collection(model, owner_type):
        if element.get("id") == owner_id:
            return element
    return None


def _drop_none(mapping: dict[str, Any]) -> dict[str, Any]:
    """Omit keys whose value is None.

    `JSON.stringify` drops `undefined` properties, so the Node server's output
    simply has no `branchKind` on an ungrouped step. Writing `null` instead
    would be 7% more tokens of nothing, and reads to a model as "explicitly
    none" rather than "not applicable". Only the projections use this — the
    pass-through tools must keep whatever nulls the API really sent.
    """
    return {k: v for k, v in mapping.items() if v is not None}


def _haystack(*parts: Any) -> str:
    return "\n".join(str(p) for p in parts if p).lower()


def search_model(model: dict[str, Any], query: str) -> list[dict[str, Any]]:
    needle = query.lower()
    hits: list[dict[str, Any]] = []

    def consider(owner_type: str, element: dict[str, Any]) -> None:
        diagram_text = [
            value
            for diagram in element.get("sequenceDiagrams") or []
            for value in (diagram.get("name"), diagram.get("plantUmlSource"))
        ]
        hay = _haystack(
            element.get("name"),
            element.get("description"),
            element.get("technology"),
            element.get("endpoint"),
            element.get("method"),
            element.get("request"),
            element.get("response"),
            element.get("headers"),
            *diagram_text,
        )
        if needle in hay:
            hits.append(
                _drop_none(
                    {
                        "ownerType": owner_type,
                        "id": element.get("id"),
                        "name": element.get("name"),
                        "kind": element.get("kind"),
                        "endpoint": element.get("endpoint"),
                        "method": element.get("method"),
                        "description": element.get("description"),
                    }
                )
            )

    for owner_type in ("system", "container", "component", "code"):
        for element in _collection(model, owner_type):
            consider(owner_type, element)

    for flow in model.get("dataFlows") or []:
        steps = flow.get("steps") or []
        step_text = [
            value for step in steps for value in (step.get("name"), step.get("description"))
        ]
        if needle in _haystack(flow.get("name"), flow.get("description"), *step_text):
            hits.append(
                _drop_none(
                    {
                        "ownerType": "dataFlow",
                        "id": flow.get("id"),
                        "name": flow.get("name"),
                        "description": flow.get("description"),
                        "stepCount": len(steps),
                    }
                )
            )

    return hits


def participant_name(model: dict[str, Any], participant: dict[str, Any] | None) -> str:
    if not participant or not participant.get("id"):
        return ""
    for element in _collection(model, participant.get("type") or ""):
        if element.get("id") == participant["id"]:
            return element.get("name") or participant["id"]
    return participant["id"]


def _step_branch_kind(step: dict[str, Any]) -> str | None:
    """Only grouped steps have a branch kind; an ungrouped one reports none."""
    if not step.get("parallelGroupId"):
        return None
    return "alternative" if step.get("branchKind") == "alternative" else "parallel"


def summarize_data_flow(model: dict[str, Any], flow: dict[str, Any]) -> dict[str, Any]:
    steps = flow.get("steps") or []
    return _drop_none({
        "id": flow.get("id"),
        "name": flow.get("name"),
        "description": flow.get("description") or "",
        "stepCount": len(steps),
        "documentationIds": flow.get("documentationIds") or [],
        "sequenceIds": flow.get("sequenceIds") or [],
        "updatedAt": flow.get("updatedAt"),
        "steps": [
            _drop_none({
                "id": step.get("id"),
                "index": index,
                "name": step.get("name") or "",
                "description": step.get("description") or "",
                "from": {
                    **(step.get("from") or {}),
                    "name": participant_name(model, step.get("from")),
                },
                "to": {**(step.get("to") or {}), "name": participant_name(model, step.get("to"))},
                "endpointIds": step.get("endpointIds") or [],
                "connections": step.get("connections") or [],
                "parallelGroupId": step.get("parallelGroupId") or None,
                "branchKind": _step_branch_kind(step),
            })
            for index, step in enumerate(steps)
        ],
    })
