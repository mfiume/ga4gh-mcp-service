# Amazon Bedrock (AgentCore / Strands)

Bedrock agents consume MCP tools over **streamable HTTP**. Host the server (HTTP
transport) somewhere the agent runtime can reach it, then register the `/mcp`
endpoint as an MCP tool source.

### 1. Run / deploy the server (HTTP)

```bash
GA4GH_MCP_TRANSPORT=http GA4GH_MCP_HOST=0.0.0.0 GA4GH_MCP_PORT=8080 uv run ga4gh-mcp serve
```

Container deploy (ECS/Fargate/App Runner) using `../../Dockerfile`:

```bash
docker build -t ga4gh-mcp .
# push to ECR and run with env GA4GH_MCP_TRANSPORT=http, port 8080 exposed.
```

### 2. Connect from a Strands / Bedrock agent

```python
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession
from strands import Agent
from strands.tools.mcp import MCPClient

ga4gh = MCPClient(lambda: streamablehttp_client("https://YOUR-HOST/mcp"))

with ga4gh:
    agent = Agent(
        model="anthropic.claude-sonnet-4-5-v1:0",   # a Bedrock model id
        tools=ga4gh.list_tools_sync(),
        system_prompt="Use the GA4GH tools to discover and access genomics services.",
    )
    print(agent("List the DRS services in the GA4GH registry"))
```

For **Bedrock AgentCore Gateway**, register the same `https://YOUR-HOST/mcp`
endpoint as an MCP target; AgentCore imports the tool schemas automatically.

### 3. Verify

```bash
curl -s https://YOUR-HOST/healthz
uv run python scripts/smoke.py --http-only
```
