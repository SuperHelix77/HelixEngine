"""Installed entrypoint contract, independent of setup's internal helpers."""
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


def test_unqualified_host_keeps_simple_and_compound_commands_native(monkeypatch):
    from helixengine import codex_intercept
    monkeypatch.setattr(codex_intercept, "os", SimpleNamespace(name="nt"))
    assert codex_intercept.route("git status --short") is None
    assert codex_intercept.route("git status --short && git diff --stat") is None


@pytest.mark.skipif(os.name != "posix", reason="Native hook setup currently qualifies POSIX only")
def test_codex_setup_cli_preserves_config_and_status_has_no_data_side_effect(tmp_path):
    project = tmp_path / "project with spaces"
    project.mkdir()
    data = tmp_path / "not-created-by-setup"
    command = [sys.executable, "-m", "helixengine", "--data-dir", str(data), "codex"]

    def invoke(action):
        return subprocess.run(command + [action, "--project", str(project)],
                              capture_output=True, timeout=10)

    status = invoke("status")
    assert status.returncode == 0, status.stderr
    assert not data.exists() and not (project / ".codex").exists()
    assert json.loads(status.stdout)["changed"] is False
    installed = invoke("install")
    assert installed.returncode == 0, installed.stderr
    hooks = project / ".codex" / "hooks.json"
    first = hooks.read_bytes()
    assert "PreToolUse" in json.loads(first)["hooks"]
    assert invoke("install").returncode == 0
    assert hooks.read_bytes() == first
    removed = invoke("remove")
    assert removed.returncode == 0, removed.stderr
    assert not (project / ".codex" / "config.toml").exists()
    assert not data.exists()


def test_codex_setup_requires_explicit_project():
    result = subprocess.run([sys.executable, "-m", "helixengine", "codex", "install"],
                            capture_output=True, timeout=10)
    assert result.returncode == 2
    assert b"--project" in result.stderr
