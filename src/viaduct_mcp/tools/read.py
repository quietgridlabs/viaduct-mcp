"""Read-only tools. None of these need edit access."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError

from ..config import Settings
from ..model import find_in_model, search_model, summarize_data_flow
from ..schemas import OwnerType, ProjectId
from ..session import client_for, resolve_project_id


def as_text(payload: Any) -> str:
    """Tools answer text; structures go out as indented JSON, as before."""
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, indent=2, ensure_ascii=False)


def register(server: MCPServer, settings: Settings) -> None:
    @server.tool(name="c4_whoami", description="Verify C4 API auth and return the current user.")
    async def c4_whoami(ctx: Context) -> str:
        client = client_for(settings, ctx)
        return as_text(await client.get("/api/me"))

    @server.tool(
        name="c4_list_projects",
        description="List Viaduct projects accessible to the authenticated user "
        "(includes access role).",
    )
    async def c4_list_projects(ctx: Context) -> str:
        client = client_for(settings, ctx)
        return as_text(await client.get("/api/projects"))

    @server.tool(
        name="c4_project_access",
        description="Check access for a project. Write tools require canEdit=true "
        "(owner or edit share).",
    )
    async def c4_project_access(ctx: Context, projectId: ProjectId = None) -> str:
        client = client_for(settings, ctx)
        pid = resolve_project_id(settings, projectId)
        return as_text(await client.get(f"/api/projects/{pid}/access"))

    @server.tool(
        name="c4_project_context",
        description="Get LLM-ready markdown context for a project: systems, containers/services, "
        "components/endpoints (incl. request/response/headers), attached documentation "
        "and sequence diagrams.",
    )
    async def c4_project_context(
        ctx: Context,
        projectId: ProjectId = None,
        includeDocs: bool | None = None,
        includeSequences: bool | None = None,
        maxDocChars: int | None = None,
        maxSequenceChars: int | None = None,
    ) -> str:
        client = client_for(settings, ctx)
        pid = resolve_project_id(settings, projectId)
        markdown = await client.get(
            f"/api/projects/{pid}/context",
            accept="text/markdown",
            query={
                "docs": "0" if includeDocs is False else "1",
                "sequences": "0" if includeSequences is False else "1",
                "maxDocChars": maxDocChars,
                "maxSequenceChars": maxSequenceChars,
            },
        )
        return as_text(markdown)

    @server.tool(
        name="c4_get_element",
        description="Get one C4 element (system/container/component/code) with docs and sequences.",
    )
    async def c4_get_element(
        ctx: Context, ownerType: OwnerType, ownerId: str, projectId: ProjectId = None
    ) -> str:
        client = client_for(settings, ctx)
        pid = resolve_project_id(settings, projectId)
        project = (await client.get(f"/api/projects/{pid}"))["project"]
        entity = find_in_model(project.get("model") or {}, ownerType, ownerId)
        if entity is None:
            raise ToolError(f"Element not found: {ownerType}/{ownerId}")
        docs = (
            await client.get(
                f"/api/projects/{pid}/docs", query={"ownerType": ownerType, "ownerId": ownerId}
            )
        ).get("docs")
        return as_text(
            {
                "project": {"id": project.get("id"), "name": project.get("name")},
                "ownerType": ownerType,
                "entity": entity,
                "docs": docs,
            }
        )

    @server.tool(
        name="c4_list_docs",
        description="List documentation files for a project (optionally filtered by owner).",
    )
    async def c4_list_docs(
        ctx: Context,
        projectId: ProjectId = None,
        ownerType: OwnerType | None = None,
        ownerId: str | None = None,
    ) -> str:
        client = client_for(settings, ctx)
        pid = resolve_project_id(settings, projectId)
        return as_text(
            await client.get(
                f"/api/projects/{pid}/docs", query={"ownerType": ownerType, "ownerId": ownerId}
            )
        )

    @server.tool(
        name="c4_get_doc",
        description="Get a single documentation file by id (searches project docs list).",
    )
    async def c4_get_doc(ctx: Context, docId: str, projectId: ProjectId = None) -> str:
        client = client_for(settings, ctx)
        pid = resolve_project_id(settings, projectId)
        docs = (await client.get(f"/api/projects/{pid}/docs")).get("docs") or []
        for doc in docs:
            if doc.get("id") == docId:
                return as_text(doc)
        raise ToolError(f"Doc not found: {docId}")

    @server.tool(
        name="c4_list_sequences",
        description="List sequence diagrams attached to containers/components in a project.",
    )
    async def c4_list_sequences(ctx: Context, projectId: ProjectId = None) -> str:
        client = client_for(settings, ctx)
        pid = resolve_project_id(settings, projectId)
        payload = await client.get(
            f"/api/projects/{pid}/context", query={"format": "json", "docs": "0"}
        )
        return as_text({"sequences": (payload.get("project") or {}).get("sequences") or []})

    @server.tool(
        name="c4_get_sequence", description="Get one sequence diagram (PlantUML) by id."
    )
    async def c4_get_sequence(ctx: Context, diagramId: str, projectId: ProjectId = None) -> str:
        client = client_for(settings, ctx)
        pid = resolve_project_id(settings, projectId)
        model = (await client.get(f"/api/projects/{pid}"))["project"].get("model") or {}
        for owner_type, key in (("container", "containers"), ("component", "components")):
            for owner in model.get(key) or []:
                for diagram in owner.get("sequenceDiagrams") or []:
                    if diagram.get("id") == diagramId:
                        return as_text(
                            {
                                "ownerType": owner_type,
                                "ownerId": owner.get("id"),
                                "ownerName": owner.get("name"),
                                "diagram": diagram,
                            }
                        )
        raise ToolError(f"Sequence not found: {diagramId}")

    @server.tool(
        name="c4_list_data_flows",
        description="List project-level Magic flows with step outlines (from→to, endpoints, "
        "connections, parallelGroupId, branchKind). Use this before creating a flow so you "
        "update an existing journey instead of duplicating it.",
    )
    async def c4_list_data_flows(ctx: Context, projectId: ProjectId = None) -> str:
        client = client_for(settings, ctx)
        pid = resolve_project_id(settings, projectId)
        model = (await client.get(f"/api/projects/{pid}"))["project"].get("model") or {}
        flows = [summarize_data_flow(model, flow) for flow in model.get("dataFlows") or []]
        return as_text({"dataFlows": flows})

    @server.tool(
        name="c4_get_data_flow",
        description="Get one Magic flow with resolved participant names, steps, endpoints, "
        "connections, and optional parallelGroupId / branchKind.",
    )
    async def c4_get_data_flow(ctx: Context, flowId: str, projectId: ProjectId = None) -> str:
        client = client_for(settings, ctx)
        pid = resolve_project_id(settings, projectId)
        model = (await client.get(f"/api/projects/{pid}"))["project"].get("model") or {}
        for flow in model.get("dataFlows") or []:
            if flow.get("id") == flowId:
                return as_text({"flow": summarize_data_flow(model, flow)})
        raise ToolError(f"Magic flow not found: {flowId}")

    @server.tool(
        name="c4_search",
        description="Search systems/containers/components/code/Magic flows (names, descriptions, "
        "endpoints, sequences) in a project.",
    )
    async def c4_search(ctx: Context, query: str, projectId: ProjectId = None) -> str:
        if not query:
            raise ToolError("query is required")
        client = client_for(settings, ctx)
        pid = resolve_project_id(settings, projectId)
        model = (await client.get(f"/api/projects/{pid}"))["project"].get("model") or {}
        hits = search_model(model, query)

        needle = query.lower()
        docs = (await client.get(f"/api/projects/{pid}/docs")).get("docs") or []
        doc_hits = [
            {
                "type": "documentation",
                "id": doc.get("id"),
                "title": doc.get("title"),
                "ownerType": doc.get("owner_type"),
                "ownerId": doc.get("owner_id"),
            }
            for doc in docs
            if needle in (doc.get("title") or "").lower()
            or needle in (doc.get("markdown") or "").lower()
        ]
        return as_text({"query": query, "elements": hits, "docs": doc_hits})

    @server.tool(
        name="c4_list_change_sets",
        description="List implementation change sets for a project: the pieces of work an "
        "architect has specified, each pinned to a named architecture revision.",
    )
    async def c4_list_change_sets(ctx: Context, projectId: ProjectId = None) -> str:
        client = client_for(settings, ctx)
        pid = resolve_project_id(settings, projectId)
        return as_text(await client.get(f"/api/projects/{pid}/change-sets"))

    @server.tool(
        name="c4_get_implementation_bundle",
        description=(
            "Everything needed to implement ONE change set, and nothing else: the intent, "
            "the architecture constraints, the acceptance criteria with stable ids, and only "
            "the in-scope elements, their contracts, the connections crossing the boundary, "
            "the flows that pass through, and the attached docs.\n\n"
            "Read this INSTEAD of c4_project_context when implementing. It is scoped to the "
            "work and read from a pinned revision, so it stays fixed while you work; "
            "c4_project_context returns the whole project and drifts as others edit it.\n\n"
            "Write a test for every acceptance criterion and put its id in the test name, "
            "e.g. it('[ac_19eedf3f7128] returns 201 ...'). That id is how the criterion is "
            "later matched to evidence that it holds."
        ),
    )
    async def c4_get_implementation_bundle(
        ctx: Context, changeSetId: str, projectId: ProjectId = None
    ) -> str:
        if not changeSetId:
            raise ToolError("changeSetId is required")
        client = client_for(settings, ctx)
        pid = resolve_project_id(settings, projectId)
        return as_text(
            await client.get(f"/api/projects/{pid}/change-sets/{changeSetId}/bundle")
        )
