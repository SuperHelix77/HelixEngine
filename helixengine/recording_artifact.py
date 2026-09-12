"""Bounded, exact-byte publication of one caller-bound regular file.

This module deliberately has no model, command, or payload interpretation
boundary.  ``publish`` only replaces an already-existing regular file after
the caller's expected bytes, file identity, and parent identity have been
checked.  Cooperative publishers lock the parent directory with the native
OS lock.  The lock does not constrain a writer which ignores it, so callers
must own exclusive write authority for the bound path.

The publication receipt describes byte and durability evidence.  It is not a
cross-database commit receipt and does not constitute semantic approval.
Failures after replacement raise :class:`UncertainPublication`; the module
never attempts to reset a possibly published file.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
import stat
import time
import uuid

try:  # pragma: no cover - import availability is exercised by platform gates
    import fcntl
except ImportError:  # pragma: no cover - Windows and unusual Python builds
    fcntl = None


MAX_ARTIFACT_BYTES = 17 * 1024 * 1024
"""Maximum materialized file and expected byte string size."""

MAX_READ_BYTES = MAX_ARTIFACT_BYTES * 4
"""Maximum bytes read by one publish call, including bounded rechecks."""

LOCK_TIMEOUT_SECONDS = 1.0
"""Maximum time spent waiting for a cooperative parent-directory lock."""

LOCK_POLL_SECONDS = 0.01

_CHUNK_BYTES = 1024 * 1024
_SCHEMA = "helix.recording.artifact.receipt.v1"


class RecordingArtifactError(RuntimeError):
    """Base class for rejected or failed recording-artifact operations."""


class RecordingConflict(RecordingArtifactError, ValueError):
    """The caller's bound bytes or identity no longer match the file."""


class UnsupportedPlatform(RecordingArtifactError, OSError):
    """Safe native locking or durability cannot be established."""


class UncertainPublication(RecordingArtifactError, OSError):
    """A failure occurred after publication could have changed the target."""

    def __init__(self, message: str, *, evidence: dict | None = None):
        super().__init__(message)
        self.evidence = dict(evidence or {})


class LockTimeout(RecordingArtifactError, TimeoutError):
    """A cooperative publisher did not release its parent lock in time."""


# Short aliases make the failure modes convenient to catch without changing
# the more descriptive public names above.
Conflict = RecordingConflict
DurabilityUnsupported = UnsupportedPlatform


@dataclass
class _ParentBinding:
    anchor_fd: int
    parent_fd: int
    components: tuple[str | bytes, ...]
    parent_identity: tuple[int, int]
    target_name: str | bytes
    display_path: str


@dataclass
class _ReadBudget:
    used: int = 0

    def charge(self, amount: int) -> None:
        if amount < 0 or self.used + amount > MAX_READ_BYTES:
            raise RecordingArtifactError(
                f"recording read budget exceeded ({MAX_READ_BYTES} bytes)"
            )
        self.used += amount


def _require_expected(value: bytes, name: str) -> bytes:
    if type(value) is not bytes:
        raise TypeError(f"{name} must be bytes")
    if len(value) > MAX_ARTIFACT_BYTES:
        raise ValueError(
            f"{name} exceeds the {MAX_ARTIFACT_BYTES}-byte recording limit"
        )
    return value


def _path_value(path) -> str | bytes:
    try:
        value = os.fspath(path)
    except TypeError as exc:
        raise TypeError("path must be a filesystem path") from exc
    if not isinstance(value, (str, bytes)):
        raise TypeError("path must resolve to str or bytes")
    if not value:
        raise ValueError("path must name an existing file")
    nul = b"\0" if isinstance(value, bytes) else "\0"
    if nul in value:
        raise ValueError("path cannot contain NUL")
    return value


def _platform_supported() -> bool:
    """Return whether all primitives needed for safe publication exist."""

    if os.name != "posix" or fcntl is None:
        return False
    required = ("O_DIRECTORY", "O_NOFOLLOW", "fsync", "fchmod")
    if any(not hasattr(os, name) for name in required):
        return False
    if not callable(getattr(fcntl, "flock", None)):
        return False
    try:
        supported_dir_fd = os.supports_dir_fd
    except AttributeError:
        return False
    return all(
        function in supported_dir_fd
        for function in (os.open, os.stat, os.rename, os.unlink)
    ) and all(
        hasattr(fcntl, name) for name in ("LOCK_EX", "LOCK_NB", "LOCK_UN")
    )


