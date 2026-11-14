from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from hermes_cli.home_migration import HomeMigration, Layout, MigrationState, Record
from hermes_cli.home_migration_rewrite import PathMapping, rename_env_file_keys
from hermes_constants import adopt_legacy_env, default_home_in, env_value, unset_env
from pm.environments import install_key_for


@dataclass
class FakeSystem:
    user_home: Path
    running: bool = False
    stopped: list[str] = field(default_factory=list)
    started: list[str] = field(default_factory=list)
    installed: list[tuple[Path, Path, list[str]]] = field(default_factory=list)

    @property
    def agents(self) -> Path:
        return self.user_home / "Library" / "LaunchAgents"

    def desktop_running(self) -> bool:
        return self.running

    def service_files(self, legacy: bool) -> list[Path]:
        prefix = "ai.hermes.gateway" if legacy else "de.a2genesis.a2assistant.gateway"
        return sorted(self.agents.glob(prefix + "*.plist")) if self.agents.is_dir() else []

    def stop_service(self, unit_file: Path) -> None:
        self.stopped.append(unit_file.name)

    def start_service(self, unit_file: Path) -> None:
        self.started.append(unit_file.name)

    def install_gateways(self, launcher: Path, home: Path, profiles: list[str]) -> None:
        self.installed.append((launcher, home, profiles))
        for profile in profiles:
            name = "de.a2genesis.a2assistant.gateway" + (f"-{profile}" if profile else "")
            (self.agents / f"{name}.plist").write_text(f"<plist>{home}</plist>", encoding="utf-8")


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def account(tmp_path: Path):
    user = tmp_path / "user"
    legacy = user / ".hermes"
    real_legacy = Path(os.path.realpath(user)) / ".hermes"
    install = legacy / "hermes-agent"
    _write(install / ".hermes" / "bin" / "hermes", f"#!/bin/sh\nexec {real_legacy}/tools/python -c x\n")
    _write(install / "hermes_cli" / "__init__.py", "")
    old_key = install_key_for(str(real_legacy / "hermes-agent"))
    _write(legacy / "installs" / old_key / "facts.json",
           json.dumps({"environment": f"{real_legacy}/installs/{old_key}/environments/e/venv"}))
    _write(legacy / "installs" / old_key / "environments" / "e" / "venv" / "pyvenv.cfg",
           f"home = {real_legacy}/tools/python-3/bin\nrelocatable = true\n")
    _write(legacy / "config.yaml", f"cwd: {real_legacy}/hermes-agent\nca: {real_legacy}/certs/root.crt\n"
                                  "db: ~/.hermes/data/a2.db\nother: /opt/.hermes-like/keep\n")
    _write(legacy / "cron" / "jobs.json", json.dumps({"jobs": [{"script": f"{real_legacy}/scripts/check.sh"}]}))
    _write(legacy / "profiles" / "buero" / "config.yaml", f"skills: {real_legacy}/profiles/buero/skills\n")
    _write(legacy / ".env", "A2INTELLIGENCE_API_KEY=secret-1\nHERMES_LANGFUSE_PUBLIC_KEY=pk\n"
                            "export HERMES_LANGFUSE_SECRET_KEY='sk'\n")
    _write(legacy / "profiles" / "buero" / ".env", "HERMES_API_TIMEOUT=30\nA2ASSISTANT_YOLO_MODE=1\nHERMES_YOLO_MODE=0\n")
    _write(legacy / "skills" / "note.md", "uses ~/.hermes/skills and $HERMES_HOME\n")
    _write(user / "Library" / "LaunchAgents" / "ai.hermes.gateway.plist", f"<plist>{real_legacy}</plist>")
    _write(user / "Library" / "Application Support" / "Hermes" / "Preferences", "{}")
    _write(user / ".local" / "bin" / "hermes", f"#!/bin/sh\nexec {real_legacy}/hermes-agent/.hermes/bin/hermes \"$@\"\n")
    applications = tmp_path / "Applications"
    applications.mkdir()
    (applications / "A2Assistant.app").symlink_to(f"{real_legacy}/hermes-agent/apps/desktop/release/A2Assistant.app")
    layout = Layout(user, applications=applications)
    system = FakeSystem(user)
    published: list[Path] = []
    migration = HomeMigration(layout, system, log=lambda line: None, publish_launchers=published.append)
    snapshot = {path: path.read_text(encoding="utf-8") for path in user.rglob("*")
                if path.is_file() and not path.is_symlink()}
    return migration, system, published, snapshot, old_key


def _real(path: Path) -> str:
    return os.path.realpath(path)


