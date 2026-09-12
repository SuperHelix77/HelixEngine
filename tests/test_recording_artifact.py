"""Focused tests for the exact-byte recording artifact boundary."""

from contextlib import contextmanager
import os
from pathlib import Path
import stat
import threading
import time

import pytest

from helixengine import recording_artifact as artifact


POSIX = pytest.mark.skipif(
    os.name != "posix", reason="recording publication is POSIX-only"
)


def target(tmp_path: Path) -> Path:
    return tmp_path.resolve() / "recording.txt"


@POSIX
def test_exact_unicode_and_newline_bytes_are_published(tmp_path):
    path = target(tmp_path)
    before = "başlangıç\r\n最後\n".encode("utf-8")
    after = "İris\u00a0東京 Ϟ-17\n9007199254740993\r\n".encode("utf-8")
    path.write_bytes(before)
    path.chmod(0o640)

    receipt = artifact.publish(path, before, after)

    assert path.read_bytes() == after
    assert receipt["status"] == "published"
    assert receipt["replayed"] is False
    assert receipt["readback_exact"] is True
    assert receipt["after_sha256"] == receipt["readback_sha256"]
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


@POSIX
def test_duplicate_retry_is_exact_replayed_idempotency(tmp_path):
    path = target(tmp_path)
    before, after = b"old\n", b"new\n"
    path.write_bytes(before)

    first = artifact.publish(path, before, after)
    second = artifact.publish(path, before, after)

    assert first["status"] == "published"
    assert second["status"] == "replayed"
    assert second["replayed"] is True
    assert second["idempotent"] is True
    assert second["readback_exact"] is True
    assert path.read_bytes() == after


@POSIX
def test_duplicate_retry_target_fsync_failure_has_no_success_receipt(
    monkeypatch, tmp_path
):
    path = target(tmp_path)
    before, after = b"old\n", b"new\n"
    path.write_bytes(before)
    artifact.publish(path, before, after)
    original_fsync = artifact.os.fsync

    def fail_regular_fsync(fd):
        if stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("injected replay target fsync failure")
        return original_fsync(fd)

    monkeypatch.setattr(artifact.os, "fsync", fail_regular_fsync)
    with pytest.raises(artifact.RecordingArtifactError, match="fsync"):
        artifact.publish(path, before, after)

    assert path.read_bytes() == after


@POSIX
def test_mismatched_file_is_rejected_without_overwrite(tmp_path):
    path = target(tmp_path)
    path.write_bytes(b"caller-bound-other\n")

    with pytest.raises(artifact.RecordingConflict):
        artifact.publish(path, b"expected-old\n", b"replacement\n")

    assert path.read_bytes() == b"caller-bound-other\n"


@POSIX
def test_symlink_file_and_parent_are_rejected(tmp_path):
    root = tmp_path.resolve()
    real = root / "real"
    real.mkdir()
    actual = real / "recording.txt"
    actual.write_bytes(b"old")

    file_link = root / "file-link"
    file_link.symlink_to(actual)
    with pytest.raises(artifact.RecordingArtifactError, match="symlink"):
        artifact.publish(file_link, b"old", b"new")

    parent_link = root / "parent-link"
    parent_link.symlink_to(real, target_is_directory=True)
    with pytest.raises(artifact.RecordingArtifactError, match="symlink"):
        artifact.publish(parent_link / "recording.txt", b"old", b"new")

    assert actual.read_bytes() == b"old"


@POSIX
def test_nonregular_missing_and_multihardlink_targets_are_rejected(tmp_path):
    root = tmp_path.resolve()
    missing = root / "missing"
    with pytest.raises(artifact.RecordingArtifactError):
        artifact.publish(missing, b"old", b"new")

    directory = root / "directory"
    directory.mkdir()
    with pytest.raises(artifact.RecordingArtifactError):
        artifact.publish(directory, b"old", b"new")

    path = root / "hardlinked"
    alias = root / "hardlink-alias"
    path.write_bytes(b"old")
    alias.hardlink_to(path)
    with pytest.raises(artifact.RecordingArtifactError, match="hardlink"):
        artifact.publish(path, b"old", b"new")


@POSIX
def test_write_failure_preserves_old_and_removes_temp(monkeypatch, tmp_path):
    path = target(tmp_path)
    before, after = b"old", b"new"
    path.write_bytes(before)

    def fail_write(*_args, **_kwargs):
        raise OSError("injected write failure")

    monkeypatch.setattr(artifact.os, "write", fail_write)
    with pytest.raises(artifact.RecordingArtifactError):
        artifact.publish(path, before, after)

    assert path.read_bytes() == before
    assert list(path.parent.iterdir()) == [path]


