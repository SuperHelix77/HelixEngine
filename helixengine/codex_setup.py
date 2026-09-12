"""Bounded, project-local setup for the optional Codex command hooks.

This module owns only the project ``.codex/hooks.json`` file.  It does not
touch trust records, model settings, permissions, skills, or the Helix data
directory.  Native hook trust and reload remain a separate operator action.
"""

from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import shlex
import sys
import tempfile
from typing import Any


MAX_CONFIG_BYTES = 256 * 1024
MANAGED_STATUS = "HelixEngine managed Codex hook (do not edit)"
EVENTS = ("PreToolUse", "SubagentStart", "SubagentStop", "UserPromptSubmit")
_LOCK_NAME = ".hooks.json.helix.lock"


class SetupRefused(ValueError):
    """The requested setup would be unsafe or ambiguous."""


def _result(path: Path, *, changed: bool, installed: bool, supported: bool = True, error: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(path),
        "changed": changed,
        "supported": supported,
        "installed": installed,
        "native_trust_review_required": True,
        "installed_config_presence_is_not_activation_proof": True,
    }
    if error:
        result["error"] = error
    return result


def _project_paths(project: os.PathLike[str] | str) -> tuple[Path, Path, Path]:
    try:
        project_path = Path(project).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, TypeError) as exc:
        raise SetupRefused(f"Invalid project path: {exc}") from exc
    if not project_path.is_dir():
        raise SetupRefused("Project path must be a directory")
    codex_dir = project_path / ".codex"
    config_path = codex_dir / "hooks.json"
    return project_path, codex_dir, config_path


def _check_codex_dir(codex_dir: Path, *, create: bool) -> None:
    if codex_dir.is_symlink():
        raise SetupRefused(f"Refusing symlinked .codex directory: {codex_dir}")
    if codex_dir.exists() and not codex_dir.is_dir():
        raise SetupRefused(f".codex is not a directory: {codex_dir}")
    if create and not codex_dir.exists():
        codex_dir.mkdir(mode=0o700)


def _read_bytes(config_path: Path) -> bytes | None:
    if config_path.is_symlink():
        raise SetupRefused(f"Refusing symlinked hooks file: {config_path}")
    if not config_path.exists():
        return None
    if not config_path.is_file():
        raise SetupRefused(f"Hooks path is not a regular file: {config_path}")
    try:
        with config_path.open("rb") as stream:
            raw = stream.read(MAX_CONFIG_BYTES + 1)
    except OSError as exc:
        raise SetupRefused(f"Cannot read hooks file: {exc}") from exc
    if len(raw) > MAX_CONFIG_BYTES:
        raise SetupRefused(f"Hooks file exceeds {MAX_CONFIG_BYTES} bytes")
    return raw


def _validate_shape(value: Any, path: str = "config") -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SetupRefused("Existing hooks JSON must be an object")
    hooks = value.get("hooks")
    if "hooks" in value and not isinstance(hooks, dict):
        raise SetupRefused("Existing hooks JSON 'hooks' must be an object")
    if hooks is None:
        return value
    for event, groups in hooks.items():
        if not isinstance(event, str) or not isinstance(groups, list):
            raise SetupRefused("Existing hooks JSON has invalid event list types")
        for index, group in enumerate(groups):
            if not isinstance(group, dict):
                raise SetupRefused(f"Existing hook group {event}[{index}] must be an object")
            group_hooks = group.get("hooks")
            if not isinstance(group_hooks, list):
                raise SetupRefused(f"Existing hook group {event}[{index}] has invalid hooks")
            for hook_index, hook in enumerate(group_hooks):
                if not isinstance(hook, dict):
                    raise SetupRefused(f"Existing hook {event}[{index}].hooks[{hook_index}] must be an object")
                if "type" in hook and not isinstance(hook["type"], str):
                    raise SetupRefused("Existing hook type must be a string")
                if "command" in hook and not isinstance(hook["command"], str):
                    raise SetupRefused("Existing hook command must be a string")
                if "statusMessage" in hook and not isinstance(hook["statusMessage"], str):
                    raise SetupRefused("Existing hook statusMessage must be a string")
    return value


