# Google Vertex AI (Agent Development Kit)

Vertex AI agents consume remote MCP servers over **streamable HTTP** via the Agent Development
Kit's `MCPToolset` + `StreamableHTTPConnectionParams`. This server defaults to `stateless_http=True`,
which is the right mode for serverless/managed hosting (Cloud Run, Agent Engine).

## 1. Host the server over HTTP

```bash
# locally
ga4gh-mcp --transport streamable-http --host 0.0.0.0 --port 8000 --path /mcp

# or containerized (see the repo Dockerfile) on Cloud Run
gcloud run deploy ga4gh-mcp \
  --image <your-registry>/ga4gh-mcp:latest \
  --port 8000 --allow-unauthenticated
# the MCP endpoint is then https://<cloud-run-url>/mcp
```

The Docker image defaults to `GA4GH_MCP_TRANSPORT=streamable-http` and binds `0.0.0.0:8000`.

## 2. Wire it into an ADK agent

```python
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool import StreamableHTTPConnectionParams

ga4gh_tools = MCPToolset(
    connection_params=StreamableHTTPConnectionParams(
        url="https://<your-cloud-run-url>/mcp",
        # headers={"Authorization": "Bearer <id-token>"},  # if you deploy authenticated
    )
)

agent = LlmAgent(
    model="gemini-2.5-pro",
    name="ga4gh_agent",
    instruction="Use the GA4GH registry tools to find and inspect genomics services.",
    tools=[ga4gh_tools],
)
```

`MCPToolset` auto-discovers all 18 tools from the server at startup and exposes them to the model.

## Verify

```bash
# 1) endpoint is reachable (expect an HTTP response from the MCP endpoint, not connection refused)
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://<your-cloud-run-url>/mcp \
  -H 'Accept: application/json, text/event-stream' -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# 2) tools load in ADK (prints tool names)
python -c "
import asyncio
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool import StreamableHTTPConnectionParams
async def main():
    ts = MCPToolset(connection_params=StreamableHTTPConnectionParams(url='https://<your-cloud-run-url>/mcp'))
    print([t.name for t in await ts.get_tools()])
asyncio.run(main())
"
```

Then run your agent and ask it to *"list DRS services in the GA4GH registry"* — it should call
`list_services`.

Sources: [ADK MCP tools](https://adk.dev/tools-custom/mcp-tools/),
[Use Google ADK and MCP with an external server](https://cloud.google.com/blog/topics/developers-practitioners/use-google-adk-and-mcp-with-an-external-server).
