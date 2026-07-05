# Google Vertex AI (Agent Development Kit)

Vertex AI agents consume MCP tools over **streamable HTTP** via the ADK's
`MCPToolset`. Run the server with the HTTP transport and point the toolset at
`/mcp`.

### 1. Run the server (HTTP)

Locally:

```bash
GA4GH_MCP_TRANSPORT=http GA4GH_MCP_HOST=0.0.0.0 GA4GH_MCP_PORT=8080 uv run ga4gh-mcp serve
```

Or containerized (see `../../Dockerfile`) — e.g. on Cloud Run:

```bash
docker build -t gcr.io/PROJECT/ga4gh-mcp .
docker push gcr.io/PROJECT/ga4gh-mcp
gcloud run deploy ga4gh-mcp --image gcr.io/PROJECT/ga4gh-mcp \
  --set-env-vars GA4GH_MCP_TRANSPORT=http,GA4GH_MCP_HOST=0.0.0.0,GA4GH_MCP_PORT=8080 \
  --port 8080 --allow-unauthenticated
```

### 2. Wire it into an ADK agent

```python
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from mcp.client.streamable_http import streamablehttp_client

ga4gh_tools = MCPToolset(
    connection_params=streamablehttp_client("https://YOUR-CLOUD-RUN-URL/mcp"),
)

agent = LlmAgent(
    model="gemini-2.5-pro",
    name="ga4gh_agent",
    instruction="Use the GA4GH tools to discover and access genomics services.",
    tools=[ga4gh_tools],
)
```

### 3. Verify

```bash
curl -s https://YOUR-URL/healthz          # {"status":"ok",...}
# and a headless MCP handshake from your machine:
GA4GH_MCP_TRANSPORT=http uv run python scripts/smoke.py --http-only
```
