# cc-config

Unified viewer for all Claude Code configuration. Reads every config file across all levels and presents them organized by **concept** rather than by file, so you can see at a glance how MCP servers, hooks, permissions, and everything else are set up across your environment.

## The problem

Claude Code configuration is spread across many files at multiple levels:

- **Managed** (enterprise): `/Library/Application Support/ClaudeCode/managed-settings.json`
- **User global**: `~/.claude/settings.json`, `~/.claude/CLAUDE.md`, `~/.claude/commands/`, etc.
- **Project shared**: `.claude/settings.json`, `CLAUDE.md`, `.mcp.json`
- **Project local**: `.claude/settings.local.json`, `CLAUDE.local.md`

When something isn't working, you end up grepping across a dozen files to figure out where a setting lives and what's overriding what.

## Install

```bash
git clone git@github.com:pbenmoser4/cc-config.git
cd cc-config
pip install -e .
```

## Usage

```
cc-config [CONCEPT] [OPTIONS]
```

### Show everything

```bash
cc-config
```

### Filter to a single concept

```bash
cc-config mcp           # MCP servers
cc-config hooks         # Hooks
cc-config permissions   # Permission rules
cc-config model         # Model settings
cc-config commands      # Custom slash commands
cc-config instructions  # CLAUDE.md files
cc-config plugins       # Installed plugins & blocklist
cc-config env           # Environment variables
cc-config skills        # Skills
cc-config agents        # Agents
cc-config rules         # Rules
```

### Options

```
-p, --project DIR    Project directory (default: cwd)
-j, --json           JSON output
-l, --level LEVEL    Filter to one level: managed, user, project-shared, project-local
--files              Show config file inventory (which files exist/missing)
-v, --verbose        Don't truncate long paths
--no-color           Disable colors
```

### Examples

```bash
# What MCP servers are configured for a specific project?
cc-config mcp -p ~/dev/myproject

# What permissions come from the project level only?
cc-config permissions -l project-local

# Which config files exist (and which are missing)?
cc-config --files

# Machine-readable output
cc-config --json | jq '.concepts.mcp'
```

## Sample output

```
╔══════════════════════════════════════════════════╗
║  cc-config · ~/dev/myproject                     ║
╚══════════════════════════════════════════════════╝
  Sources:  ● managed  ● user-global  ● project-shared  ● project-local

── MCP Servers ───────────────────────────────────────────────

  postgres                                              ● project-shared
    command:  npx
    args:     ["-y", "@anthropic/mcp-postgres", "postgresql://localhost/mydb"]

  github                                                ● user-global
    command:  ~/bin/github-mcp-server
    env:      GITHUB_TOKEN=ghp_***

── Permissions ───────────────────────────────────────────────

  allow
    mcp__github__*                                      ● user-global
    WebSearch                                           ● project-local

  deny
    (none)
```

Each entry is color-tagged with its source level so you can immediately see where it's defined and what might be overriding what.

## Removing configuration

```
cc-config rm <concept> <name> [OPTIONS]
```

Deep-cleans a configuration item by removing its definition **and** all related references across every config level. Always shows a plan and asks for confirmation before making changes.

### Examples

```bash
# Remove an MCP server (also cleans up permissions, CLAUDE.md sections, hooks)
cc-config rm mcp github

# Preview what would be removed without changing anything
cc-config rm mcp github --dry-run

# Remove a custom command
cc-config rm commands backlog

# Remove a permission rule
cc-config rm permissions WebSearch

# Remove an installed plugin (also deletes cached files)
cc-config rm plugins rust-analyzer-lsp@claude-plugins-official

# Remove a hook event
cc-config rm hooks PostToolUse

# Remove an environment variable
cc-config rm env MY_VAR

# Skip confirmation
cc-config rm mcp old-server -y
```

### Supported concepts

`model`, `mcp`, `hooks`, `permissions`, `commands`, `skills`, `agents`, `rules`, `env`, `plugins`

### Options

```
--dry-run    Show what would be removed without making changes
-y, --yes    Skip confirmation prompt
-p, --project DIR    Project directory (default: cwd)
--no-color   Disable colors
```

> **Non-TTY environments:** When stdin is not a TTY (e.g., running from Claude Code's Bash tool or a script), the confirmation prompt is skipped automatically — equivalent to `--yes`.

### Sample removal plan

```
$ cc-config rm mcp github --dry-run

  cc-config rm mcp github

  Primary:
    ✕ Remove 'github' from mcpServers  ● user-global
      ~/.claude/settings.json

  Related references:
    ~ Remove 1 permission rule(s) matching mcp__github__*  ● user-global
      ~/.claude/settings.json
    ~ Remove 'github' section from CLAUDE.md (marker-bounded)  ● user-global
      ~/.claude/CLAUDE.md
    ~ Remove hook 'PostToolUse' (references github binary)  ● user-global
      ~/.claude/settings.json

  4 action(s): 1 primary, 3 related reference(s)

  --dry-run: no changes made.
```

### What deep clean finds

When removing an MCP server, for example, `cc-config rm` finds and removes:
- The server definition in `mcpServers` (from settings.json and .mcp.json at all levels)
- Permission rules matching `mcp__<name>__*`
- CLAUDE.md sections bounded by `<!-- name:start -->` / `<!-- name:end -->` markers
- Hook events whose commands reference the server's binary
- Entries in `allowedMcpServers` / `deniedMcpServers` lists

## How it works

1. **Discovery** — Finds all config files at all levels for the given project
2. **Parsing** — Reads settings.json, .mcp.json, CLAUDE.md, command front-matter, plugin manifests
3. **Grouping** — Reorganizes entries by concept and applies merge/override rules
4. **Rendering** — Outputs with color-coded source badges

Zero external dependencies. Python 3.10+ stdlib only.

## Claude Code command

The repo includes a `/cc-config` slash command. Copy it to your commands directory or install the tool and it's already set up:

```bash
cp ~/.claude/commands/cc-config.md  # already installed if you followed the setup
```

Then use `/cc-config mcp` from within any Claude Code session.

## Config levels & precedence

Settings merge with this priority (highest wins):

| Priority | Level | Files |
|----------|-------|-------|
| 1 | Managed | `/Library/Application Support/ClaudeCode/managed-settings.json` |
| 2 | Project local | `.claude/settings.local.json` |
| 3 | Project shared | `.claude/settings.json` |
| 4 | User global | `~/.claude/settings.json` |

- **Permissions**: Additive across levels (all allow/deny rules apply)
- **Hooks**: Additive (hooks from all levels fire)
- **MCP servers**: Merged by name (project overrides global for same server name)
- **Model, env**: Override (highest priority wins)
- **CLAUDE.md**: All levels concatenated (all apply)

## License

MIT