def _ensure_platform() -> None:
    if not _platform_supported():
        raise UnsupportedPlatform(
            "safe recording publication is unsupported on this platform"
        )


def _directory_flags() -> int:
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _file_flags() -> int:
    return os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _open_directory(path, *, dir_fd: int | None = None) -> int:
    try:
        if dir_fd is None:
            return os.open(path, _directory_flags())
        return os.open(path, _directory_flags(), dir_fd=dir_fd)
    except OSError as exc:
        raise RecordingArtifactError(
            f"cannot open parent directory component safely: {path!r}"
        ) from exc


def _split_parent(path: str | bytes) -> tuple[bool, str | bytes, tuple[str | bytes, ...]]:
    is_bytes = isinstance(path, bytes)
    separator = b"/" if is_bytes else "/"
    dot = b"." if is_bytes else "."
    dotdot = b".." if is_bytes else ".."
    root = separator
    absolute = path.startswith(separator)
    parent = os.path.dirname(path)
    target_name = os.path.basename(path)
    if not target_name or target_name in (dot, dotdot):
        raise ValueError("path must name one existing file")
    if not parent:
        parent = dot if not absolute else root

    raw_components = parent.split(separator)
    components: list[str | bytes] = []
    for component in raw_components:
        if not component or component == dot:
            continue
        if component == dotdot:
            raise ValueError("parent traversal is not supported")
        components.append(component)
    return absolute, target_name, tuple(components)


def _walk_parent(path: str | bytes) -> _ParentBinding:
    absolute, target_name, components = _split_parent(path)
    anchor_path = os.sep if absolute else "."
    anchor_fd = _open_directory(anchor_path)
    current_fd = os.dup(anchor_fd)
    try:
        for component in components:
            try:
                component_stat = os.stat(
                    component, dir_fd=current_fd, follow_symlinks=False
                )
            except OSError as exc:
                raise RecordingArtifactError(
                    f"missing or unreadable parent component: {component!r}"
                ) from exc
            if stat.S_ISLNK(component_stat.st_mode):
                raise RecordingArtifactError(
                    f"symlink parent component rejected: {component!r}"
                )
            if not stat.S_ISDIR(component_stat.st_mode):
                raise RecordingArtifactError(
                    f"non-directory parent component rejected: {component!r}"
                )
            try:
                next_fd = os.open(
                    component, _directory_flags(), dir_fd=current_fd
                )
            except OSError as exc:
                raise RecordingArtifactError(
                    f"parent component changed while opening safely: {component!r}"
                ) from exc
            os.close(current_fd)
            current_fd = next_fd
        parent_stat = os.fstat(current_fd)
        if not stat.S_ISDIR(parent_stat.st_mode):  # defensive; O_DIRECTORY also checks
            raise RecordingArtifactError("bound parent is not a directory")
        display_path = os.fsdecode(path)
        return _ParentBinding(
            anchor_fd=anchor_fd,
            parent_fd=current_fd,
            components=components,
            parent_identity=(parent_stat.st_dev, parent_stat.st_ino),
            target_name=target_name,
            display_path=display_path,
        )
    except BaseException:
        os.close(current_fd)
        os.close(anchor_fd)
        raise


def _close_binding(binding: _ParentBinding) -> None:
    for fd in (binding.parent_fd, binding.anchor_fd):
        try:
            os.close(fd)
        except OSError:
            pass


def _verify_parent(binding: _ParentBinding, *, after_replace: bool = False) -> None:
    try:
        current_fd = os.dup(binding.anchor_fd)
        try:
            for component in binding.components:
                current_fd_next = os.open(
                    component, _directory_flags(), dir_fd=current_fd
                )
                os.close(current_fd)
                current_fd = current_fd_next
            current_stat = os.fstat(current_fd)
        finally:
            os.close(current_fd)
    except OSError as exc:
        kind = "after publication" if after_replace else "before publication"
        error = UncertainPublication(
            f"bound parent could not be reverified {kind}",
            evidence={"phase": "parent_identity", "path": binding.display_path},
        )
        raise error from exc
    identity = (current_stat.st_dev, current_stat.st_ino)
    if identity != binding.parent_identity:
        phase = "post_replace_parent_identity" if after_replace else "parent_identity"
        raise UncertainPublication(
            "bound parent identity changed",
            evidence={
                "phase": phase,
                "path": binding.display_path,
                "expected_parent": binding.parent_identity,
                "observed_parent": identity,
            },
        )


