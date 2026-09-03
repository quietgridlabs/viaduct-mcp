"""Write tools. Every one checks edit access before touching anything."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError

from ..config import Settings
from ..schemas import (
    BranchKind,
    ChannelCompatibility,
    ChannelProtocol,
    ChannelRole,
    ChannelSchemaFormat,
    ConnectionRef,
    ElementKind,
    FlowParticipant,
    FlowStep,
    Group,
    HeadersSchema,
    KeySchema,
    OwnerType,
    PathType,
    ProjectId,
    SequenceOwnerType,
    TableColumn,
    Tags,
    ValueSchema,
)
from ..session import client_for, compact, require_editable, resolve_project_id
from .read import as_text


def _dump(value: Any) -> Any:
    """Pydantic models out to plain JSON, honouring the `from` alias."""
    if isinstance(value, list):
        return [_dump(v) for v in value]
    if hasattr(value, "model_dump"):
        return value.model_dump(by_alias=True, exclude_none=True)
    return value


def register(server: MCPServer, settings: Settings) -> None:
    async def editable(ctx: Context, project_id: str | None):
        client = client_for(settings, ctx)
        pid = resolve_project_id(settings, project_id)
        await require_editable(client, pid)
        return client, pid

    @server.tool(
        name="c4_create_element",
        description="Create a C4 element (system/container/component/endpoint/channel/code). "
        "Idempotent by name within parent. For ER tables under a DB container pass columns[]. "
        "A broker topic or queue is kind='channel' under its broker container — name it after "
        "the topic and give it protocol, schemaFormat and the keySchema / valueSchema / "
        "headersSchema contracts instead of the endpoint's method / request / response. "
        "Requires edit access.",
    )
    async def c4_create_element(
        ctx: Context,
        kind: ElementKind,
        name: str,
        projectId: ProjectId = None,
        description: str | None = None,
        technology: str | None = None,
        external: bool | None = None,
        systemId: str | None = None,
        containerId: str | None = None,
        componentId: str | None = None,
        method: str | None = None,
        endpoint: str | None = None,
        headers: str | None = None,
        request: str | None = None,
        response: str | None = None,
        protocol: ChannelProtocol | None = None,
        schemaFormat: ChannelSchemaFormat | None = None,
        keySchema: KeySchema = None,
        valueSchema: ValueSchema = None,
        headersSchema: HeadersSchema = None,
        compatibility: ChannelCompatibility | None = None,
        columns: list[TableColumn] | None = None,
        tags: Tags = None,
        group: Group = None,
    ) -> str:
        client, pid = await editable(ctx, projectId)
        body = compact(
            kind=kind,
            name=name,
            description=description,
            technology=technology,
            external=external,
            systemId=systemId,
            containerId=containerId,
            componentId=componentId,
            method=method,
            endpoint=endpoint,
            headers=headers,
            request=request,
            response=response,
            protocol=protocol,
            schemaFormat=schemaFormat,
            keySchema=keySchema,
            valueSchema=valueSchema,
            headersSchema=headersSchema,
            compatibility=compatibility,
            columns=_dump(columns),
            tags=tags,
            group=group,
        )
        return as_text(await client.post(f"/api/projects/{pid}/elements", body=body))

    @server.tool(
        name="c4_update_element",
        description="Patch fields on an existing C4 element. Pass columns[] to set ER table "
        "schema, or the channel fields (protocol / schemaFormat / keySchema / valueSchema / "
        "headersSchema / compatibility) to edit a broker topic's contract. Requires edit access.",
    )
    async def c4_update_element(
        ctx: Context,
        ownerType: OwnerType,
        ownerId: str,
        projectId: ProjectId = None,
        name: str | None = None,
        description: str | None = None,
        technology: str | None = None,
        url: str | None = None,
        external: bool | None = None,
        method: str | None = None,
        endpoint: str | None = None,
        headers: str | None = None,
        request: str | None = None,
        response: str | None = None,
        protocol: ChannelProtocol | None = None,
        schemaFormat: ChannelSchemaFormat | None = None,
        keySchema: KeySchema = None,
        valueSchema: ValueSchema = None,
        headersSchema: HeadersSchema = None,
        compatibility: ChannelCompatibility | None = None,
        kind: str | None = None,
        columns: list[TableColumn] | None = None,
        tags: Tags = None,
        group: Group = None,
    ) -> str:
        client, pid = await editable(ctx, projectId)
        patch = compact(
            name=name,
            description=description,
            technology=technology,
            url=url,
            external=external,
            method=method,
            endpoint=endpoint,
            headers=headers,
            request=request,
            response=response,
            protocol=protocol,
            schemaFormat=schemaFormat,
            keySchema=keySchema,
            valueSchema=valueSchema,
            headersSchema=headersSchema,
            compatibility=compatibility,
            kind=kind,
            columns=_dump(columns),
            tags=tags,
            group=group,
        )
        return as_text(
            await client.patch(f"/api/projects/{pid}/elements/{ownerType}/{ownerId}", body=patch)
        )

    @server.tool(
        name="c4_delete_element",
        description="Delete a C4 element. Fails if it has children unless cascade=true. "
        "Requires edit access.",
    )
    async def c4_delete_element(
        ctx: Context,
        ownerType: OwnerType,
        ownerId: str,
        projectId: ProjectId = None,
        cascade: bool | None = None,
    ) -> str:
        client, pid = await editable(ctx, projectId)
        return as_text(
            await client.delete(
                f"/api/projects/{pid}/elements/{ownerType}/{ownerId}",
                query={"cascade": "1"} if cascade else None,
            )
        )

    @server.tool(
        name="c4_upsert_connection",
        description="Create or update a connection from sourceId → targetId on the source "
        "element. For an edge to a broker, channelRole says which way the source is using it "
        "— produce or consume; a service doing both needs one connection per direction. "
        "Requires edit access.",
    )
    async def c4_upsert_connection(
        ctx: Context,
        sourceId: str,
        targetId: str,
        projectId: ProjectId = None,
        sourceType: OwnerType | None = None,
        label: str | None = None,
        technology: str | None = None,
        description: str | None = None,
        bidirectional: bool | None = None,
        relatedComponentIds: list[str] | None = None,
        pathType: PathType | None = None,
        channelRole: ChannelRole | None = None,
    ) -> str:
        client, pid = await editable(ctx, projectId)
        body = compact(
            sourceId=sourceId,
            targetId=targetId,
            sourceType=sourceType,
            label=label,
            technology=technology,
            description=description,
            bidirectional=bidirectional,
            relatedComponentIds=relatedComponentIds,
            pathType=pathType,
            channelRole=channelRole,
        )
        return as_text(await client.post(f"/api/projects/{pid}/connections", body=body))

    @server.tool(
        name="c4_delete_connection",
        description="Delete a connection sourceId → targetId. Requires edit access.",
    )
    async def c4_delete_connection(
        ctx: Context,
        sourceId: str,
        targetId: str,
        projectId: ProjectId = None,
        sourceType: OwnerType | None = None,
    ) -> str:
        client, pid = await editable(ctx, projectId)
        body = compact(sourceId=sourceId, targetId=targetId, sourceType=sourceType)
        return as_text(await client.delete(f"/api/projects/{pid}/connections", body=body))

    @server.tool(
        name="c4_upsert_doc",
        description="Create or update markdown documentation on an element and attach it to the "
        "entity (documentationId / documentations) so the canvas docs badge appears. Pass docId "
        "to update; omit to create. Requires edit access.",
    )
    async def c4_upsert_doc(
        ctx: Context,
        ownerType: OwnerType,
        ownerId: str,
        markdown: str,
        projectId: ProjectId = None,
        title: str | None = None,
        docId: str | None = None,
    ) -> str:
        client, pid = await editable(ctx, projectId)
        if docId:
            data = await client.put(
                f"/api/projects/{pid}/docs/{docId}",
                body=compact(title=title, markdown=markdown, ownerType=ownerType, ownerId=ownerId),
            )
            extra = data if isinstance(data, dict) else {}
            return as_text({"ok": True, "created": False, **extra})
        data = await client.post(
            f"/api/projects/{pid}/docs",
            body={
                "ownerType": ownerType,
                "ownerId": ownerId,
                "title": title or "Documentation",
                "markdown": markdown,
            },
        )
        return as_text({"ok": True, "created": True, **(data if isinstance(data, dict) else {})})

    @server.tool(
        name="c4_delete_doc",
        description="Delete a documentation file. Requires edit access.",
    )
    async def c4_delete_doc(ctx: Context, docId: str, projectId: ProjectId = None) -> str:
        client, pid = await editable(ctx, projectId)
        return as_text(await client.delete(f"/api/projects/{pid}/docs/{docId}"))

    @server.tool(
        name="c4_upsert_sequence",
        description="Create or update a PlantUML sequence diagram on a container or component. "
        "Requires edit access.",
    )
    async def c4_upsert_sequence(
        ctx: Context,
        ownerType: SequenceOwnerType,
        ownerId: str,
        plantUmlSource: str,
        projectId: ProjectId = None,
        name: str | None = None,
        diagramId: str | None = None,
    ) -> str:
        client, pid = await editable(ctx, projectId)
        body = compact(
            ownerType=ownerType,
            ownerId=ownerId,
            name=name,
            plantUmlSource=plantUmlSource,
            diagramId=diagramId,
        )
        return as_text(await client.post(f"/api/projects/{pid}/sequences", body=body))

    @server.tool(
        name="c4_delete_sequence",
        description="Delete a sequence diagram by id. Requires edit access.",
    )
    async def c4_delete_sequence(ctx: Context, diagramId: str, projectId: ProjectId = None) -> str:
        client, pid = await editable(ctx, projectId)
        return as_text(await client.delete(f"/api/projects/{pid}/sequences/{diagramId}"))

    @server.tool(
        name="c4_upsert_data_flow",
        description="Create or update a project-level Magic flow (from→to steps). Consecutive "
        "steps sharing parallelGroupId play as one stage: branchKind parallel = async/fan-out "
        "(AND), alternative = exclusive choice (OR). Pass flowId to update; omit to create "
        "(idempotent by name). Omitted fields on update are preserved. For a single hop prefer "
        "c4_upsert_data_flow_step. Optional documentationIds / sequenceIds attach existing docs "
        "and PlantUML diagrams. Requires edit access.",
    )
    async def c4_upsert_data_flow(
        ctx: Context,
        projectId: ProjectId = None,
        name: str | None = None,
        description: str | None = None,
        flowId: str | None = None,
        steps: list[FlowStep] | None = None,
        documentationIds: list[str] | None = None,
        sequenceIds: list[str] | None = None,
    ) -> str:
        if not flowId and not name:
            raise ToolError("name or flowId required")
        client, pid = await editable(ctx, projectId)
        body = compact(
            flowId=flowId,
            name=name,
            description=description,
            steps=_dump(steps),
            documentationIds=documentationIds,
            sequenceIds=sequenceIds,
        )
        return as_text(await client.post(f"/api/projects/{pid}/data-flows", body=body))

    @server.tool(
        name="c4_delete_data_flow",
        description="Delete a Magic flow by id. Requires edit access.",
    )
    async def c4_delete_data_flow(ctx: Context, flowId: str, projectId: ProjectId = None) -> str:
        client, pid = await editable(ctx, projectId)
        return as_text(await client.delete(f"/api/projects/{pid}/data-flows/{flowId}"))

    @server.tool(
        name="c4_upsert_data_flow_step",
        description="Add or patch one hop on a Magic flow. Pass stepId to update (omitted fields "
        "are preserved). Omit stepId to append (from_ + to required). index is 0-based "
        "insert/move. Requires edit access.",
    )
    async def c4_upsert_data_flow_step(
        ctx: Context,
        flowId: str,
        projectId: ProjectId = None,
        stepId: str | None = None,
        index: int | None = None,
        name: str | None = None,
        description: str | None = None,
        # `from` is a Python keyword and this SDK derives the wire name from the
        # signature, so the flat tool spells it `from_`. Nested FlowStep objects
        # still use `from` — that path goes through a pydantic alias.
        from_: FlowParticipant | None = None,
        to: FlowParticipant | None = None,
        endpointIds: list[str] | None = None,
        channelIds: list[str] | None = None,
        connections: list[ConnectionRef] | None = None,
        parallelGroupId: str | None = None,
        branchKind: BranchKind | None = None,
    ) -> str:
        client, pid = await editable(ctx, projectId)
        body = compact(
            stepId=stepId,
            index=index,
            name=name,
            description=description,
            to=_dump(to),
            endpointIds=endpointIds,
            channelIds=channelIds,
            connections=_dump(connections),
            parallelGroupId=parallelGroupId,
            branchKind=branchKind,
        )
        # The API itself expects `from`, whatever the tool parameter is called.
        if from_ is not None:
            body["from"] = _dump(from_)
        return as_text(
            await client.post(f"/api/projects/{pid}/data-flows/{flowId}/steps", body=body)
        )

    @server.tool(
        name="c4_delete_data_flow_step",
        description="Delete one hop from a Magic flow. Requires edit access.",
    )
    async def c4_delete_data_flow_step(
        ctx: Context, flowId: str, stepId: str, projectId: ProjectId = None
    ) -> str:
        client, pid = await editable(ctx, projectId)
        return as_text(
            await client.delete(f"/api/projects/{pid}/data-flows/{flowId}/steps/{stepId}")
        )

    @server.tool(
        name="c4_report_progress",
        description=(
            "Report what you just finished on a change set. Call this after each "
            "meaningful piece of work, not once at the end.\n\n"
            "Pass `criterionId` (an `ac_...` id from the implementation bundle) when the "
            "work proves that acceptance criterion — the criterion is then marked done and "
            "your entry becomes the evidence for it. Put the commit sha, PR url or test "
            "name in `ref`.\n\n"
            "Omit `criterionId` for general progress. The change set moves to "
            "`implementing` on the first report by itself; you do not need to set that."
        ),
    )
    async def c4_report_progress(
        ctx: Context,
        changeSetId: str,
        summary: str,
        criterionId: str | None = None,
        ref: str | None = None,
        projectId: ProjectId = None,
    ) -> str:
        if not changeSetId:
            raise ToolError("changeSetId is required")
        if not summary:
            raise ToolError("summary is required")
        client, pid = await editable(ctx, projectId)
        return as_text(
            await client.post(
                f"/api/projects/{pid}/change-sets/{changeSetId}/progress",
                body=compact(summary=summary, criterionId=criterionId, ref=ref),
            )
        )

    @server.tool(
        name="c4_set_change_set_status",
        description=(
            "Move a change set to `ready`, `implementing` or `done`. Reporting progress "
            "already flips it to `implementing`, so in practice you call this to mark "
            "`done` once every acceptance criterion has evidence."
        ),
    )
    async def c4_set_change_set_status(
        ctx: Context, changeSetId: str, status: str, projectId: ProjectId = None
    ) -> str:
        if not changeSetId:
            raise ToolError("changeSetId is required")
        allowed = {"draft", "ready", "implementing", "done"}
        if status not in allowed:
            raise ToolError(f"status must be one of {sorted(allowed)}")
        client, pid = await editable(ctx, projectId)
        return as_text(
            await client.patch(
                f"/api/projects/{pid}/change-sets/{changeSetId}",
                body={"status": status},
            )
        )