@POSIX
def test_rename_failure_raises_and_preserves_old(monkeypatch, tmp_path):
    path = target(tmp_path)
    before, after = b"old", b"new"
    path.write_bytes(before)

    def fail_rename(*_args, **_kwargs):
        raise OSError("injected rename failure")

    monkeypatch.setattr(artifact, "_atomic_replace", fail_rename)
    with pytest.raises(artifact.UncertainPublication):
        artifact.publish(path, before, after)

    assert path.read_bytes() == before
    assert list(path.parent.iterdir()) == [path]


@POSIX
def test_readback_failure_raises_and_does_not_reset_possible_publication(
    monkeypatch, tmp_path
):
    path = target(tmp_path)
    before, after = b"old", b"new"
    path.write_bytes(before)

    def fail_readback(*_args, **_kwargs):
        raise OSError("injected readback failure")

    monkeypatch.setattr(artifact, "_readback_target", fail_readback)
    with pytest.raises(artifact.UncertainPublication) as raised:
        artifact.publish(path, before, after)

    assert raised.value.evidence["phase"] == "readback"
    assert path.read_bytes() == after


@POSIX
def test_two_concurrent_publishers_with_stale_old_have_one_conflict(
    monkeypatch, tmp_path
):
    path = target(tmp_path)
    before, after = b"old", b"new"
    path.write_bytes(before)
    barrier = threading.Barrier(2)
    original_lock = artifact._exclusive_parent_lock

    @contextmanager
    def synchronized_lock(parent_fd):
        barrier.wait(timeout=5)
        with original_lock(parent_fd):
            yield

    monkeypatch.setattr(artifact, "_exclusive_parent_lock", synchronized_lock)
    results = []

    def worker():
        try:
            results.append(("ok", artifact.publish(path, before, after)))
        except Exception as exc:  # deliberate collection of both outcomes
            results.append(("error", exc))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert sum(kind == "ok" for kind, _ in results) == 1
    assert sum(
        kind == "error" and isinstance(value, artifact.RecordingConflict)
        for kind, value in results
    ) == 1
    assert path.read_bytes() == after


@POSIX
def test_unknown_directory_durability_fails_closed_without_write(monkeypatch, tmp_path):
    path = target(tmp_path)
    before, after = b"old", b"new"
    path.write_bytes(before)

    def unsupported(_parent_fd):
        raise artifact.UnsupportedPlatform("injected unknown durability")

    monkeypatch.setattr(artifact, "_probe_directory_fsync", unsupported)
    with pytest.raises(artifact.UnsupportedPlatform):
        artifact.publish(path, before, after)

    assert path.read_bytes() == before


@POSIX
def test_lock_timeout_is_bounded(monkeypatch, tmp_path):
    path = target(tmp_path)
    before, after = b"old", b"new"
    path.write_bytes(before)
    monkeypatch.setattr(artifact, "LOCK_TIMEOUT_SECONDS", 0.03)
    monkeypatch.setattr(artifact, "LOCK_POLL_SECONDS", 0.001)

    original_flock = artifact.fcntl.flock

    def always_busy(fd, operation):
        if operation & artifact.fcntl.LOCK_NB:
            raise BlockingIOError("injected busy lock")
        return original_flock(fd, operation)

    monkeypatch.setattr(artifact.fcntl, "flock", always_busy)
    started = time.monotonic()
    with pytest.raises(artifact.LockTimeout):
        artifact.publish(path, before, after)
    assert time.monotonic() - started < 0.5
    assert path.read_bytes() == before


@POSIX
def test_verify_is_read_only_and_exact(tmp_path):
    path = target(tmp_path)
    payload = "exact\nπ\n".encode()
    path.write_bytes(payload)

    receipt = artifact.verify(path, payload)

    assert receipt["status"] == "verified"
    assert receipt["readback_exact"] is True
    assert path.read_bytes() == payload
    with pytest.raises(artifact.RecordingConflict):
        artifact.verify(path, b"different")


def test_unsupported_platform_rejection_is_explicit_and_nonmutating(
    monkeypatch, tmp_path
):
    path = tmp_path / "recording.txt"
    path.write_bytes(b"old")
    monkeypatch.setattr(artifact, "_platform_supported", lambda: False)

    with pytest.raises(artifact.UnsupportedPlatform):
        artifact.publish(path, b"old", b"new")

    assert path.read_bytes() == b"old"
