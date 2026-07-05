# Claude Code

Claude Code supports MCP over **stdio** (local) and **HTTP** (remote).

### stdio (local checkout)

```bash
claude mcp add ga4gh -- uv run --directory /ABSOLUTE/PATH/TO/ga4gh-mcp-service ga4gh-mcp serve --transport stdio
```

Or from GitHub with no clone:

```bash
claude mcp add ga4gh -- uvx --from git+https://github.com/mfiume/ga4gh-mcp-service ga4gh-mcp serve --transport stdio
```

Pass a token via env:

```bash
claude mcp add ga4gh --env GA4GH_MCP_TOKEN_DATA_TERRA_BIO=eyJ... -- uvx --from git+https://github.com/mfiume/ga4gh-mcp-service ga4gh-mcp serve
```

### HTTP (connect to a running server)

```bash
# start it (any host):
GA4GH_MCP_TRANSPORT=http GA4GH_MCP_PORT=8080 uv run ga4gh-mcp serve
# register the endpoint:
claude mcp add --transport http ga4gh http://localhost:8080/mcp
```

### Project-scoped config (`.mcp.json` in a repo)

```json
{
  "mcpServers": {
    "ga4gh": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/mfiume/ga4gh-mcp-service", "ga4gh-mcp", "serve", "--transport", "stdio"]
    }
  }
}
```

**Verify:**

```bash
claude mcp list                 # shows "ga4gh"
claude mcp get ga4gh            # shows the config
# in a session:  /mcp           # lists the ga4gh tools
```
