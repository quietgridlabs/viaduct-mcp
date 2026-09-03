"""Tool registration split by whether a tool writes."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from ..config import Settings
from . import read, write


def register_all(server: MCPServer, settings: Settings) -> None:
    read.register(server, settings)
    write.register(server, settings)
