from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from hermes_cli.branding import (
    CLI_COMMAND,
    ENV_PREFIX,
    LAUNCHD_GATEWAY_LABEL,
    LEGACY_ENV_PREFIX,
    LEGACY_LAUNCHD_GATEWAY_LABEL,
    LEGACY_SYSTEMD_GATEWAY_UNIT,
    SYSTEMD_GATEWAY_UNIT,
)
from hermes_cli.desktop_bundle import MACOS_APP_BUNDLE

COMMAND_TIMEOUT_S = 120
INSTALL_COMMAND = ("gateway", "install", "--start-now", "--start-on-login")


class MigrationSystem(Protocol):
    def desktop_running(self) -> bool: ...

    def service_files(self, legacy: bool) -> list[Path]: ...

    def stop_service(self, unit_file: Path) -> None: ...

    def start_service(self, unit_file: Path) -> None: ...

    def install_gateways(self, launcher: Path, home: Path, profiles: list[str]) -> None: ...


def _uid() -> int:
    return os.getuid() if hasattr(os, "getuid") else 0


def _run(command: list[str], *, env: dict[str, str] | None = None, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, env=env,
                          timeout=COMMAND_TIMEOUT_S, check=check)


def profile_of_service_file(unit_file: Path) -> str | None:
    stem = unit_file.name.removesuffix(".plist").removesuffix(".service")
    for base in (LAUNCHD_GATEWAY_LABEL, LEGACY_LAUNCHD_GATEWAY_LABEL, SYSTEMD_GATEWAY_UNIT,
                 LEGACY_SYSTEMD_GATEWAY_UNIT):
        if stem == base:
            return None
        if stem.startswith(base + "-"):
            return stem[len(base) + 1:]
    return None


@dataclass
class HostSystem:
    user_home: Path
    platform: str = field(default_factory=lambda: sys.platform)

    @property
    def _service_dir(self) -> Path:
        if self.platform == "darwin":
            return self.user_home / "Library" / "LaunchAgents"
        return self.user_home / ".config" / "systemd" / "user"

    def desktop_running(self) -> bool:
        if self.platform != "darwin":
            return False
        return _run(["/usr/bin/pgrep", "-f", MACOS_APP_BUNDLE + "/Contents/MacOS/"]).returncode == 0

    def service_files(self, legacy: bool) -> list[Path]:
        if self.platform == "darwin":
            base, suffix = (LEGACY_LAUNCHD_GATEWAY_LABEL if legacy else LAUNCHD_GATEWAY_LABEL), ".plist"
        else:
            base, suffix = (LEGACY_SYSTEMD_GATEWAY_UNIT if legacy else SYSTEMD_GATEWAY_UNIT), ".service"
        directory = self._service_dir
        if not directory.is_dir():
            return []
        return sorted(path for path in directory.iterdir()
                      if path.name == base + suffix or (path.name.startswith(base + "-") and path.name.endswith(suffix)))

    def stop_service(self, unit_file: Path) -> None:
        if self.platform == "darwin":
            _run(["/bin/launchctl", "bootout", f"gui/{_uid()}", str(unit_file)])
        else:
            _run(["systemctl", "--user", "disable", "--now", unit_file.name])

    def start_service(self, unit_file: Path) -> None:
        if self.platform == "darwin":
            _run(["/bin/launchctl", "bootstrap", f"gui/{_uid()}", str(unit_file)], check=True)
        else:
            _run(["systemctl", "--user", "daemon-reload"])
            _run(["systemctl", "--user", "enable", "--now", unit_file.name], check=True)

    def install_gateways(self, launcher: Path, home: Path, profiles: list[str]) -> None:
        env = {key: value for key, value in os.environ.items() if not key.startswith((ENV_PREFIX, LEGACY_ENV_PREFIX))}
        env[ENV_PREFIX + "HOME"] = str(home)
        if self.platform != "darwin":
            _run(["systemctl", "--user", "daemon-reload"])
        for profile in profiles:
            selector = ["-p", profile] if profile else []
            done = _run([str(launcher), *selector, *INSTALL_COMMAND], env=env)
            if done.returncode != 0:
                raise RuntimeError(f"`{CLI_COMMAND} {' '.join([*selector, *INSTALL_COMMAND])}` failed: "
                                   f"{(done.stderr or done.stdout).strip()[-400:]}")
