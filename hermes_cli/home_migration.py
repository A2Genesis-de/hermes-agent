from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from hermes_cli.branding import (
    CLI_COMMAND,
    DESKTOP_USER_DATA_DIR,
    HOME_DIR_NAME,
    INSTALL_DIR_NAME,
    LEGACY_CLI_COMMAND,
    LEGACY_DESKTOP_USER_DATA_DIR,
    LEGACY_HOME_DIR_NAME,
    LEGACY_INSTALL_DIR_NAME,
    MIGRATION_MARKER,
)
from hermes_cli.desktop_bundle import MACOS_APP_BUNDLE
from hermes_cli.home_migration_rewrite import (
    PathMapping,
    read_text,
    rename_env_file_keys,
    rewrite_paths,
    walk_text_files,
    write_atomic,
)
from hermes_cli.home_migration_system import MigrationSystem, profile_of_service_file
from pm.environments import install_key_for

MARKER_VERSION = 1
BACKUP_DIR = Path("backups") / "a2assistant-migration"
LOG_FILE = Path("logs") / "a2assistant-migration.log"
SKIPPED_INSTALL_DIRS = ("__pycache__", "node_modules", ".git")


class MigrationState(Enum):
    PENDING = "pending"
    MIGRATED = "migrated"
    FRESH = "fresh"
    CONFLICT = "conflict"


class MigrationRefused(RuntimeError):
    pass


@dataclass(frozen=True)
class Layout:
    user_home: Path
    applications: Path = Path("/Applications")

    @property
    def real_user_home(self) -> Path:
        return Path(os.path.realpath(self.user_home))

    @property
    def legacy_home(self) -> Path:
        return self.user_home / LEGACY_HOME_DIR_NAME

    @property
    def home(self) -> Path:
        return self.user_home / HOME_DIR_NAME

    @property
    def marker(self) -> Path:
        return self.home / MIGRATION_MARKER

    @property
    def app_support(self) -> Path:
        return self.user_home / "Library" / "Application Support"

    @property
    def local_bin(self) -> Path:
        return self.user_home / ".local" / "bin"

    @property
    def applications_link(self) -> Path:
        return self.applications / MACOS_APP_BUNDLE

    def install_paths(self, home: Path, legacy: bool) -> tuple[Path, Path]:
        names = (LEGACY_INSTALL_DIR_NAME, INSTALL_DIR_NAME) if legacy else (INSTALL_DIR_NAME, LEGACY_INSTALL_DIR_NAME)
        return home / names[0], home / names[1]

    def state(self) -> MigrationState:
        home_real = self.home.is_dir() and not self.home.is_symlink()
        legacy_real = self.legacy_home.is_dir() and not self.legacy_home.is_symlink()
        if home_real and self.marker.is_file():
            return MigrationState.MIGRATED
        if legacy_real and not os.path.lexists(self.home):
            return MigrationState.PENDING
        if not legacy_real and not os.path.lexists(self.home):
            return MigrationState.FRESH
        if home_real and not legacy_real:
            return MigrationState.FRESH
        return MigrationState.CONFLICT

    def mapping(self, record: Record) -> PathMapping:
        legacy_real = str(self.real_user_home / LEGACY_HOME_DIR_NAME)
        home_real = str(self.real_user_home / HOME_DIR_NAME)
        pairs = []
        if record.install_moved:
            pairs.append((f"{legacy_real}/installs/{record.legacy_install_key}",
                          f"{home_real}/installs/{record.install_key}"))
            pairs.append((f"{legacy_real}/{LEGACY_INSTALL_DIR_NAME}", f"{home_real}/{INSTALL_DIR_NAME}"))
            pairs.append((f"~/{LEGACY_HOME_DIR_NAME}/{LEGACY_INSTALL_DIR_NAME}", f"~/{HOME_DIR_NAME}/{INSTALL_DIR_NAME}"))
        pairs += [(legacy_real, home_real), (f"~/{LEGACY_HOME_DIR_NAME}", f"~/{HOME_DIR_NAME}"),
                  (f"$HOME/{LEGACY_HOME_DIR_NAME}", f"$HOME/{HOME_DIR_NAME}"),
                  (f"${{HOME}}/{LEGACY_HOME_DIR_NAME}", f"${{HOME}}/{HOME_DIR_NAME}")]
        return PathMapping(pairs)


@dataclass
class Record:
    migrated_at: str = ""
    install_moved: bool = False
    legacy_install_key: str = ""
    install_key: str = ""
    env_keys: dict[str, list[str]] = field(default_factory=dict)
    service_profiles: list[str] = field(default_factory=list)
    service_backups: list[str] = field(default_factory=list)
    service_dir: str = ""
    applications_link: str = ""
    user_data_moved: bool = False
    completed: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> Record:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        data.pop("version", None)
        return cls(**{key: value for key, value in data.items() if key in cls.__dataclass_fields__})

    def save(self, path: Path) -> None:
        payload = {"version": MARKER_VERSION, **self.__dict__}
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)