@contextmanager
def _exclusive_parent_lock(parent_fd: int):
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    try:
        while True:
            try:
                fcntl.flock(parent_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise LockTimeout(
                        f"cooperative parent-directory lock timed out after "
                        f"{LOCK_TIMEOUT_SECONDS:.3f}s"
                    )
                time.sleep(min(LOCK_POLL_SECONDS, max(0.0, deadline - time.monotonic())))
    except OSError as exc:
        if isinstance(exc, LockTimeout):
            raise
        raise UnsupportedPlatform(
            "exclusive parent-directory lock is unavailable"
        ) from exc
    try:
        yield
    finally:
        try:
            fcntl.flock(parent_fd, fcntl.LOCK_UN)
        except OSError as exc:
            raise UncertainPublication(
                "parent-directory lock could not be released",
                evidence={"phase": "lock_release"},
            ) from exc


def _probe_directory_fsync(parent_fd: int) -> None:
    try:
        os.fsync(parent_fd)
    except OSError as exc:
        raise UnsupportedPlatform(
            "directory durability is unknown; refusing publication"
        ) from exc


def _stat_target(parent_fd: int, target_name: str | bytes):
    try:
        target_stat = os.stat(
            target_name, dir_fd=parent_fd, follow_symlinks=False
        )
    except FileNotFoundError as exc:
        raise RecordingArtifactError("bound recording file is missing") from exc
    except OSError as exc:
        raise RecordingArtifactError("bound recording file cannot be stated") from exc
    if stat.S_ISLNK(target_stat.st_mode):
        raise RecordingArtifactError("symlink recording file rejected")
    if not stat.S_ISREG(target_stat.st_mode):
        raise RecordingArtifactError("recording target must be a regular file")
    if target_stat.st_nlink != 1:
        raise RecordingArtifactError("multi-hardlink recording file rejected")
    if target_stat.st_size < 0 or target_stat.st_size > MAX_ARTIFACT_BYTES:
        raise RecordingArtifactError(
            f"recording file exceeds the {MAX_ARTIFACT_BYTES}-byte limit"
        )
    return target_stat


def _file_identity(target_stat) -> tuple[int, int, int, int, int, int, int]:
    return (
        target_stat.st_dev,
        target_stat.st_ino,
        target_stat.st_nlink,
        target_stat.st_mode,
        target_stat.st_size,
        target_stat.st_mtime_ns,
        target_stat.st_ctime_ns,
    )


def _same_file_identity(first, second) -> bool:
    return _file_identity(first) == _file_identity(second)


def _read_fd(fd: int, budget: _ReadBudget) -> bytes:
    result = bytearray()
    while True:
        remaining = MAX_ARTIFACT_BYTES - len(result)
        request = min(_CHUNK_BYTES, remaining + 1)
        try:
            block = os.read(fd, request)
        except InterruptedError:
            continue
        except OSError as exc:
            raise RecordingArtifactError("recording file read failed") from exc
        if not block:
            break
        budget.charge(len(block))
        result.extend(block)
        if len(result) > MAX_ARTIFACT_BYTES:
            raise RecordingArtifactError(
                f"recording file exceeds the {MAX_ARTIFACT_BYTES}-byte limit"
            )
    return bytes(result)


def _read_target(
    parent_fd: int,
    target_name: str | bytes,
    budget: _ReadBudget,
    *,
    bound_stat=None,
):
    initial_stat = _stat_target(parent_fd, target_name)
    if bound_stat is not None and not _same_file_identity(bound_stat, initial_stat):
        raise RecordingConflict("bound recording file identity changed")
    try:
        fd = os.open(target_name, _file_flags(), dir_fd=parent_fd)
    except OSError as exc:
        raise RecordingArtifactError("bound recording file cannot be opened safely") from exc
    try:
        opened_stat = os.fstat(fd)
        if not stat.S_ISREG(opened_stat.st_mode) or opened_stat.st_nlink != 1:
            raise RecordingArtifactError("recording target changed from regular file")
        if not _same_file_identity(initial_stat, opened_stat):
            raise RecordingConflict("recording file identity changed while opening")
        payload = _read_fd(fd, budget)
        final_stat = os.fstat(fd)
        if not _same_file_identity(opened_stat, final_stat):
            raise RecordingConflict("recording file changed during read")
        path_final_stat = _stat_target(parent_fd, target_name)
        if not _same_file_identity(final_stat, path_final_stat):
            raise RecordingConflict("recording file identity changed during read")
        if final_stat.st_size != len(payload):
            raise RecordingConflict("recording file size changed during read")
        if bound_stat is not None and not _same_file_identity(bound_stat, final_stat):
            raise RecordingConflict("bound recording file changed during read")
        return payload, final_stat
    finally:
        os.close(fd)


def _temp_name(target_name: str | bytes) -> str | bytes:
    token = uuid.uuid4().hex
    if isinstance(target_name, bytes):
        return b"." + target_name + b".helix-recording-" + token.encode("ascii")
    return "." + target_name + ".helix-recording-" + token


def _create_temp(parent_fd: int, target_name: str | bytes) -> tuple[str | bytes, int]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    flags |= getattr(os, "O_CLOEXEC", 0)
    for _ in range(8):
        candidate = _temp_name(target_name)
        try:
            return candidate, os.open(candidate, flags, 0o600, dir_fd=parent_fd)
        except FileExistsError:
            continue
        except OSError as exc:
            raise RecordingArtifactError("same-directory temp file creation failed") from exc
    raise RecordingArtifactError("could not allocate a unique temp file")


def _write_all(fd: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        block = payload[offset : offset + _CHUNK_BYTES]
        try:
            written = os.write(fd, block)
        except InterruptedError:
            continue
        except OSError as exc:
            raise RecordingArtifactError("same-directory temp write failed") from exc
        if written <= 0 or written > len(block):
            raise RecordingArtifactError("same-directory temp write made no progress")
        offset += written


def _remove_temp(parent_fd: int, temp_name: str | bytes | None) -> None:
    if temp_name is None:
        return
    try:
        os.unlink(temp_name, dir_fd=parent_fd)
    except FileNotFoundError:
        return
    except OSError:
        # The original publication error is more useful.  A failure to clean
        # up a temp file is retained by the caller's exception evidence.
        return


def _write_temp(
    parent_fd: int, target_name: str | bytes, payload: bytes, mode: int
) -> str | bytes:
    temp_name, temp_fd = _create_temp(parent_fd, target_name)
    completed = False
    try:
        _write_all(temp_fd, payload)
        try:
            os.fchmod(temp_fd, mode)
            os.fsync(temp_fd)
        except OSError as exc:
            raise RecordingArtifactError("temp file permission or fsync failed") from exc
        completed = True
        return temp_name
    finally:
        try:
            os.close(temp_fd)
        finally:
            if not completed:
                _remove_temp(parent_fd, temp_name)


def _atomic_replace(
    parent_fd: int, temp_name: str | bytes, target_name: str | bytes
) -> None:
    try:
        os.replace(
            temp_name,
            target_name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
    except OSError as exc:
        raise UncertainPublication(
            "atomic replacement outcome is uncertain",
            evidence={"phase": "atomic_replace"},
        ) from exc


def _readback_target(parent_fd: int, target_name: str | bytes, budget: _ReadBudget):
    """Read the replacement through a fresh path-bound descriptor."""

    return _read_target(parent_fd, target_name, budget)


def _fsync_replay_target(
    parent_fd: int,
    target_name: str | bytes,
    bound_stat,
    expected_after: bytes,
    budget: _ReadBudget,
):
    """Durably revalidate an already-present exact target before replaying."""

    current_stat = _stat_target(parent_fd, target_name)
    if not _same_file_identity(bound_stat, current_stat):
        raise RecordingConflict("replayed recording file identity changed")
    try:
        fd = os.open(target_name, _file_flags(), dir_fd=parent_fd)
    except OSError as exc:
        raise RecordingArtifactError(
            "replayed recording file cannot be opened for fsync"
        ) from exc
    try:
        opened_stat = os.fstat(fd)
        if not _same_file_identity(bound_stat, opened_stat):
            raise RecordingConflict("replayed recording file identity changed")
        try:
            os.fsync(fd)
        except OSError as exc:
            raise RecordingArtifactError(
                "replayed recording file fsync failed"
            ) from exc
        final_stat = os.fstat(fd)
        if not _same_file_identity(opened_stat, final_stat):
            raise RecordingConflict("replayed recording file changed during fsync")
    finally:
        os.close(fd)

    replayed_bytes, replayed_stat = _read_target(
        parent_fd,
        target_name,
        budget,
        bound_stat=bound_stat,
    )
    if replayed_bytes != expected_after:
        raise RecordingConflict("replayed recording bytes changed during revalidation")
    return replayed_bytes, replayed_stat


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _receipt(
    binding: _ParentBinding,
    *,
    expected_before: bytes,
    expected_after: bytes,
    mode: int,
    status: str,
    replayed: bool,
    readback_sha256: str,
    read_bytes: int,
    atomic_replacement: bool,
    temp_fsync: bool,
    target_fsync: bool,
    directory_fsync: bool,
) -> dict:
    return {
        "schema": _SCHEMA,
        "operation": "publish",
        "status": status,
        "path": binding.display_path,
        "bytes": len(expected_after),
        "before_sha256": _digest(expected_before),
        "after_sha256": _digest(expected_after),
        "readback_sha256": readback_sha256,
        "readback": True,
        "readback_exact": readback_sha256 == _digest(expected_after),
        "read_bytes": read_bytes,
        "permissions": stat.S_IMODE(mode),
        "replayed": replayed,
        "idempotent": replayed,
        "atomic_replacement": atomic_replacement,
        "durability": {
            "temp_fsync": temp_fsync,
            "target_fsync": target_fsync,
            "directory_fsync": directory_fsync,
        },
        "lock": "parent_directory_exclusive",
        "semantic_approval": None,
        "max_bytes": MAX_ARTIFACT_BYTES,
        "read_budget_bytes": MAX_READ_BYTES,
    }


def _conflict_for_observed(observed: bytes, expected_before: bytes, expected_after: bytes):
    if observed == expected_after:
        return RecordingConflict(
            "recording target became the expected bytes while this publisher waited; "
            "retry was based on a stale bound"
        )
    return RecordingConflict("recording target does not match expected_before")


def publish(path, expected_before: bytes, expected_after: bytes) -> dict:
    """Publish ``expected_after`` over one already-existing bound file.

    The call returns only after durable temp-file and directory fsyncs plus a
    complete exact readback.  If ``expected_after`` was already present when
    this call bound the target, a replayed/idempotent receipt is returned.  A
    publisher which observed ``expected_before`` before waiting on the lock is
    treated as stale when another publisher wins that lock first.
    """

    expected_before = _require_expected(expected_before, "expected_before")
    expected_after = _require_expected(expected_after, "expected_after")
    path_value = _path_value(path)
    _ensure_platform()
    binding = _walk_parent(path_value)
    temp_name: str | bytes | None = None
    try:
        # Bind and read once before waiting for the cooperative publisher lock.
        # This preserves the stale-old conflict distinction for two callers
        # which start concurrently, while a later duplicate sees the new inode.
        _probe_directory_fsync(binding.parent_fd)
        budget = _ReadBudget()
        pre_bytes, pre_stat = _read_target(
            binding.parent_fd, binding.target_name, budget
        )
        if pre_bytes not in (expected_before, expected_after):
            raise _conflict_for_observed(
                pre_bytes, expected_before, expected_after
            )

        with _exclusive_parent_lock(binding.parent_fd):
            _verify_parent(binding)
            current_bytes, current_stat = _read_target(
                binding.parent_fd,
                binding.target_name,
                budget,
            )
            if not _same_file_identity(pre_stat, current_stat):
                raise _conflict_for_observed(
                    current_bytes, expected_before, expected_after
                )
            if pre_bytes == expected_after:
                if current_bytes != expected_after:
                    raise _conflict_for_observed(
                        current_bytes, expected_before, expected_after
                    )
                replayed_bytes, replayed_stat = _fsync_replay_target(
                    binding.parent_fd,
                    binding.target_name,
                    current_stat,
                    expected_after,
                    budget,
                )
                try:
                    os.fsync(binding.parent_fd)
                except OSError as exc:
                    raise RecordingArtifactError(
                        "directory fsync failed during replay"
                    ) from exc
                _verify_parent(binding)
                return _receipt(
                    binding,
                    expected_before=expected_before,
                    expected_after=expected_after,
                    mode=replayed_stat.st_mode,
                    status="replayed",
                    replayed=True,
                    readback_sha256=_digest(replayed_bytes),
                    read_bytes=budget.used,
                    atomic_replacement=False,
                    temp_fsync=False,
                    target_fsync=True,
                    directory_fsync=True,
                )
            if current_bytes != expected_before:
                raise _conflict_for_observed(
                    current_bytes, expected_before, expected_after
                )

            mode = stat.S_IMODE(pre_stat.st_mode)
            temp_name = _write_temp(
                binding.parent_fd, binding.target_name, expected_after, mode
            )
            try:
                # Recheck the bound old inode/content after writing the temp so
                # a writer which ignores the cooperative lock is never silently
                # overwritten when its change is observable here.
                before_replace, before_replace_stat = _read_target(
                    binding.parent_fd,
                    binding.target_name,
                    budget,
                    bound_stat=pre_stat,
                )
                if before_replace != expected_before:
                    raise _conflict_for_observed(
                        before_replace, expected_before, expected_after
                    )
                _verify_parent(binding)
                _atomic_replace(
                    binding.parent_fd, temp_name, binding.target_name
                )
                temp_name = None
            except RecordingConflict:
                raise
            except UncertainPublication:
                raise
            except BaseException as exc:
                raise UncertainPublication(
                    "publication failed before replacement completed",
                    evidence={"phase": "pre_replace"},
                ) from exc
            finally:
                _remove_temp(binding.parent_fd, temp_name)

            try:
                os.fsync(binding.parent_fd)
            except OSError as exc:
                raise UncertainPublication(
                    "directory fsync failed after replacement",
                    evidence={"phase": "directory_fsync"},
                ) from exc

            try:
                readback, readback_stat = _readback_target(
                    binding.parent_fd,
                    binding.target_name,
                    budget,
                )
            except BaseException as exc:
                if isinstance(exc, UncertainPublication):
                    raise
                raise UncertainPublication(
                    "full readback failed after replacement",
                    evidence={"phase": "readback"},
                ) from exc
            if readback != expected_after:
                raise UncertainPublication(
                    "full readback bytes differ after replacement",
                    evidence={
                        "phase": "readback",
                        "expected_after_sha256": _digest(expected_after),
                        "observed_sha256": _digest(readback),
                    },
                )
            if stat.S_IMODE(readback_stat.st_mode) != mode:
                raise UncertainPublication(
                    "published file permissions differ from the bound file",
                    evidence={
                        "phase": "readback_permissions",
                        "expected_permissions": mode,
                        "observed_permissions": stat.S_IMODE(readback_stat.st_mode),
                    },
                )
            _verify_parent(binding, after_replace=True)
            return _receipt(
                binding,
                expected_before=expected_before,
                expected_after=expected_after,
                mode=mode,
                status="published",
                replayed=False,
                readback_sha256=_digest(readback),
                read_bytes=budget.used,
                atomic_replacement=True,
                temp_fsync=True,
                target_fsync=False,
                directory_fsync=True,
            )
    finally:
        _remove_temp(binding.parent_fd, temp_name)
        _close_binding(binding)


def verify(path, expected: bytes) -> dict:
    """Read and verify one existing bound file without modifying it."""

    expected = _require_expected(expected, "expected")
    path_value = _path_value(path)
    _ensure_platform()
    binding = _walk_parent(path_value)
    try:
        budget = _ReadBudget()
        with _exclusive_parent_lock(binding.parent_fd):
            _verify_parent(binding)
            payload, target_stat = _read_target(
                binding.parent_fd, binding.target_name, budget
            )
            if payload != expected:
                raise RecordingConflict("recording target does not match expected bytes")
            _verify_parent(binding)
            return {
                "schema": _SCHEMA,
                "operation": "verify",
                "status": "verified",
                "path": binding.display_path,
                "bytes": len(payload),
                "sha256": _digest(payload),
                "readback": True,
                "readback_exact": True,
                "read_bytes": budget.used,
                "permissions": stat.S_IMODE(target_stat.st_mode),
                "lock": "parent_directory_exclusive",
                "max_bytes": MAX_ARTIFACT_BYTES,
                "read_budget_bytes": MAX_READ_BYTES,
            }
    finally:
        _close_binding(binding)


__all__ = [
    "MAX_ARTIFACT_BYTES",
    "MAX_READ_BYTES",
    "LOCK_TIMEOUT_SECONDS",
    "RecordingArtifactError",
    "RecordingConflict",
    "Conflict",
    "UnsupportedPlatform",
    "DurabilityUnsupported",
    "LockTimeout",
    "UncertainPublication",
    "publish",
    "verify",
]
