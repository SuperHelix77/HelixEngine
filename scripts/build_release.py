#!/usr/bin/env python3
"""Build release artifacts and deterministic manifest/checksums.

The runtime package has one small TLS certificate dependency, certifi. The
build command itself uses the PEP 517 build frontend installed by maintainers.
"""

from __future__ import annotations

import hashlib
import copy
import gzip
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
FORBIDDEN_MEMBER_PARTS = {".git", "research", "private_logs", "raw_logs"}
ABSOLUTE_MEMBER = re.compile(r"^(?:/|[A-Za-z]:[\\\\/])")


def _metadata() -> tuple[str, str]:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = config.get("project", {})
    name = project.get("name")
    version = project.get("version")
    if name != "helixengine" or version != "0.1.0":
        raise SystemExit("pyproject.toml must declare helixengine version 0.1.0")
    return name, version


def _artifact_names(name: str, version: str) -> tuple[str, str]:
    return f"{name}-{version}-py3-none-any.whl", f"{name}-{version}.tar.gz"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_utf8(path: Path, value: str) -> None:
    path.write_bytes(value.encode("utf-8"))


def _member_names(path: Path) -> list[str]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()
    with tarfile.open(path, "r:gz") as archive:
        return [member.name for member in archive.getmembers()]


def _assert_safe_members(path: Path) -> None:
    for raw_name in _member_names(path):
        name = raw_name.replace("\\", "/")
        parts = {part for part in name.split("/") if part}
        if ABSOLUTE_MEMBER.match(name) or ".." in parts:
            raise SystemExit(f"unsafe absolute or parent path in {path.name}: {raw_name}")
        if parts.intersection(FORBIDDEN_MEMBER_PARTS):
            raise SystemExit(f"forbidden private/research path in {path.name}: {raw_name}")


def _normalize_sdist(path: Path, source_epoch: int) -> None:
    """Rewrite setuptools' sdist with stable tar and gzip metadata."""
    temporary = None
    try:
        with tarfile.open(path, "r:gz") as archive:
            members = archive.getmembers()
            payloads = {}
            for member in members:
                if member.isfile():
                    source = archive.extractfile(member)
                    payloads[member.name] = source.read() if source is not None else b""
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".helixengine-sdist-", suffix=".tar.gz", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            with gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=source_epoch) as compressed:
                with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as output:
                    for original in sorted(members, key=lambda item: item.name):
                        member = copy.copy(original)
                        member.mtime = source_epoch
                        member.uid = 0
                        member.gid = 0
                        member.uname = ""
                        member.gname = ""
                        member.pax_headers = {}
                        if member.isfile():
                            output.addfile(member, io.BytesIO(payloads[member.name]))
                        else:
                            output.addfile(member)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _build(name: str, version: str) -> None:
    DIST.mkdir(exist_ok=True)
    wheel_name, sdist_name = _artifact_names(name, version)
    for filename in (wheel_name, sdist_name, "manifest.json", "SHA256SUMS"):
        target = DIST / filename
        if target.exists():
            if not target.is_file():
                raise SystemExit(f"release target is not a regular file: {target}")
            target.unlink()

    source_epoch = os.environ.get("SOURCE_DATE_EPOCH", "315532800")
    try:
        source_epoch_int = int(source_epoch)
    except ValueError as exc:
        raise SystemExit("SOURCE_DATE_EPOCH must be an integer") from exc
    if source_epoch_int < 0:
        raise SystemExit("SOURCE_DATE_EPOCH must be non-negative")
    # pip's Windows console launchers are ZIP files too. Build isolation
    # inherits this value, so dates before 1980 break dependency installation.
    source_epoch_int = max(source_epoch_int, 315532800)

    environment = os.environ.copy()
    environment["SOURCE_DATE_EPOCH"] = str(source_epoch_int)
    environment.setdefault("PYTHONHASHSEED", "0")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--sdist",
            "--outdir",
            "dist",
            ".",
        ],
        cwd=ROOT,
        env=environment,
        check=True,
    )

    wheel = DIST / wheel_name
    sdist = DIST / sdist_name
    if not wheel.is_file() or not sdist.is_file():
        raise SystemExit("build did not produce the expected wheel and sdist")
    _normalize_sdist(sdist, source_epoch_int)
    unexpected = sorted(
        path.name
        for path in DIST.iterdir()
        if path.is_file()
        and path.suffix in {".whl", ".gz"}
        and path.name not in {wheel_name, sdist_name}
    )
    if unexpected:
        raise SystemExit(f"unexpected release artifacts in dist: {', '.join(unexpected)}")

    for artifact in (wheel, sdist):
        _assert_safe_members(artifact)

    artifacts = [
        {
            "name": path.name,
            "kind": "wheel" if path.suffix == ".whl" else "sdist",
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in (wheel, sdist)
    ]
    manifest = {
        "schema": "helix.release.manifest.v1",
        "package": name,
        "version": version,
        "source_date_epoch": source_epoch_int,
        "runtime_dependencies": ["certifi>=2024.2.2"],
        "artifacts": artifacts,
        "limits": [
            "Manifest covers the wheel and sdist emitted by this build.",
            "Checksums do not attest to a third-party source or operating-system package manager.",
        ],
    }
    manifest_path = DIST / "manifest.json"
    _write_utf8(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    checksum_entries = artifacts + [
        {
            "name": manifest_path.name,
            "sha256": _sha256(manifest_path),
        }
    ]
    _write_utf8(
        DIST / "SHA256SUMS",
        "".join(f"{entry['sha256']}  {entry['name']}\n" for entry in checksum_entries),
    )
    print(f"built {wheel.name}")
    print(f"built {sdist.name}")
    print("wrote dist/manifest.json and dist/SHA256SUMS")


if __name__ == "__main__":
    _build(*_metadata())
