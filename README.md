# Viaduct MCP

MCP server for [Viaduct](https://c4.quietgridlabs.com) — C4 architecture models,
their documentation, PlantUML sequence diagrams and Magic flows, exposed to
Cursor, Claude Code, Claude Desktop and any other MCP client.

## Auth

The server holds no API credentials. Every request must carry the caller's
token in `Authorization: Bearer …` — the same value you put in the MCP client
config. A shared server token would let one caller act as another.

Get a token from Viaduct: sign in, then the gear next to your username →
**Settings** → **MCP access** → **Create token**.

## Connect a client

Point the agent at the HTTP MCP endpoint and send the token in headers:

```json
{
  "mcpServers": {
    "viaduct": {
      "url": "https://mcp.quietgridlabs.com/mcp",
      "headers": { "Authorization": "Bearer c4pat_..." }
    }
  }
}
```

This is the supported way to use Viaduct from an agent. stdio transport still
exists for process wiring and tests, but MCP clients do not attach HTTP headers
on stdio — without `Authorization` tools will refuse to call the API.

## Run the server

```bash
cp .env.example .env      # set C4_API_URL if needed
docker compose up -d --build
curl localhost:8082/healthz
```

### Deploy note

Bind behind TLS (reverse proxy / load balancer). The process listens on plain
HTTP inside the container (`0.0.0.0:8080`); terminate TLS at the edge and
forward to `/mcp`. Do not expose the container port directly to the public
internet without TLS.

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `C4_API_URL` | — | Required. |
| `C4_MCP_TRANSPORT` | `stdio` | or `streamable-http` |
| `C4_DEFAULT_PROJECT_ID` | — | Lets tools omit `projectId`. |
| `C4_MCP_HOST` / `C4_MCP_PORT` | `0.0.0.0` / `8080` | HTTP only. |
| `C4_MCP_TIMEOUT` | `30` | Seconds per upstream call. |
| `C4_MCP_LOG_LEVEL` | `info` | stderr only (stdout is the MCP wire on stdio). Tool calls and upstream errors are logged as `key=value` lines — readable via `docker compose logs -f`. |
| `C4_MCP_RATE_LIMIT` | `120` (HTTP) / `0` (stdio) | Max `tools/call` per bearer fingerprint per minute. `0` disables. In-memory per process. |

## Tools

29 tools. Every write checks `canEdit` on the project first and refuses before
touching anything.

**Read:** `c4_whoami`, `c4_list_projects`, `c4_project_access`, `c4_project_context`,
`c4_get_element`, `c4_list_docs`, `c4_get_doc`, `c4_list_sequences`,
`c4_get_sequence`, `c4_list_data_flows`, `c4_get_data_flow`, `c4_search`,
`c4_list_change_sets`, `c4_get_implementation_bundle`.

**Write:** `c4_create_element`, `c4_update_element`, `c4_delete_element`,
`c4_upsert_connection`, `c4_delete_connection`, `c4_upsert_doc`, `c4_delete_doc`,
`c4_upsert_sequence`, `c4_delete_sequence`, `c4_upsert_data_flow`,
`c4_delete_data_flow`, `c4_upsert_data_flow_step`, `c4_delete_data_flow_step`,
`c4_report_progress`, `c4_set_change_set_status`.

### Endpoints and channels

Two kinds of contract, and they are not interchangeable. A request/response call
is `kind='endpoint'` — `method`, `endpoint`, `request`, `response`. A broker
topic or queue is `kind='channel'` under its broker container: `protocol`,
`schemaFormat`, `compatibility`, and `keySchema` / `valueSchema` /
`headersSchema` in place of request/response. Each schema is tagged text —
a `@format` line, an optional `@name` line, a blank line, then the source:

```
@format json-schema
@name SubscriptionCdcEvent

{ "type": "object", "properties": { … } }
```

On a connection to a broker, `channelRole` records the direction (`produce` or
`consume`); a service that does both needs one connection each way. A Magic flow
step points at a topic through `channelIds`, the way it points at a call through
`endpointIds`.

### One deliberate difference from the Node server

`c4_upsert_data_flow_step` takes `from_`, not `from`. `from` is a Python keyword
and this SDK derives the wire name from the function signature, so a flat
parameter cannot be called `from`. Nested flow steps inside `c4_upsert_data_flow`
still use `from` — that path goes through a pydantic alias. The API itself is
unchanged either way and always receives `from`.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q
ruff check src tests
```

`tests/test_tools.py` drives the tools the way a client does — by name, with a
JSON payload, against a mocked API — so a schema that disagrees with its handler
fails in CI rather than in someone's editor.

## License

Apache License 2.0. See [LICENSE](./LICENSE).
