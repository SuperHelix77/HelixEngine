"""Focused tests for exact, read-only recording recovery."""

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path

import pytest

from helixengine import recording_artifact as artifact


POSIX = pytest.mark.skipif(
    os.name != "posix", reason="recording verification is POSIX-only"
)


def target(tmp_path: Path) -> Path:
    return tmp_path.resolve() / "recording.txt"


@POSIX
def test_read_verified_returns_exact_unicode_and_nul_bytes(tmp_path):
    path = target(tmp_path)
    expected = "başlangıç\r\n最後\n".encode("utf-8") + b"nul\x00tail\xff"
    path.write_bytes(expected)

    payload, receipt = artifact.read_verified(path, expected)

    assert type(payload) is bytes
    assert payload == expected
    assert receipt["status"] == "verified"
    assert receipt["readback_exact"] is True
    assert receipt["bytes"] == len(expected)
    assert receipt["sha256"] == hashlib.sha256(expected).hexdigest()
    assert receipt["scope"] == (
        "Point-in-time exact read; not future file freshness or semantic guarantee"
    )
    assert path.read_bytes() == expected


@POSIX
def test_verify_receipt_is_unchanged_and_read_shares_one_target_read(
    monkeypatch, tmp_path
):
    path = target(tmp_path)
    expected = b"bound\n"
    path.write_bytes(expected)
    original_read_target = artifact._read_target
    calls = []

    def counted_read_target(*args, **kwargs):
        calls.append(1)
        return original_read_target(*args, **kwargs)

    monkeypatch.setattr(artifact, "_read_target", counted_read_target)

    before = artifact.verify(path, expected)
    payload, read_receipt = artifact.read_verified(path, expected)
    after = artifact.verify(path, expected)

    assert payload == expected
    assert read_receipt["scope"].startswith("Point-in-time exact read")
    assert before == after
    assert calls == [1, 1, 1]


@POSIX
def test_mismatch_fails_without_writing(tmp_path):
    path = target(tmp_path)
    actual = b"actual\n"
    path.write_bytes(actual)
    before = path.stat()

    with pytest.raises(artifact.RecordingConflict):
        artifact.read_verified(path, b"stale\n")

    after = path.stat()
    assert path.read_bytes() == actual
    assert (after.st_ino, after.st_size, after.st_mtime_ns) == (
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )


@POSIX
def test_change_during_read_is_rejected(monkeypatch, tmp_path):
    path = target(tmp_path)
    expected = b"before-read\n"
    changed = b"changed-during-read\n"
    path.write_bytes(expected)
    original_read_fd = artifact._read_fd

    def read_then_change(fd, budget):
        payload = original_read_fd(fd, budget)
        path.write_bytes(changed)
        return payload

    monkeypatch.setattr(artifact, "_read_fd", read_then_change)

    with pytest.raises(artifact.RecordingConflict, match="during read"):
        artifact.read_verified(path, expected)

    assert path.read_bytes() == changed


@POSIX
def test_post_read_mutation_cannot_change_returned_payload(monkeypatch, tmp_path):
    path = target(tmp_path)
    expected = b"point-in-time\n"
    changed = b"after-lock-release\n"
    path.write_bytes(expected)
    original_lock = artifact._exclusive_parent_lock

    @contextmanager
    def mutate_after_unlock(parent_fd):
        with original_lock(parent_fd):
            yield
        path.write_bytes(changed)

    monkeypatch.setattr(artifact, "_exclusive_parent_lock", mutate_after_unlock)

    payload, receipt = artifact.read_verified(path, expected)

    assert payload == expected
    assert receipt["sha256"] == hashlib.sha256(expected).hexdigest()
    assert path.read_bytes() == changed


@POSIX
def test_symlink_and_hardlink_targets_are_rejected(tmp_path):
    root = tmp_path.resolve()
    actual = root / "actual"
    actual.write_bytes(b"exact")

    symlink = root / "symlink"
    symlink.symlink_to(actual)
    with pytest.raises(artifact.RecordingArtifactError, match="symlink"):
        artifact.read_verified(symlink, b"exact")

    hardlink = root / "hardlink"
    hardlink.hardlink_to(actual)
    with pytest.raises(artifact.RecordingArtifactError, match="hardlink"):
        artifact.read_verified(actual, b"exact")


def test_unsupported_platform_behavior_is_unchanged(monkeypatch, tmp_path):
    path = tmp_path / "recording.txt"
    expected = b"old"
    path.write_bytes(expected)
    monkeypatch.setattr(artifact, "_platform_supported", lambda: False)

    with pytest.raises(artifact.UnsupportedPlatform):
        artifact.read_verified(path, expected)

    assert path.read_bytes() == expected
