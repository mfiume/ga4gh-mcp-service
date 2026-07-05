# Amazon Bedrock (AgentCore)

Amazon Bedrock AgentCore supports MCP over **streamable HTTP**, in two ways:

1. **AgentCore Gateway** — register this server as a remote **MCP server target**; the Gateway
   fronts it as a single secure endpoint for your agents (with OAuth). Best for a hosted server.
2. **AgentCore Runtime** — deploy the server as a container into AgentCore Runtime. Runtime
   recommends **stateless** MCP servers (`stateless_http=True`, which is this server's default) and
   automatically injects an `Mcp-Session-Id` header for session continuity.

## Host the server

```bash
ga4gh-mcp --transport streamable-http --host 0.0.0.0 --port 8000 --path /mcp
# or use the repo Dockerfile (already defaults to streamable-http on 0.0.0.0:8000)
```

## Option 1 — register as a Gateway MCP-server target

Create/patch a gateway target of type MCP server pointing at your endpoint (`.../mcp`). Configure
the authorization provider in AgentCore Identity. Two-legged OAuth (client-credentials) and
three-legged OAuth (authorization-code) are both supported; the Gateway performs the MCP handshake
and indexes the tools via `SynchronizeGatewayTargets`.

```jsonc
// target definition (illustrative shape — set via the AgentCore console / API)
{
  "name": "ga4gh",
  "targetConfiguration": {
    "mcp": { "server": { "endpoint": "https://<your-host>/mcp" } }
  },
  "credentialProviderConfigurations": [
    { "credentialProviderType": "OAUTH", "credentialProvider": { "oauthCredentialProvider": {
        "providerArn": "<agentcore-identity-oauth-provider-arn>" } } }
  ]
}
```

## Option 2 — deploy into AgentCore Runtime

Package the container (repo `Dockerfile`) and deploy to Runtime. Keep `GA4GH_MCP_STATELESS_HTTP=true`
(default). Runtime handles session headers; your agent connects to the Runtime-provided MCP URL.

## Verify

```bash
# endpoint is reachable and speaks MCP
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://<your-host>/mcp \
  -H 'Accept: application/json, text/event-stream' -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

After registering the target, list tools from the Gateway (they appear namespaced by target),
then have your Bedrock agent call `list_services` — e.g. ask it to *"find TES services in the GA4GH
registry."*

Sources:
[AgentCore Gateway](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html),
[MCP server targets](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-MCPservers.html),
[Deploy MCP servers in AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html).
