"""Thin async client for the Viaduct REST API.

Deliberately thin: this server owns no model logic the API does not already
own. Every tool is a shaped call plus, at most, a projection of the answer.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError

logger = logging.getLogger("viaduct_mcp.api")


class C4ApiError(ToolError):
    """An upstream API call that did not return 2xx.

    Subclasses ``ToolError`` so MCP 2.1+ surfaces the status to the client
    instead of swallowing it behind ``Error executing tool <name>``.
    """

    def __init__(self, status: int, method: str, path: str, body: str) -> None:
        self.status = status
        self.method = method
        self.path = path
        self.body = body
        super().__init__(f"C4 API {status} {method} {path}: {body[:400]}")


class C4Client:
    """One client per request in HTTP mode, one per process on stdio."""

    def __init__(self, base_url: str, token: str, timeout: float = 30.0) -> None:
        if not base_url:
            raise RuntimeError("Missing env C4_API_URL")
        if not token:
            raise RuntimeError(
                "No API token. Send 'Authorization: Bearer c4pat_…' with the request "
                "(MCP client headers)."
            )
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout

    async def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: Any | None = None,
        accept: str = "application/json",
    ) -> Any:
        headers = {"Authorization": f"Bearer {self._token}", "Accept": accept}
        content: bytes | None = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            content = json.dumps(body).encode()

        params = {k: str(v) for k, v in (query or {}).items() if v not in (None, "")}
        url = f"{self._base_url}{path}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as http:
                response = await http.request(
                    method,
                    url,
                    params=params or None,
                    headers=headers,
                    content=content,
                )
        except httpx.RequestError as exc:
            logger.error("upstream transport method=%s path=%s err=%s", method, path, exc)
            raise

        text = response.text
        if response.is_error:
            logger.warning(
                "upstream error status=%s method=%s path=%s body=%s",
                response.status_code,
                method,
                path,
                text[:200].replace("\n", " "),
            )
            raise C4ApiError(response.status_code, method, path, text)

        logger.debug("upstream ok status=%s method=%s path=%s", response.status_code, method, path)

        # The context endpoint answers markdown; everything else is JSON.
        if "markdown" in accept or "markdown" in (response.headers.get("content-type") or ""):
            return text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    async def get(self, path: str, **kw: Any) -> Any:
        return await self.request("GET", path, **kw)

    async def post(self, path: str, **kw: Any) -> Any:
        return await self.request("POST", path, **kw)

    async def put(self, path: str, **kw: Any) -> Any:
        return await self.request("PUT", path, **kw)

    async def patch(self, path: str, **kw: Any) -> Any:
        return await self.request("PATCH", path, **kw)

    async def delete(self, path: str, **kw: Any) -> Any:
        return await self.request("DELETE", path, **kw)
