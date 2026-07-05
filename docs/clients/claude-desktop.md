# Claude Desktop

Claude Desktop speaks MCP over **stdio**. Add an entry to its config file:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

### Option A — run from a local checkout (recommended for dev)

```json
{
  "mcpServers": {
    "ga4gh": {
      "command": "uv",
      "args": ["run", "--directory", "/ABSOLUTE/PATH/TO/ga4gh-mcp-service",
               "ga4gh-mcp", "serve", "--transport", "stdio"]
    }
  }
}
```

### Option B — run straight from GitHub with uvx (no clone)

```json
{
  "mcpServers": {
    "ga4gh": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/mfiume/ga4gh-mcp-service",
               "ga4gh-mcp", "serve", "--transport", "stdio"]
    }
  }
}
```

### With a token for a protected service (optional)

```json
{
  "mcpServers": {
    "ga4gh": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/mfiume/ga4gh-mcp-service", "ga4gh-mcp", "serve"],
      "env": {
        "GA4GH_MCP_TRANSPORT": "stdio",
        "GA4GH_MCP_TOKEN_DATA_TERRA_BIO": "eyJhbGciOi..."
      }
    }
  }
}
```

**Verify:** fully quit and reopen Claude Desktop. The GA4GH tools appear under the
🔌 (tools) menu. Ask: _"List GA4GH DRS services in the registry"_ → it should call
`registry_list_services`. Before configuring, confirm the command works headless:

```bash
uv run --directory /ABSOLUTE/PATH/TO/ga4gh-mcp-service ga4gh-mcp tools
```
