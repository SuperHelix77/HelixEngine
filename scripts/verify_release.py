#!/usr/bin/env python3
"""Verify release manifest, checksums, and package member boundaries."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import tarfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
ABSOLUTE_MEMBER = re.compile(r"^(?:/|[A-Za-z]:[\\\\/])")
FORBIDDEN_MEMBER_PARTS = {".git", "research", "private_logs", "raw_logs"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _member_names(path: Path) -> list[str]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()
    with tarfile.open(path, "r:gz") as archive:
        return [member.name for member in archive.getmembers()]


def _check_members(path: Path) -> None:
    for raw_name in _member_names(path):
        name = raw_name.replace("\\", "/")
        parts = {part for part in name.split("/") if part}
        if ABSOLUTE_MEMBER.match(name) or ".." in parts:
            raise SystemExit(f"unsafe member path: {path.name}: {raw_name}")
        if parts.intersection(FORBIDDEN_MEMBER_PARTS):
            raise SystemExit(f"forbidden member path: {path.name}: {raw_name}")


def main() -> int:
    manifest_path = DIST / "manifest.json"
    checksums_path = DIST / "SHA256SUMS"
    if not manifest_path.is_file() or not checksums_path.is_file():
        raise SystemExit("dist/manifest.json and dist/SHA256SUMS are required")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "helix.release.manifest.v1":
        raise SystemExit("unsupported release manifest schema")
    if manifest.get("package") != "helixengine" or manifest.get("version") != "0.1.0":
        raise SystemExit("release manifest package/version mismatch")
    entries = manifest.get("artifacts")
    if not isinstance(entries, list) or len(entries) != 2:
        raise SystemExit("release manifest must contain exactly one wheel and one sdist")
    if {entry.get("kind") for entry in entries} != {"wheel", "sdist"}:
        raise SystemExit("release manifest must contain one wheel and one sdist")
    expected = {}
    for entry in entries:
        name = entry.get("name")
        path = DIST / name if isinstance(name, str) else None
        if (
            path is None
            or path.parent != DIST
            or path.name != name
            or not path.is_file()
        ):
            raise SystemExit(f"missing manifest artifact: {name}")
        if name in expected:
            raise SystemExit(f"duplicate manifest artifact: {name}")
        if path.stat().st_size != entry.get("bytes") or _sha256(path) != entry.get("sha256"):
            raise SystemExit(f"manifest hash/size mismatch: {name}")
        _check_members(path)
        expected[name] = entry["sha256"]
    expected["manifest.json"] = _sha256(manifest_path)

    actual = {}
    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, separator, name = line.partition("  ")
        if not separator or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise SystemExit(f"invalid checksum line: {line}")
        if not name or Path(name).name != name or name in actual:
            raise SystemExit(f"invalid or duplicate checksum name: {name}")
        actual[name] = digest
    if actual != expected:
        raise SystemExit("SHA256SUMS does not exactly match the manifest")
    print("release manifest and checksums verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
