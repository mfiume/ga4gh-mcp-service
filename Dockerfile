# GA4GH MCP service — HTTP transport container
FROM python:3.12-slim

# uv for fast, reproducible installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src

RUN uv pip install --system --no-cache .

ENV GA4GH_MCP_TRANSPORT=http \
    GA4GH_MCP_HOST=0.0.0.0 \
    GA4GH_MCP_PORT=8080 \
    GA4GH_MCP_LOG_LEVEL=INFO

EXPOSE 8080

# Simple container healthcheck against the built-in /healthz route
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=3).status==200 else 1)"

CMD ["ga4gh-mcp", "serve"]
