# Security Policy

## Supported versions

Security fixes land on the default branch (`main`) of this repository. There is
no long-term support line yet — upgrade by pulling the latest release or image.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security problems.

Email **support@quietgridlabs.com** with:

- a description of the issue and its impact
- steps to reproduce, or a proof of concept if you have one
- affected version / commit if known

We will acknowledge receipt within a few business days and follow up with a
fix or mitigation plan. Please give us a reasonable window before any public
disclosure.

## Scope notes

This server is a thin MCP proxy in front of the Viaduct HTTP API:

- It does **not** store API tokens. Callers must send `Authorization: Bearer …`
  on each request.
- Upstream responses (including error bodies, truncated) may be forwarded to
  the MCP client. Treat the MCP endpoint as trusted-network / TLS-terminated.
- In-memory rate limiting is per process and is not a substitute for edge
  controls.
