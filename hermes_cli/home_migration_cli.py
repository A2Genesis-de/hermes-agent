from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from hermes_cli.branding import CLI_COMMAND, ENV_PREFIX, INSTALL_DIR_NAME, LEGACY_CLI_COMMAND
from hermes_cli.home_migration import HomeMigration, Layout, install_inside_legacy_home, is_pending
from hermes_cli.home_migration_system import HostSystem
from hermes_constants import unset_env


def _migration(user_home: Path | None = None) -> HomeMigration:
    home = user_home or Path.home()
    return HomeMigration(Layout(home), HostSystem(home))


def cmd_migrate_home(args: Any) -> int:
    migration = _migration()
    dry_run = bool(getattr(args, "dry_run", False))
    if getattr(args, "rollback", False):
        return migration.rollback(dry_run=dry_run)
    return migration.migrate(dry_run=dry_run)


def _relaunch_update(layout: Layout) -> None:
    launchers = layout.home / INSTALL_DIR_NAME / ".hermes" / "bin"
    for name in (CLI_COMMAND, LEGACY_CLI_COMMAND):
        launcher = launchers / name
        if launcher.is_file():
            env = dict(os.environ)
            unset_env(env, "HOME")
            env[ENV_PREFIX + "HOME"] = str(layout.home)
            os.execve(launcher, [str(launcher), *sys.argv[1:]], env)


def migrate_before_update(project_root: Path, *, gateway_mode: bool) -> None:
    if gateway_mode or not is_pending() or not install_inside_legacy_home(project_root):
        return
    migration = _migration()
    print(f"Renaming the install to {CLI_COMMAND} before updating (`{CLI_COMMAND} migrate --dry-run` shows the plan).")
    if migration.migrate(dry_run=False) != 0:
        print(f"The rename did not run; updating in place. Run `{CLI_COMMAND} migrate` later.", file=sys.stderr)
        return
    _relaunch_update(migration.layout)
