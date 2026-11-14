from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

from hermes_cli.branding import ENV_PREFIX, LEGACY_ENV_PREFIX

TEXT_SUFFIXES = (".yaml", ".yml", ".json", ".toml", ".cfg", ".pth")
MAX_TEXT_BYTES = 4 * 1024 * 1024
ENV_FILE_NAMES = (".env",)
_ENV_LINE = re.compile(r"^(\s*(?:export\s+)?)({prefix})([A-Za-z0-9_]+)(\s*=)")


class PathMapping:
    def __init__(self, pairs: Sequence[tuple[str, str]]):
        self.pairs = [pair for pair in pairs if pair[0] != pair[1]]
        self._pattern = re.compile("|".join(f"({re.escape(old)})(?![\\w.-])" for old, _ in self.pairs)) \
            if self.pairs else None

    def reversed(self) -> PathMapping:
        return PathMapping([(new, old) for old, new in self.pairs])

    def apply(self, text: str) -> str:
        if self._pattern is None:
            return text
        return self._pattern.sub(lambda match: self.pairs[match.lastindex - 1][1], text)


def write_atomic(path: Path, text: str) -> None:
    mode = path.stat().st_mode & 0o7777
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def read_text(path: Path) -> str | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_TEXT_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def rewrite_paths(files: Iterable[Path], mapping: PathMapping, *, dry_run: bool) -> list[Path]:
    changed = []
    for path in files:
        text = read_text(path)
        if text is None:
            continue
        result = mapping.apply(text)
        if result != text:
            changed.append(path)
            if not dry_run:
                write_atomic(path, result)
    return changed


def _rename_env_keys(text: str, old_prefix: str, new_prefix: str, only: set[str] | None) -> tuple[str, list[str]]:
    pattern = re.compile(_ENV_LINE.pattern.replace("{prefix}", re.escape(old_prefix)))
    lines = text.splitlines(keepends=True)
    existing = {match.group(3) for line in lines if (match := re.match(
        _ENV_LINE.pattern.replace("{prefix}", re.escape(new_prefix)), line))}
    renamed = []
    for index, line in enumerate(lines):
        match = pattern.match(line)
        if not match or match.group(3) in existing or (only is not None and match.group(3) not in only):
            continue
        lines[index] = f"{match.group(1)}{new_prefix}{match.group(3)}{match.group(4)}{line[match.end():]}"
        renamed.append(match.group(3))
    return "".join(lines), renamed


def rename_env_file_keys(path: Path, *, dry_run: bool, reverse_names: Iterable[str] | None = None) -> list[str]:
    text = read_text(path)
    if text is None:
        return []
    if reverse_names is None:
        result, renamed = _rename_env_keys(text, LEGACY_ENV_PREFIX, ENV_PREFIX, None)
    else:
        result, renamed = _rename_env_keys(text, ENV_PREFIX, LEGACY_ENV_PREFIX, set(reverse_names))
    if renamed and not dry_run:
        write_atomic(path, result)
    return renamed


def walk_text_files(root: Path, *, skip_dirs: Sequence[str] = ()) -> Iterator[Path]:
    if not root.is_dir():
        return
    for directory, dirs, names in os.walk(root):
        dirs[:] = [name for name in dirs if name not in skip_dirs and not (Path(directory) / name).is_symlink()]
        for name in names:
            if name.endswith(TEXT_SUFFIXES) or name in ("pyvenv.cfg",) or Path(directory).name == "bin":
                yield Path(directory) / name
