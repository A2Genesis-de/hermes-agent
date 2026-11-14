# A2Assistant CLI Reference

Live sources when anything looks stale: `a2assistant --help`, `a2assistant <command> --help`,
https://hermes-agent.nousresearch.com/docs/reference/cli-commands

### Global Flags

```
hermes [flags] [command]        (no subcommand = interactive chat)

  --version, -V             Show version
  -z, --oneshot PROMPT      One-shot: print ONLY the final response (for scripts/pipes)
  -m MODEL  --provider P    Model/provider override for this invocation
  -t, --toolsets LIST       Comma-separated toolsets for this invocation
  --resume, -r SESSION      Resume session by ID or title
  --continue, -c [NAME]     Resume by name, or most recent session
  --worktree, -w            Isolated git worktree mode (parallel agents)
  --skills, -s SKILL        Preload skills (comma-separate or repeat)
  --profile, -p NAME        Use a named profile
  --yolo                    Skip dangerous command approval
  --tui / --cli             Force the Ink TUI / classic REPL
  --ignore-rules            Skip AGENTS.md/SOUL.md/memory/skill injection
  --safe-mode               Disable ALL customizations (troubleshooting)
  --pass-session-id         Include session ID in system prompt
```

### Chat

```
a2assistant chat [flags]
  -q, --query TEXT          Single query, non-interactive
  --image PATH              Attach a local image to a single query
  -Q, --quiet               Suppress banner, spinner, tool previews
  --checkpoints             Enable filesystem checkpoints (/rollback)
  --max-turns N             Cap tool-calling iterations
  --source TAG              Session source tag (default: cli)
```
(plus the global flags above)

### Configuration

```
a2assistant setup [section]      Wizard (model|tts|terminal|gateway|tools|agent)
a2assistant model                Interactive model/provider picker
a2assistant fallback [add|remove|list]  Fallback provider chain
a2assistant config [show|edit|get|set|unset|path|env-path|check|migrate]
a2assistant login / logout       OAuth sign-in / clear stored auth
a2assistant doctor [--fix]       Check dependencies and config
a2assistant status [--full]      Component summary (--full: every section)
```

### Tools & Skills

```
a2assistant tools [list|enable NAME|disable NAME]   Per-platform toolsets (curses UI with no args)

a2assistant skills list|browse|search QUERY|inspect ID
a2assistant skills install ID    Hub identifier OR a direct https://…/SKILL.md URL
a2assistant skills config        Enable/disable skills per platform
a2assistant skills check|update|uninstall|publish PATH
a2assistant skills tap add REPO  Add a GitHub repo as a skill source
a2assistant bundles              Skill bundles (one /<name> alias loads several skills)
```

### MCP Servers

```
a2assistant mcp add NAME (--url or --command) | remove | list | test NAME
a2assistant mcp catalog | install NAME     Curated catalog install
a2assistant mcp configure NAME             Toggle tool selection
hermes mcp-serve                      Run A2Assistant as an MCP server (mcp-serve plugin)
```
Details (transport, tool discovery, catalog): `references/native-mcp.md`.

### Gateway (Messaging Platforms)

```
a2assistant gateway run|install|start|stop|restart|status|setup
```

Platforms: Telegram, API Server, Webhooks. Open WebUI connects via the API Server adapter. The Telegram adapter ships under `plugins/platforms/telegram/`.
Docs: https://hermes-agent.nousresearch.com/docs/user-guide/messaging/

### Sessions

```
a2assistant sessions list|browse|rename ID TITLE|delete ID|export OUT|prune|stats
```

### Cron / Webhooks

```
a2assistant cron list|create SCHED|edit ID|pause|resume|run ID|remove|status
    Schedules: '30m', 'every 2h', '0 9 * * *', ISO timestamp
a2assistant webhook subscribe NAME|list|remove NAME|test NAME
```
Webhook payloads/routes: `references/webhooks.md`.

### Profiles

```
a2assistant profile list|create NAME (--clone|--clone-all|--clone-from)|use|show|delete
a2assistant profile rename A B | alias NAME | export NAME | import FILE
a2assistant profile migrate-identity A B   Retry a completed rename's session/routing identity migration
```

### Credentials & Pools

```
a2assistant auth                 Interactive credential manager
a2assistant auth add [PROVIDER]  Add OAuth or API-key credential (nous, openai-codex, qwen-oauth, …)
a2assistant auth list|remove P IDX|reset PROVIDER|status
```
Multiple credentials per provider form a pool that rotates automatically and skips exhausted keys.

### Other

```
a2assistant desktop / gui        Native desktop app
a2assistant dashboard            Web admin panel + embedded chat (--stop / --status)
a2assistant proxy                OpenAI-compatible local proxy backed by an OAuth provider
a2assistant portal               Quick setup / sign in via Nous Portal
a2assistant kanban <verb>        Multi-agent work-queue board
a2assistant project              Named multi-folder workspaces (see references/projects-and-folders.md)
a2assistant skin list|use|set    Switch/tweak skins (see references/themes.md)
a2assistant pets <verb>          Pet mascots (see references/petdex.md)
a2assistant memory setup|status|off|reset   Memory provider
a2assistant secrets bitwarden|onepassword   External secret stores
a2assistant moa                  Mixture-of-Agents slots
a2assistant hooks / security / backup / import / checkpoints / console
a2assistant logs [-f] [errors]   View agent/error logs
a2assistant send                 One-off message through a gateway platform
a2assistant pairing / plugins / insights / journey / computer-use
a2assistant acp                  ACP server (IDE integration)
a2assistant completion bash|zsh|fish
a2assistant update / uninstall
```

Plugin- and provider-supplied subcommands (e.g. `a2assistant photon setup`) only appear once their plugin is installed/active. Importing from OpenClaw, Claude Code, Codex CLI or Cursor (`a2assistant import-agent <agent>`, plus the older `a2assistant claw migrate|cleanup`) comes from the `agent-importers` plugin; a fresh `a2assistant setup` that finds one of those agents offers to install it.

### Where to Find Things

| Looking for... | Location |
|---|---|
| Config options | `a2assistant config edit` · [Configuration docs](https://hermes-agent.nousresearch.com/docs/user-guide/configuration) |
| Tools / toolsets | `a2assistant tools list` · [Tools reference](https://hermes-agent.nousresearch.com/docs/reference/tools-reference) |
| Skills catalog | `a2assistant skills browse` · [Skills catalog](https://hermes-agent.nousresearch.com/docs/reference/skills-catalog) |
| Provider setup | `a2assistant model` · [Providers guide](https://hermes-agent.nousresearch.com/docs/integrations/providers) |
| Env variables | `a2assistant config env-path` · [Env vars reference](https://hermes-agent.nousresearch.com/docs/reference/environment-variables) |
| Gateway logs | `~/.a2assistant/logs/gateway.log` (or `a2assistant logs`) |
| Sessions | `a2assistant sessions browse` (reads state.db) |
