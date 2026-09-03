"""Shapes the tools accept, mirroring the zod schemas of the Node server."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

OwnerType = Literal["system", "container", "component", "code"]
ElementKind = Literal["system", "container", "component", "endpoint", "channel", "code"]
SequenceOwnerType = Literal["container", "component"]
PathType = Literal["bezier", "straight", "step"]
BranchKind = Literal["parallel", "alternative"]

# Broker channels — a topic/queue is not a request/response endpoint, so it
# carries its own contract: key, value and headers schemas instead of
# request/response. The Node server normalises a few aliases ("json",
# "rabbitmq", …); these literals are the spellings it settles on.
ChannelProtocol = Literal["kafka", "amqp", "sqs", "nats", "redis-stream", "mqtt"]
ChannelSchemaFormat = Literal["avro", "json-schema", "protobuf", "cloudevents"]
ChannelCompatibility = Literal["backward", "forward", "full", "none"]
ChannelRole = Literal["produce", "consume"]

CHANNEL_SCHEMA_HELP = (
    "Tagged text: a '@format <fmt>' line, an optional '@name <Name>' line, "
    "then a blank line and the schema source."
)

KeySchema = Annotated[
    str | None,
    Field(default=None, description=f"channel: message key schema. {CHANNEL_SCHEMA_HELP}"),
]

ValueSchema = Annotated[
    str | None,
    Field(default=None, description=f"channel: message payload schema. {CHANNEL_SCHEMA_HELP}"),
]

HeadersSchema = Annotated[
    str | None,
    Field(default=None, description=f"channel: message headers schema. {CHANNEL_SCHEMA_HELP}"),
]

ProjectId = Annotated[
    str | None, Field(default=None, description="Project id; defaults to C4_DEFAULT_PROJECT_ID")
]

Tags = Annotated[
    list[str] | None,
    Field(default=None, max_length=3, description="Up to 3 labels; reused across the project"),
]

Group = Annotated[
    str | None,
    Field(
        default=None,
        description="Visual boundary name; siblings sharing a group are drawn in one box",
    ),
]


class TableColumn(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1)
    dataType: str | None = None
    primaryKey: bool | None = None
    nullable: bool | None = None


class FlowParticipant(BaseModel):
    id: str
    type: OwnerType


class ConnectionRef(BaseModel):
    sourceId: str
    targetId: str


class FlowStep(BaseModel):
    id: str | None = None
    name: str | None = None
    description: str | None = None
    from_: FlowParticipant = Field(alias="from")
    to: FlowParticipant
    endpointIds: list[str] | None = None
    channelIds: list[str] | None = None
    connections: list[ConnectionRef] | None = None
    parallelGroupId: str | None = None
    branchKind: BranchKind | None = Field(
        default=None,
        description="parallel = AND / fan-out (default); alternative = exclusive OR",
    )

    model_config = {"populate_by_name": True}
