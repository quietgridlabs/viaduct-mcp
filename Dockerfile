# syntax=docker/dockerfile:1
ARG PYTHON_IMAGE=python:3.13-slim

FROM ${PYTHON_IMAGE} AS build
WORKDIR /build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
# Wheels go to a prefix so the runtime image carries no build tooling.
RUN pip install --prefix=/install "."

FROM ${PYTHON_IMAGE} AS runtime
LABEL org.opencontainers.image.title="Viaduct MCP" \
      org.opencontainers.image.vendor="Quiet Grid Labs"

# The server holds no state and needs no write access anywhere.
RUN useradd --system --create-home --uid 10001 viaduct
COPY --from=build /install /usr/local
USER viaduct
WORKDIR /home/viaduct

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    C4_MCP_TRANSPORT=streamable-http \
    C4_MCP_HOST=0.0.0.0 \
    C4_MCP_PORT=8080

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=2).status==200 else 1)"

CMD ["python", "-m", "viaduct_mcp"]