def _decode(raw: bytes | None) -> dict[str, Any]:
    if raw is None:
        return {}
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise SetupRefused("Duplicate JSON key in hooks configuration")
            result[key] = value
        return result
    def constant(value):
        raise SetupRefused("Non-finite JSON value in hooks configuration")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise SetupRefused(f"Existing hooks file is not valid UTF-8 JSON: {exc}") from exc
    return _validate_shape(value)


def _command(data_dir: os.PathLike[str] | str, python_executable: os.PathLike[str] | str | None) -> str:
    executable = sys.executable if python_executable is None else os.fspath(python_executable)
    if not isinstance(executable, str) or not executable or "\x00" in executable:
        raise SetupRefused("python_executable must be a non-empty path")
    data = os.fspath(data_dir)
    if not isinstance(data, str) or not data or "\x00" in data:
        raise SetupRefused("data_dir must be a non-empty path")
    intercept = str(Path(__file__).resolve().with_name("codex_intercept.py"))
    executable = str(Path(executable).expanduser().absolute())
    data = str(Path(data).expanduser().resolve())
    return shlex.join([executable, intercept, "hook", data])


def _managed_groups(command: str) -> dict[str, dict[str, Any]]:
    hook = {"type": "command", "command": command, "timeout": 10, "statusMessage": MANAGED_STATUS}
    return {
        "PreToolUse": {"matcher": "^Bash$", "hooks": [hook]},
        "SubagentStart": {"hooks": [hook]},
        "SubagentStop": {"hooks": [hook]},
        "UserPromptSubmit": {"hooks": [hook]},
    }


