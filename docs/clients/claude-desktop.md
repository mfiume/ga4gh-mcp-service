# Claude Desktop

Claude Desktop speaks MCP over **stdio**. Add this server to
`claude_desktop_config.json`:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

## Option A — no install (uvx, recommended)

```json
{
  "mcpServers": {
    "ga4gh": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/mfiume/ga4gh-mcp-service", "ga4gh-mcp"]
    }
  }
}
```

## Option B — local checkout

```json
{
  "mcpServers": {
    "ga4gh": {
      "command": "/absolute/path/to/ga4gh-mcp-service/.venv/bin/ga4gh-mcp",
      "args": [],
      "env": {
        "GA4GH_MCP_AUTH_CONFIG": "/absolute/path/to/auth.json"
      }
    }
  }
}
```

`env` is optional — add auth env vars (see [`../auth.md`](../auth.md)) only if you need to reach
protected services.

## Verify

1. Confirm the command works before wiring it in:
   ```bash
   uvx --from git+https://github.com/mfiume/ga4gh-mcp-service ga4gh-mcp --list-tools
   # -> prints 18 tools as JSON
   ```
2. Fully restart Claude Desktop (quit, not just close the window).
3. In a chat, open the tools (plug icon) — you should see `ga4gh` with 18 tools.
4. Ask: *"List the DRS services in the GA4GH registry."* — Claude calls `list_services`.