@dataclass
class Step:
    description: str
    action: Callable[[], None]
    name: str = ""


def profile_homes(home: Path) -> list[Path]:
    profiles = home / "profiles"
    if not profiles.is_dir():
        return []
    return sorted(path for path in profiles.iterdir() if path.is_dir() and not path.is_symlink()
                  and not path.name.startswith("."))


def config_files(home: Path) -> Iterator[Path]:
    for root in (home, *profile_homes(home)):
        for pattern in ("*.yaml", "*.yml", "*.json", "cron/*.json", "plugins/*/*.yaml", "plugins/*/*.yml",
                        "plugins/*/*.json", "plugins/*/*.toml"):
            yield from sorted(root.glob(pattern))


def env_files(home: Path) -> list[Path]:
    return [root / ".env" for root in (home, *profile_homes(home)) if (root / ".env").is_file()]


class HomeMigration:
    def __init__(self, layout: Layout, system: MigrationSystem, *, log: Callable[[str], None] = print,
                 publish_launchers: Callable[[Path], object] | None = None):
        self.layout = layout
        self.system = system
        self.log = log
        self.publish_launchers = publish_launchers or _expose_cli

    def _timestamp(self) -> str:
        return datetime.now(UTC).isoformat(timespec="seconds")

    def _write_log(self, home: Path, line: str) -> None:
        path = home / LOG_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(f"{self._timestamp()} {line}\n")

    def _require_desktop_closed(self) -> None:
        if self.system.desktop_running():
            raise MigrationRefused(f"Quit {MACOS_APP_BUNDLE.removesuffix('.app')} first; the desktop app is running.")

    def _rewrite_targets(self, home: Path, install: Path) -> Iterator[Path]:
        yield from config_files(home)
        installs = home / "installs"
        if installs.is_dir():
            for state_dir in sorted(installs.iterdir()):
                yield from walk_text_files(state_dir, skip_dirs=SKIPPED_INSTALL_DIRS)
        launchers = install / ".hermes" / "bin"
        if launchers.is_dir():
            yield from sorted(path for path in launchers.iterdir() if path.is_file())
        if self.layout.local_bin.is_dir():
            yield from sorted(path for path in self.layout.local_bin.iterdir() if path.is_file())

    def plan(self) -> list[Step]:
        state = self.layout.state()
        if state is not MigrationState.PENDING:
            return []
        layout = self.layout
        record = Record(migrated_at=self._timestamp())
        legacy_install, _ = layout.install_paths(layout.legacy_home, legacy=True)
        record.install_moved = legacy_install.is_dir() and not legacy_install.is_symlink()
        if record.install_moved:
            record.legacy_install_key = install_key_for(str(layout.real_user_home / LEGACY_HOME_DIR_NAME
                                                            / LEGACY_INSTALL_DIR_NAME))
            record.install_key = install_key_for(str(layout.real_user_home / HOME_DIR_NAME / INSTALL_DIR_NAME))
        legacy_services = self.system.service_files(legacy=True)
        record.service_profiles = [profile_of_service_file(path) or "" for path in legacy_services]
        record.service_dir = str(legacy_services[0].parent) if legacy_services else ""
        home = layout.home
        install = home / INSTALL_DIR_NAME

        def save() -> None:
            record.save(layout.marker)

        def stop_services() -> None:
            backup = layout.legacy_home / BACKUP_DIR / "services"
            backup.mkdir(parents=True, exist_ok=True)
            for path in legacy_services:
                self.system.stop_service(path)
                shutil.move(str(path), backup / path.name)
                record.service_backups.append(path.name)

        def move_home() -> None:
            os.rename(layout.legacy_home, home)
            os.symlink(home, layout.legacy_home)
            save()

        def move_install() -> None:
            os.rename(home / LEGACY_INSTALL_DIR_NAME, install)
            os.symlink(INSTALL_DIR_NAME, home / LEGACY_INSTALL_DIR_NAME)
            old_state, new_state = home / "installs" / record.legacy_install_key, home / "installs" / record.install_key
            if old_state.is_dir() and not os.path.lexists(new_state):
                os.rename(old_state, new_state)
            save()

        def rewrite() -> None:
            changed = rewrite_paths(self._rewrite_targets(home, install), layout.mapping(record), dry_run=False)
            for path in changed:
                self._write_log(home, f"rewrote paths in {path}")
            for path in env_files(home):
                renamed = rename_env_file_keys(path, dry_run=False)
                if renamed:
                    record.env_keys[str(path.relative_to(home))] = renamed
            save()

        def move_desktop() -> None:
            link = layout.applications_link
            if link.is_symlink():
                target = os.readlink(link)
                moved = layout.mapping(record).apply(target)
                if moved != target:
                    record.applications_link = target
                    link.unlink()
                    os.symlink(moved, link)
            legacy_data, data = layout.app_support / LEGACY_DESKTOP_USER_DATA_DIR, layout.app_support / DESKTOP_USER_DATA_DIR
            if legacy_data.is_dir() and not legacy_data.is_symlink() and not os.path.lexists(data):
                os.rename(legacy_data, data)
                record.user_data_moved = True
            save()

        def publish_launchers() -> None:
            self.publish_launchers(install)

        def install_services() -> None:
            if record.service_profiles:
                self.system.install_gateways(self._launcher(install), home, record.service_profiles)

        steps = [
            Step("Check that the desktop app is closed", self._require_desktop_closed, "desktop_closed"),
            Step(f"Stop and set aside {len(legacy_services)} gateway service(s): "
                 + ", ".join(path.name for path in legacy_services), stop_services, "services_stopped"),
            Step(f"Move {layout.legacy_home} to {home} and keep {layout.legacy_home} as a link", move_home, "home_moved"),
        ]
        if record.install_moved:
            steps.append(Step(f"Rename the install {home / LEGACY_INSTALL_DIR_NAME} to {install} (old name kept as a "
                              f"link) and its dependency state {record.legacy_install_key} to {record.install_key}",
                              move_install, "install_moved"))
        steps += [
            Step("Rewrite absolute paths in config.yaml, profile configs, cron jobs, plugin configs, dependency "
                 "state and launchers; rename HERMES_* keys in .env files to A2ASSISTANT_*", rewrite, "rewritten"),
            Step(f"Point {layout.applications_link} at the moved build and move the desktop data "
                 f"{LEGACY_DESKTOP_USER_DATA_DIR} to {DESKTOP_USER_DATA_DIR}", move_desktop, "desktop_moved"),
        ]
        if record.install_moved:
            steps.append(Step(f"Publish the `{CLI_COMMAND}` launchers (`{LEGACY_CLI_COMMAND}` stays as an alias)",
                              publish_launchers, "launchers"))
        steps.append(Step("Install and start the gateway service(s) under the new name for: "
                          + (", ".join(name or "default" for name in record.service_profiles) or "none"),
                          install_services, "services_installed"))
        for step in steps:
            step.action = self._tracked(step, record, home)
        return steps

    def _tracked(self, step: Step, record: Record, home: Path) -> Callable[[], None]:
        action = step.action

        def run() -> None:
            action()
            record.completed.append(step.name)
            if self.layout.marker.parent.is_dir() and step.name not in ("desktop_closed", "services_stopped"):
                record.save(self.layout.marker)
                self._write_log(home, f"done: {step.description}")

        return run

    def _launcher(self, install: Path) -> Path:
        directory = install / ".hermes" / "bin"
        for name in (CLI_COMMAND, LEGACY_CLI_COMMAND):
            if (directory / name).is_file():
                return directory / name
        raise MigrationRefused(f"no launcher in {directory}")

    def migrate(self, *, dry_run: bool) -> int:
        state = self.layout.state()
        if state is MigrationState.MIGRATED:
            self.log(f"Already migrated to {self.layout.home}; nothing to do.")
            return 0
        if state is MigrationState.FRESH:
            self.log(f"No {self.layout.legacy_home} to migrate; nothing to do.")
            return 0
        if state is MigrationState.CONFLICT:
            self.log(f"Both {self.layout.legacy_home} and {self.layout.home} exist; resolve that by hand first.")
            return 1
        steps = self.plan()
        self.log("Plan (dry run, nothing changed):" if dry_run else "Migrating:")
        for number, step in enumerate(steps, 1):
            self.log(f"  {number}. {step.description}")
        if dry_run:
            return 0
        for step in steps:
            try:
                step.action()
            except MigrationRefused as exc:
                self.log(f"Refused: {exc}")
                return 1
            except Exception as exc:  # health: allow BLE001 -- a failed step is reported with the rollback hint
                self.log(f"Failed at '{step.description}': {exc}")
                if self.layout.marker.is_file():
                    self.log(f"Run `{CLI_COMMAND} migrate --rollback` to restore the previous layout.")
                return 1
        self.log(f"Done. Home: {self.layout.home}; log: {self.layout.home / LOG_FILE}")
        return 0

    def rollback(self, *, dry_run: bool) -> int:
        layout = self.layout
        if not layout.marker.is_file() or layout.home.is_symlink():
            self.log("No completed or partial migration found; nothing to roll back.")
            return 0
        record = Record.load(layout.marker)
        home, legacy = layout.home, layout.legacy_home
        install = home / INSTALL_DIR_NAME
        steps = [
            Step("Check that the desktop app is closed", self._require_desktop_closed),
            Step("Stop and remove the renamed gateway service(s)", self._remove_new_services),
            Step("Restore HERMES_* keys in .env files and the previous absolute paths",
                 lambda: self._restore_files(record, home, install)),
            Step("Restore the desktop link and data directory", lambda: self._restore_desktop(record)),
        ]
        if record.install_moved:
            steps.append(Step(f"Rename {install} back to {LEGACY_INSTALL_DIR_NAME}",
                              lambda: self._restore_install(record, home)))
        steps += [
            Step(f"Move {home} back to {legacy}", lambda: self._restore_home(record)),
            Step("Restore and start the previous gateway service(s)", lambda: self._restore_services(record)),
        ]
        self.log("Rollback plan (dry run, nothing changed):" if dry_run else "Rolling back:")
        for number, step in enumerate(steps, 1):
            self.log(f"  {number}. {step.description}")
        if dry_run:
            return 0
        for step in steps:
            try:
                step.action()
            except MigrationRefused as exc:
                self.log(f"Refused: {exc}")
                return 1
            except Exception as exc:  # health: allow BLE001 -- a failed rollback step is reported, not raised
                self.log(f"Rollback failed at '{step.description}': {exc}")
                return 1
        self.log(f"Rolled back to {legacy}.")
        return 0

    def _remove_new_services(self) -> None:
        for path in self.system.service_files(legacy=False):
            self.system.stop_service(path)
            path.unlink(missing_ok=True)

    def _restore_files(self, record: Record, home: Path, install: Path) -> None:
        rewrite_paths(self._rewrite_targets(home, install), self.layout.mapping(record).reversed(), dry_run=False)
        for relative, names in record.env_keys.items():
            if (home / relative).is_file():
                rename_env_file_keys(home / relative, dry_run=False, reverse_names=names)

    def _restore_desktop(self, record: Record) -> None:
        link = self.layout.applications_link
        if record.applications_link and link.is_symlink():
            link.unlink()
            os.symlink(record.applications_link, link)
        legacy_data = self.layout.app_support / LEGACY_DESKTOP_USER_DATA_DIR
        data = self.layout.app_support / DESKTOP_USER_DATA_DIR
        if record.user_data_moved and data.is_dir() and not os.path.lexists(legacy_data):
            os.rename(data, legacy_data)

    def _restore_install(self, record: Record, home: Path) -> None:
        link = home / LEGACY_INSTALL_DIR_NAME
        if link.is_symlink():
            link.unlink()
        if (home / INSTALL_DIR_NAME).is_dir() and not os.path.lexists(link):
            os.rename(home / INSTALL_DIR_NAME, link)
        new_state, old_state = home / "installs" / record.install_key, home / "installs" / record.legacy_install_key
        if new_state.is_dir() and not os.path.lexists(old_state):
            os.rename(new_state, old_state)

    def _restore_home(self, record: Record) -> None:
        layout = self.layout
        archive = layout.home / BACKUP_DIR / f"rolled-back-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
        archive.parent.mkdir(parents=True, exist_ok=True)
        os.replace(layout.marker, archive)
        if layout.legacy_home.is_symlink():
            layout.legacy_home.unlink()
        os.rename(layout.home, layout.legacy_home)
        self._write_log(layout.legacy_home, f"rolled back; record kept at {archive.name}")

    def _restore_services(self, record: Record) -> None:
        backup = self.layout.legacy_home / BACKUP_DIR / "services"
        for name in record.service_backups:
            source = backup / name
            if source.is_file() and record.service_dir:
                target = Path(record.service_dir) / name
                shutil.move(str(source), target)
                self.system.start_service(target)


def _expose_cli(install: Path) -> object:
    from hermes_cli._launchers import expose_cli

    return expose_cli(install)


def is_pending(user_home: Path | None = None) -> bool:
    return Layout(user_home or Path.home()).state() is MigrationState.PENDING


def install_inside_legacy_home(install_root: Path, user_home: Path | None = None) -> bool:
    legacy = Path(os.path.realpath((user_home or Path.home()) / LEGACY_HOME_DIR_NAME))
    try:
        Path(os.path.realpath(install_root)).relative_to(legacy)
    except ValueError:
        return False
    return True


__all__ = ["HomeMigration", "Layout", "MigrationRefused", "MigrationState", "Record", "install_inside_legacy_home",
           "is_pending", "read_text", "write_atomic"]
