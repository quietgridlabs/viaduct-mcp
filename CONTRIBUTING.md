# Contributing

Thanks for helping improve Viaduct MCP.

## Setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

## Checks

Before opening a PR:

```bash
pytest -q
ruff check src tests
```

CI runs the same pair on every push and pull request to `main`.

## Pull requests

- Prefer small, focused changes.
- Use conventional commit subjects when you can (`feat:`, `fix:`, `docs:`,
  `test:`, `chore:`).
- Update the README when behaviour or configuration changes.
- Do not commit secrets, `.env`, or local virtualenvs.

## Security

See [SECURITY.md](./SECURITY.md) for how to report vulnerabilities privately.
