"""Entry point for both transports."""

from __future__ import annotations

import sys

from . import __version__
from .config import load_settings
from .logging_setup import configure_logging, logger
from .server import build_server


def main() -> int:
    try:
        settings = load_settings()
    except RuntimeError as exc:
        print(f"viaduct-mcp: {exc}", file=sys.stderr)
        return 2

    configure_logging(settings.log_level)
    server = build_server(settings)
    logger.info(
        "starting version=%s transport=%s api=%s rate_limit=%s/min",
        __version__,
        settings.transport,
        settings.api_url or "-",
        settings.rate_limit_per_minute or "off",
    )

    if settings.is_http:
        # Stateless: any instance can serve any request, which is what makes
        # this safe to run behind a plain proxy or scale to more than one.
        logger.info("listening host=%s port=%s path=/mcp", settings.host, settings.port)
        server.run(
            transport="streamable-http",
            host=settings.host,
            port=settings.port,
            stateless_http=True,
        )
    else:
        server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
