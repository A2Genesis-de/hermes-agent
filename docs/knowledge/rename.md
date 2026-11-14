# Rename of the internal identifiers (2026-11-14)

A2Assistant no longer uses the Hermes names for anything a user sees or configures. Python packages
and modules (`hermes_cli`, `hermes_constants`, ...), internal TypeScript identifiers, file names in
the repo and the git history keep their names; they are invisible to the user.

## New names

| What | Before | Now |
|---|---|---|
| Home | `~/.hermes` | `~/.a2assistant` (`~/.hermes` stays as a link during the transition) |
| Install (git clone) | `~/.hermes/hermes-agent` | `~/.a2assistant/app` (`hermes-agent` stays as a link) |
| Home override | `HERMES_HOME` | `A2ASSISTANT_HOME` |
| Environment variables | `HERMES_*` | `A2ASSISTANT_*` |
| CLI | `hermes` (alias `a2assistant`) | `a2assistant`; `hermes`, `hermes-acp`, `hermes-agent` are silent `exec` aliases |
| LaunchAgent | `ai.hermes.gateway[-<profile>]` | `de.a2genesis.a2assistant.gateway[-<profile>]` |
| systemd user unit (Linux dev) | `hermes-gateway[-<profile>]` | `a2assistant-gateway[-<profile>]` |
| Desktop bundle id | `com.nousresearch.hermes` | `de.a2genesis.a2assistant` (name stays `A2Assistant`) |
| Desktop data | `~/Library/Application Support/Hermes` | `~/Library/Application Support/A2Assistant` |
| URL scheme | `hermes://` | `a2assistant://` (`hermes://` stays registered) |

One source of truth: the runtime names are defined in `hermes_constants.py` (it must import
without `hermes_cli`, see `tests/pm/test_bootstrap_import_closure.py`) and re-exported by
`hermes_cli/branding.py`; `hermes_cli/service_names.py` builds labels and units and holds the
both-names checks; `apps/shared/src/product-names.mjs` mirrors the names for TypeScript.

## How the code bridges old and new

- **Layout rule.** While only a real `~/.hermes` exists (no `~/.a2assistant`), the code uses the old
  home, the old LaunchAgent label and the old unit names (`hermes_constants.legacy_layout_active`,
  `default_home_in`, `service_names`). That makes the new code safe to run before the migration, so
  an old `hermes update` can install it. The shell scripts use the same rule
  (`scripts/_activation.sh`: `a2assistant_default_home`, `a2assistant_home`), and so does the
  desktop (`apps/shared/src/node/legacy-names.mjs`).
- **Environment.** `hermes_constants.adopt_legacy_env` runs when `hermes_constants` is imported,
  at CLI start, after every `.env` load and in `reload_env`. It adopts `HERMES_X` as
  `A2ASSISTANT_X` when the new name is not set, then mirrors every `A2ASSISTANT_X` back to
  `HERMES_X`. The mirror keeps user plugins outside the repo working (langfuse reads
  `HERMES_LANGFUSE_*`, advanced-delegation reads `HERMES_SESSION_PLATFORM`). Because of the mirror,
  code removes a variable with `unset_env(environ, name)`, which drops both names; a plain
  `pop("A2ASSISTANT_X")` would let a child adopt the stale `HERMES_X`. `env_value(environ, name)`
  reads another process's environment with the fallback. The desktop and the TUI adopt legacy names
  at their entry points (`apps/shared/src/node/adopt-legacy-env.mjs`).
- **Process matching and guards** accept both CLI names and both label prefixes
  (`service_names.is_launchd_label`, `is_gateway_unit`, `CLI_COMMANDS`).

## Migration (`a2assistant migrate`)

Code: `hermes_cli/home_migration.py` (plan, run, rollback), `home_migration_rewrite.py` (path and
`.env` key rewriting), `home_migration_system.py` (launchd/systemd and the desktop check),
`home_migration_cli.py` (command and update hook). Tests: `tests/hermes_cli/test_home_migration.py`.

`a2assistant migrate --dry-run` prints the plan. `a2assistant migrate` then:

1. refuses while the desktop app runs;
2. boots out every `ai.hermes.gateway*` LaunchAgent and moves its plist to
   `~/.a2assistant/backups/a2assistant-migration/services/`;
3. renames `~/.hermes` to `~/.a2assistant` and links `~/.hermes` to it;
4. renames `hermes-agent` to `app` (link kept) and `installs/<key>` to the key of the new path
   (PM keys dependency state by the resolved checkout path);
5. rewrites absolute and `~/` paths in the top-level `*.yaml`/`*.json` files of the home and every
   profile, `cron/*.json`, `plugins/*/` configs, the dependency state (`installs/`), the checkout's
   `.hermes/bin` launchers and `~/.local/bin`; renames `HERMES_*` keys to `A2ASSISTANT_*` in the main
   and profile `.env` files (values untouched, a key that already exists under the new name is left
   alone). Skills, scripts and other user content are not touched;
6. repoints `/Applications/A2Assistant.app` and moves the desktop data directory;
7. publishes the `a2assistant` launchers (`hermes` aliases);
8. runs `a2assistant [-p <profile>] gateway install` for every gateway that had a LaunchAgent, which
   writes and starts `de.a2genesis.a2assistant.gateway*`.

Progress is recorded in `~/.a2assistant/.a2assistant-migration.json` after each step; the log is
`~/.a2assistant/logs/a2assistant-migration.log`. A second run does nothing.

`a2assistant migrate --rollback` (also with `--dry-run`) uses the record: it removes the new
LaunchAgents, reverses the path and key rewrites, restores the desktop link and data, renames
`app` and the home back, restores and starts the old plists, and archives the record under
`~/.hermes/backups/a2assistant-migration/rolled-back-*.json`. The code stays the new one; it runs
on the old layout.

`a2assistant update` runs the migration once by itself before updating when the layout is still the
old one and the install lives inside `~/.hermes` (the deployment shape, not a dev checkout), then
re-executes the update from the new launcher. If the migration refuses (desktop running), the update
continues on the old layout. A gateway-triggered update (`--gateway`) never migrates.

## Handoff from an old install

The MacBook runs the old updater. `hermes update` pulls the new code and finishes through the new
tree (historical takeover), on the old layout. Then either `a2assistant migrate` or the next
`a2assistant update` performs the rename.

## Pitfalls

- macOS ties privacy permissions to the bundle id: after the first start of the renamed desktop app,
  grant Accessibility, Screen Recording, Microphone and Automation again (System Settings → Privacy
  & Security). The bundled Python keeps its signing identifier
  `com.nousresearch.hermes.managed-python`, so grants for it stay.
- Electron's `safeStorage` key is named after the app. Desktop secrets that were saved with keychain
  encryption on (opt-in) must be entered again.
- macOS lists the new LaunchAgent as a new background item; allow it if Login Items blocks it.
- Kept old names on purpose: the toolset `hermes-gateway`, the websocket subprotocol
  `hermes-gateway-ticket.`, the pid-file kind, the connection-id hash seed, the plugin manifest
  namespace `extensions.com.nousresearch.hermes`, and project-local `.hermes/` directories
  (`<project>/.hermes/plugins`, `.hermes/skills`, the checkout's `.hermes/bin`).
