# Container image for the streamable-HTTP transport (remote / Vertex / Bedrock / Cloud Run).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    GA4GH_MCP_TRANSPORT=streamable-http \
    GA4GH_MCP_HOST=0.0.0.0 \
    GA4GH_MCP_PORT=8000 \
    GA4GH_MCP_HTTP_PATH=/mcp \
    GA4GH_MCP_STATELESS_HTTP=true

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

# Run as non-root.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000
# Env vars above select the transport/host/port; override at runtime as needed.
ENTRYPOINT ["ga4gh-mcp"]