def test_adopt_legacy_env_prefers_explicit_new_names_and_mirrors_back():
    environ = {"HERMES_HOME": "/old", "HERMES_LANGFUSE_KEY": "k", "A2ASSISTANT_HOME": "/new",
               "A2ASSISTANT_TUI": "1"}
    adopt_legacy_env(environ)
    assert environ["A2ASSISTANT_HOME"] == "/new"
    assert environ["A2ASSISTANT_LANGFUSE_KEY"] == "k"
    assert environ["HERMES_HOME"] == "/new"
    assert environ["HERMES_TUI"] == "1"
    unset_env(environ, "HOME")
    assert "A2ASSISTANT_HOME" not in environ and "HERMES_HOME" not in environ
    assert env_value({"HERMES_X": "legacy"}, "X") == "legacy"
    assert env_value({"HERMES_X": "legacy", "A2ASSISTANT_X": "new"}, "X") == "new"


def test_a_removed_key_takes_its_own_mirror_along(monkeypatch):
    monkeypatch.setenv("A2ASSISTANT_MIRROR_PROBE", "1")
    adopt_legacy_env(os.environ)
    assert os.environ["HERMES_MIRROR_PROBE"] == "1"
    monkeypatch.delenv("A2ASSISTANT_MIRROR_PROBE")
    adopt_legacy_env(os.environ)
    assert "A2ASSISTANT_MIRROR_PROBE" not in os.environ and "HERMES_MIRROR_PROBE" not in os.environ


def test_default_home_keeps_the_legacy_home_until_it_is_migrated(tmp_path: Path):
    assert default_home_in(tmp_path) == tmp_path / ".a2assistant"
    (tmp_path / ".hermes").mkdir()
    assert default_home_in(tmp_path) == tmp_path / ".hermes"
    (tmp_path / ".hermes").rename(tmp_path / ".a2assistant")
    (tmp_path / ".hermes").symlink_to(tmp_path / ".a2assistant")
    assert default_home_in(tmp_path) == tmp_path / ".a2assistant"


def test_path_mapping_respects_name_boundaries():
    mapping = PathMapping([("/u/.hermes/hermes-agent", "/u/.a2assistant/app"), ("/u/.hermes", "/u/.a2assistant")])
    text = "/u/.hermes/hermes-agent/x /u/.hermes/y /u/.hermes-old /u/.hermes"
    moved = mapping.apply(text)
    assert moved == "/u/.a2assistant/app/x /u/.a2assistant/y /u/.hermes-old /u/.a2assistant"
    assert mapping.reversed().apply(moved) == text


def test_env_key_rename_keeps_values_and_existing_new_keys(tmp_path: Path):
    path = _write(tmp_path / ".env", "HERMES_A=1\nexport HERMES_B = 'two'\nA2ASSISTANT_C=3\nHERMES_C=old\nOTHER=x\n")
    assert rename_env_file_keys(path, dry_run=False) == ["A", "B"]
    assert path.read_text(encoding="utf-8") == ("A2ASSISTANT_A=1\nexport A2ASSISTANT_B = 'two'\nA2ASSISTANT_C=3\n"
                                                "HERMES_C=old\nOTHER=x\n")
    assert rename_env_file_keys(path, dry_run=False, reverse_names=["A", "B"]) == ["A", "B"]
    assert path.read_text(encoding="utf-8").startswith("HERMES_A=1\nexport HERMES_B = 'two'\n")


def test_dry_run_changes_nothing(account):
    migration, system, published, snapshot, _ = account
    assert migration.migrate(dry_run=True) == 0
    assert migration.layout.state() is MigrationState.PENDING
    assert not system.stopped and not published
    assert all(path.read_text(encoding="utf-8") == text for path, text in snapshot.items())


def test_refuses_while_the_desktop_app_runs(account):
    migration, system, _, _, _ = account
    system.running = True
    assert migration.migrate(dry_run=False) == 1
    assert migration.layout.state() is MigrationState.PENDING
    assert not system.stopped


