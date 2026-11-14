from __future__ import annotations

from pathlib import Path

from hermes_cli.branding import (
    CLI_COMMAND,
    INSTALL_DIR_NAME,
    LEGACY_INSTALL_DIR_NAME,
    LAUNCHD_GATEWAY_LABEL,
    LAUNCHD_LABEL_PREFIX,
    LEGACY_CLI_COMMAND,
    LEGACY_LAUNCHD_GATEWAY_LABEL,
    LEGACY_LAUNCHD_LABEL_PREFIX,
    LEGACY_SYSTEMD_GATEWAY_UNIT,
    SYSTEMD_GATEWAY_UNIT,
)
import hermes_constants
from hermes_constants import INSTALL_DIR_NAMES

LAUNCHD_LABEL_PREFIXES = (LAUNCHD_LABEL_PREFIX, LEGACY_LAUNCHD_LABEL_PREFIX)
LAUNCHD_GATEWAY_LABELS = (LAUNCHD_GATEWAY_LABEL, LEGACY_LAUNCHD_GATEWAY_LABEL)
LAUNCHD_RUNTIME_LABEL_PREFIX = f"{LAUNCHD_LABEL_PREFIX}-runtime."
LAUNCHD_RUNTIME_LABEL_PREFIXES = (LAUNCHD_RUNTIME_LABEL_PREFIX, "com.nousresearch.hermes.runtime.")
SYSTEMD_GATEWAY_UNITS = (SYSTEMD_GATEWAY_UNIT, LEGACY_SYSTEMD_GATEWAY_UNIT)
CLI_COMMANDS = (CLI_COMMAND, LEGACY_CLI_COMMAND)
LAUNCHER_ALIASES = {
    LEGACY_CLI_COMMAND: CLI_COMMAND,
    f"{LEGACY_CLI_COMMAND}-acp": f"{CLI_COMMAND}-acp",
    f"{LEGACY_CLI_COMMAND}-agent": f"{CLI_COMMAND}-agent",
}


def gateway_launchd_label_base() -> str:
    return LEGACY_LAUNCHD_GATEWAY_LABEL if hermes_constants.legacy_layout_active() else LAUNCHD_GATEWAY_LABEL


def gateway_launchd_label(suffix: str = "") -> str:
    base = gateway_launchd_label_base()
    return f"{base}-{suffix}" if suffix else base


def gateway_systemd_unit_base() -> str:
    return LEGACY_SYSTEMD_GATEWAY_UNIT if hermes_constants.legacy_layout_active() else SYSTEMD_GATEWAY_UNIT


def gateway_systemd_unit(suffix: str = "") -> str:
    base = gateway_systemd_unit_base()
    return f"{base}-{suffix}" if suffix else base


def is_launchd_label(label: str) -> bool:
    return label.startswith(tuple(f"{prefix}." for prefix in LAUNCHD_LABEL_PREFIXES))


def is_launchd_gateway_label(label: str) -> bool:
    return label.startswith(LAUNCHD_GATEWAY_LABELS)


def is_gateway_unit(name: str) -> bool:
    return any(name == unit or name.startswith(f"{unit}-") for unit in SYSTEMD_GATEWAY_UNITS)


def home_checkout_dir(home: Path) -> Path:
    current, legacy = (Path(home) / name for name in INSTALL_DIR_NAMES)
    return legacy if not current.exists() and legacy.is_dir() else current
