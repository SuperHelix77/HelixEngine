"""Packaging and asset smoke tests; no model calls or benchmarks."""

from __future__ import annotations

import hashlib
import importlib
from importlib import resources
import json
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def _project_metadata() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)["project"]


def test_project_metadata_is_portable_with_bounded_tls_dependency() -> None:
    project = _project_metadata()
    assert project["name"] == "helixengine"
    assert project["version"] == "0.1.0"
    assert project["requires-python"] == ">=3.11"
    assert project["dependencies"] == ["certifi>=2024.2.2"]
    assert project["scripts"]["helixengine"] == "helixengine.cli:main"
    assert "license" not in project
    assert "license-files" not in project


def test_package_version_matches_project() -> None:
    package = importlib.import_module("helixengine")
    assert package.__version__ == _project_metadata()["version"] == "0.1.0"


def test_console_entrypoint_resolves() -> None:
    module = importlib.import_module("helixengine.cli")
    assert callable(module.main)


def test_web_and_public_capsule_assets_are_package_data() -> None:
    package = resources.files("helixengine")
    for relative in (
        ("web", "index.html"),
        ("web", "app.js"),
        ("web", "style.css"),
        ("release_evidence", "index.json"),
    ):
        assert package.joinpath(*relative).is_file(), relative


def test_capsules_are_hash_bound_and_paths_are_local() -> None:
    capsule_root = ROOT / "helixengine" / "release_evidence"
    index = json.loads((capsule_root / "index.json").read_text(encoding="utf-8"))
    for entry in index["lanes"]:
        name = entry["file"]
        path = (capsule_root / name).resolve()
        assert path.parent == capsule_root.resolve()
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"]


def test_package_data_does_not_include_private_or_research_paths() -> None:
    package_root = ROOT / "helixengine"
    forbidden = {"research", "private_logs", "raw_logs", ".git"}
    for path in package_root.rglob("*"):
        assert not forbidden.intersection(path.relative_to(package_root).parts), path