def test_migrate_moves_home_rewrites_paths_and_renames_services(account):
    migration, system, published, _, old_key = account
    layout = migration.layout
    assert migration.migrate(dry_run=False) == 0

    home, legacy = layout.home, layout.legacy_home
    real_home = _real(home)
    assert home.is_dir() and not home.is_symlink()
    assert legacy.is_symlink() and _real(legacy) == real_home
    assert (home / "app" / "hermes_cli").is_dir()
    assert (home / "hermes-agent").is_symlink()
    new_key = install_key_for(f"{real_home}/app")
    assert (home / "installs" / new_key / "facts.json").is_file()
    assert not (home / "installs" / old_key).exists()

    config = (home / "config.yaml").read_text(encoding="utf-8")
    assert f"cwd: {real_home}/app\n" in config
    assert f"ca: {real_home}/certs/root.crt" in config
    assert "db: ~/.a2assistant/data/a2.db" in config
    assert "/opt/.hermes-like/keep" in config
    assert f"{real_home}/scripts/check.sh" in (home / "cron" / "jobs.json").read_text(encoding="utf-8")
    assert f"{real_home}/profiles/buero/skills" in (home / "profiles/buero/config.yaml").read_text(encoding="utf-8")
    facts = (home / "installs" / new_key / "facts.json").read_text(encoding="utf-8")
    assert f"{real_home}/installs/{new_key}/environments" in facts
    assert f"home = {real_home}/tools/" in (home / "installs" / new_key / "environments/e/venv/pyvenv.cfg").read_text(
        encoding="utf-8")
    assert f"{real_home}/app/.hermes/bin/hermes" in (layout.local_bin / "hermes").read_text(encoding="utf-8")
    assert (home / "skills" / "note.md").read_text(encoding="utf-8") == "uses ~/.hermes/skills and $HERMES_HOME\n"

    env = (home / ".env").read_text(encoding="utf-8")
    assert env == ("A2INTELLIGENCE_API_KEY=secret-1\nA2ASSISTANT_LANGFUSE_PUBLIC_KEY=pk\n"
                   "export A2ASSISTANT_LANGFUSE_SECRET_KEY='sk'\n")
    profile_env = (home / "profiles/buero/.env").read_text(encoding="utf-8")
    assert profile_env == "A2ASSISTANT_API_TIMEOUT=30\nA2ASSISTANT_YOLO_MODE=1\nHERMES_YOLO_MODE=0\n"

    assert system.stopped == ["ai.hermes.gateway.plist"]
    assert not (system.agents / "ai.hermes.gateway.plist").exists()
    assert (home / "backups/a2assistant-migration/services/ai.hermes.gateway.plist").is_file()
    assert system.installed == [(home / "app" / ".hermes" / "bin" / "hermes", home, [""])]
    assert published == [home / "app"]
    assert os.readlink(layout.applications_link) == f"{real_home}/app/apps/desktop/release/A2Assistant.app"
    assert (layout.app_support / "A2Assistant" / "Preferences").is_file()
    assert not (layout.app_support / "Hermes").exists()

    record = Record.load(layout.marker)
    assert record.env_keys == {".env": ["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"],
                               "profiles/buero/.env": ["API_TIMEOUT"]}
    assert layout.state() is MigrationState.MIGRATED
    assert "done:" in (home / "logs" / "a2assistant-migration.log").read_text(encoding="utf-8")


def test_migrate_is_idempotent(account):
    migration, system, published, _, _ = account
    assert migration.migrate(dry_run=False) == 0
    config = (migration.layout.home / "config.yaml").read_text(encoding="utf-8")
    assert migration.migrate(dry_run=False) == 0
    assert (migration.layout.home / "config.yaml").read_text(encoding="utf-8") == config
    assert len(system.installed) == 1 and len(published) == 1


def test_rollback_restores_the_previous_layout(account):
    migration, system, _, snapshot, old_key = account
    layout = migration.layout
    assert migration.migrate(dry_run=False) == 0
    assert migration.rollback(dry_run=True) == 0
    assert layout.state() is MigrationState.MIGRATED
    assert migration.rollback(dry_run=False) == 0

    assert layout.legacy_home.is_dir() and not layout.legacy_home.is_symlink()
    assert not os.path.lexists(layout.home)
    assert (layout.legacy_home / "hermes-agent" / "hermes_cli").is_dir()
    assert (layout.legacy_home / "installs" / old_key).is_dir()
    for path, text in snapshot.items():
        if path.is_file():
            assert path.read_text(encoding="utf-8") == text, path
    assert system.started == ["ai.hermes.gateway.plist"]
    assert (system.agents / "ai.hermes.gateway.plist").is_file()
    assert not list(system.agents.glob("de.a2genesis.*"))
    assert (layout.app_support / "Hermes" / "Preferences").is_file()
    assert os.readlink(layout.applications_link).endswith("/.hermes/hermes-agent/apps/desktop/release/A2Assistant.app")
    assert layout.state() is MigrationState.PENDING
    assert migration.rollback(dry_run=False) == 0


def test_conflicting_homes_are_left_alone(tmp_path: Path):
    user = tmp_path / "user"
    (user / ".hermes").mkdir(parents=True)
    (user / ".a2assistant").mkdir()
    migration = HomeMigration(Layout(user, applications=tmp_path), FakeSystem(user), log=lambda line: None,
                              publish_launchers=lambda install: None)
    assert migration.layout.state() is MigrationState.CONFLICT
    assert migration.migrate(dry_run=False) == 1