def _contains_marker(value: Any) -> bool:
    if isinstance(value, str):
        return MANAGED_STATUS in value
    if isinstance(value, dict):
        return any(_contains_marker(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_marker(item) for item in value)
    return False


def _inspect_managed(config: dict[str, Any], expected: dict[str, dict[str, Any]]) -> tuple[bool, dict[str, Any]]:
    hooks = config.get("hooks")
    if hooks is None:
        hooks = {}
        config["hooks"] = hooks
    for event, groups in hooks.items():
        for group in groups:
            marker = _contains_marker(group)
            adapter = any("codex_intercept.py" in hook.get("command", "") for hook in group["hooks"])
            if (marker or adapter) and (event not in expected or group != expected[event]):
                raise SetupRefused("Existing Helix adapter is unmanaged or altered; reconcile it before setup")
    installed = True
    for event in EVENTS:
        groups = hooks.get(event, [])
        if not isinstance(groups, list):
            raise SetupRefused(f"Existing hooks JSON event {event} must be a list")
        exact = 0
        for group in groups:
            if _contains_marker(group):
                if group != expected[event]:
                    raise SetupRefused(f"Managed {event} hook marker exists but its group was altered")
                exact += 1
        if exact == 0:
            installed = False
    return installed, hooks


def _new_config(raw: bytes | None, command: str, action: str) -> tuple[dict[str, Any], bool, bool]:
    config = _decode(raw)
    expected = _managed_groups(command)
    installed, hooks = _inspect_managed(config, expected)
    if action == "status":
        return config, False, installed
    if action == "install":
        changed = False
        for event in EVENTS:
            groups = hooks.setdefault(event, [])
            exact = [group for group in groups if group == expected[event]]
            retained = []
            seen = False
            for group in groups:
                if group == expected[event]:
                    if not seen:
                        retained.append(group)
                        seen = True
                    else:
                        changed = True
                else:
                    retained.append(group)
            if not exact:
                retained.append(expected[event])
                changed = True
            hooks[event] = retained
        return config, changed, True
    changed = False
    for event in EVENTS:
        groups = hooks.get(event, [])
        retained = [group for group in groups if group != expected[event]]
        if len(retained) != len(groups):
            changed = True
        if retained:
            hooks[event] = retained
        elif event in hooks:
            del hooks[event]
    if not hooks and "hooks" in config:
        del config["hooks"]
    return config, changed, False


def _serialize(config: dict[str, Any]) -> bytes:
    try:
        payload = json.dumps(config, indent=2, ensure_ascii=False, sort_keys=False, allow_nan=False).encode("utf-8") + b"\n"
    except (TypeError, ValueError) as exc:
        raise SetupRefused(f"Hooks configuration cannot be serialized: {exc}") from exc
    if len(payload) > MAX_CONFIG_BYTES:
        raise SetupRefused(f"New hooks file exceeds {MAX_CONFIG_BYTES} bytes")
    return payload


def _atomic_bytes(path: Path, payload: bytes, mode: int = 0o600) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temporary_path = Path(temporary)
    try:
        os.fchmod(fd, mode & 0o777)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    except Exception:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise


class _CooperativeLock:
    def __init__(self, path: Path):
        self.path = path
        self.fd: int | None = None

    def __enter__(self):
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(self.fd, f"{os.getpid()}\n".encode("ascii"))
            os.fsync(self.fd)
        except FileExistsError as exc:
            raise SetupRefused(f"Another cooperative Codex setup is active: {self.path}") from exc
        except OSError as exc:
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
                self.path.unlink(missing_ok=True)
            raise SetupRefused(f"Cannot acquire cooperative setup lock: {exc}") from exc
        return self

    def __exit__(self, exc_type, exc, traceback):
        if self.fd is not None:
            os.close(self.fd)
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        return False


def _change(config_path: Path, codex_dir: Path, original: bytes | None, payload: bytes) -> None:
    mode = 0o600 if original is None else (config_path.stat().st_mode & 0o777)
    temporary_fd, temporary_name = tempfile.mkstemp(prefix=f".{config_path.name}.", dir=str(codex_dir))
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(temporary_fd, mode)
        with os.fdopen(temporary_fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        current = _read_bytes(config_path)
        if current != original:
            raise SetupRefused("Hooks file changed during setup; refusing to replace it")
        if original is not None:
            backup = config_path.with_name(f"hooks.json.helix-{hashlib.sha256(original).hexdigest()}.bak")
            if backup.is_symlink():
                raise SetupRefused(f"Refusing symlinked hooks backup: {backup}")
            if backup.exists():
                if _read_bytes(backup) != original:
                    raise SetupRefused("Existing configuration backup changed")
            else:
                _atomic_bytes(backup, original, mode)
        # The second read is intentionally immediately before replacement.
        _check_codex_dir(codex_dir, create=False)
        if _read_bytes(config_path) != original:
            raise SetupRefused("Hooks file changed before atomic replacement; refusing to replace it")
        os.replace(temporary_path, config_path)
        try:
            directory_fd = os.open(codex_dir, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    except Exception:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise


def configure(
    project: os.PathLike[str] | str,
    data_dir: os.PathLike[str] | str,
    action: str = "install",
    python_executable: os.PathLike[str] | str | None = None,
) -> dict[str, Any]:
    """Install, remove, or inspect the bounded project Codex hook groups."""
    if action not in {"install", "remove", "status"}:
        raise SetupRefused("action must be install, remove, or status")
    _, codex_dir, config_path = _project_paths(project)
    if os.name != "posix":
        if action != "status":
            raise SetupRefused("Codex hook setup currently supports POSIX only")
        return _result(
            config_path,
            changed=False,
            installed=False,
            supported=False,
            error="Codex hook setup currently supports POSIX only",
        )
    command = _command(data_dir, python_executable)
    if action == "status":
        _check_codex_dir(codex_dir, create=False)
        raw = _read_bytes(config_path)
        _, changed, installed = _new_config(raw, command, action)
        return _result(config_path, changed=changed, installed=installed)

    _check_codex_dir(codex_dir, create=action == "install")
    if not codex_dir.exists():
        return _result(config_path, changed=False, installed=False)
    lock_path = codex_dir / _LOCK_NAME
    with _CooperativeLock(lock_path):
        original = _read_bytes(config_path)
        config, changed, installed = _new_config(original, command, action)
        if not changed:
            return _result(config_path, changed=False, installed=installed)
        _change(config_path, codex_dir, original, _serialize(config))
        return _result(config_path, changed=True, installed=installed)
