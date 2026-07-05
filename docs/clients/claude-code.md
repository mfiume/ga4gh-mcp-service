# Claude Code

Claude Code connects over **stdio** (local) or **streamable-http** (remote).

## Add over stdio (recommended)

```bash
# no install, via uvx
claude mcp add ga4gh -- uvx --from git+https://github.com/mfiume/ga4gh-mcp-service ga4gh-mcp

# or from a local checkout
claude mcp add ga4gh -- /abs/path/ga4gh-mcp-service/.venv/bin/ga4gh-mcp
```

Pass auth env vars with `-e` if needed:

```bash
claude mcp add ga4gh -e GA4GH_MCP_AUTH_CONFIG=/abs/path/auth.json -- \
  uvx --from git+https://github.com/mfiume/ga4gh-mcp-service ga4gh-mcp
```

## Add a remote (streamable-http) server

Start it somewhere reachable:

```bash
ga4gh-mcp --transport streamable-http --host 0.0.0.0 --port 8000 --path /mcp
```

Then:

```bash
claude mcp add --transport http ga4gh https://your-host:8000/mcp
```

## Equivalent `.mcp.json` (project-scoped, checked into a repo)

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

## Verify

```bash
claude mcp list                 # ga4gh should show "connected"
claude mcp get ga4gh            # shows the configured command/transport
```

In a session, run `/mcp` to inspect the 18 tools, or ask Claude:
*"Use the ga4gh tools to check the health of the Dockstore TRS service."*
