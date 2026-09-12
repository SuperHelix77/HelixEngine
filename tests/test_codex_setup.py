import json
import os
from pathlib import Path
import sys

import pytest

from helixengine.codex_setup import MANAGED_STATUS, SetupRefused, configure

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Managed native hook setup qualifies POSIX only")

def _config(project):
    return project / ".codex" / "hooks.json"


def test_install_preserves_top_level_and_unrelated_hooks_and_is_idempotent(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    codex = project / ".codex"
    codex.mkdir()
    hooks = codex / "hooks.json"
    original = {
        "name": "keep me",
        "hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": "continuity"}]}],
            "PreToolUse": [{"matcher": "^Read$", "hooks": [{"type": "command", "command": "other"}]}],
        },
        "extra": {"preserve": True},
    }
    hooks.write_text(json.dumps(original), encoding="utf-8")

    first = configure(project, tmp_path / "data")
    first_bytes = hooks.read_bytes()
    assert first["changed"] is True
    assert first["native_trust_review_required"] is True
    result = json.loads(first_bytes)
    assert result["name"] == original["name"] and result["extra"] == original["extra"]
    assert result["hooks"]["SessionStart"] == original["hooks"]["SessionStart"]
    assert result["hooks"]["PreToolUse"][0] == original["hooks"]["PreToolUse"][0]
    assert len(result["hooks"]["PreToolUse"]) == 2
    assert all(event in result["hooks"] for event in ("PreToolUse", "SubagentStart", "SubagentStop"))
    assert configure(project, tmp_path / "data")["changed"] is False
    assert hooks.read_bytes() == first_bytes
    backups = list(codex.glob("hooks.json.helix-*.bak"))
    assert len(backups) == 1 and backups[0].read_bytes() == json.dumps(original).encode()


def test_remove_refuses_altered_managed_group(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    configure(project, tmp_path / "data")
    hooks = _config(project)
    value = json.loads(hooks.read_text())
    value["hooks"]["SubagentStart"][0]["hooks"][0]["timeout"] = 77
    hooks.write_text(json.dumps(value), encoding="utf-8")
    before = hooks.read_bytes()
    with pytest.raises(SetupRefused, match="altered"):
        configure(project, tmp_path / "data", "remove")

    assert hooks.read_bytes() == before


def test_remove_own_groups_preserves_unrelated_and_is_idempotent(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    configure(project, tmp_path / "data")
    hooks = _config(project)
    value = json.loads(hooks.read_text())
    value["hooks"]["PreToolUse"].insert(0, {"matcher": "^Read$", "hooks": [{"type": "command", "command": "keep"}]})
    hooks.write_text(json.dumps(value), encoding="utf-8")
    removed = configure(project, tmp_path / "data", "remove")
    assert removed["changed"] is True
    after = json.loads(hooks.read_text())
    assert after == {"hooks": {"PreToolUse": [{"matcher": "^Read$", "hooks": [{"type": "command", "command": "keep"}]}]}}
    assert configure(project, tmp_path / "data", "remove")["changed"] is False


def test_status_is_read_only_and_reports_presence(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    data = tmp_path / "data"
    result = configure(project, data, "status")
    assert result["changed"] is False and result["installed"] is False
    assert not data.exists() and not (project / ".codex").exists()
    configure(project, data)
    status = configure(project, data, "status")
    assert status["changed"] is False and status["installed"] is True


def test_malformed_oversized_and_modified_files_are_refused(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    codex = project / ".codex"
    codex.mkdir()
    hooks = codex / "hooks.json"
    hooks.write_text("{", encoding="utf-8")
    with pytest.raises(SetupRefused):
        configure(project, tmp_path / "data")
    hooks.write_bytes(b"{}")
    hooks.write_bytes(b"x" * (256 * 1024 + 1))
    with pytest.raises(SetupRefused):
        configure(project, tmp_path / "data")

    hooks.unlink()
    configure(project, tmp_path / "data")
    value = json.loads(hooks.read_text())
    value["hooks"]["PreToolUse"][0]["hooks"][0]["command"] += " altered"
    hooks.write_text(json.dumps(value), encoding="utf-8")
    before = hooks.read_bytes()
    with pytest.raises(SetupRefused, match="altered"):
        configure(project, tmp_path / "data")
    assert hooks.read_bytes() == before


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlink behavior")
def test_symlinked_codex_and_hooks_are_refused(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    real = tmp_path / "real-codex"
    real.mkdir()
    (project / ".codex").symlink_to(real, target_is_directory=True)
    with pytest.raises(SetupRefused, match="symlinked .codex"):
        configure(project, tmp_path / "data")

    project2 = tmp_path / "project2"
    project2.mkdir()
    codex = project2 / ".codex"
    codex.mkdir()
    target = tmp_path / "hooks-target.json"
    target.write_text("{}", encoding="utf-8")
    (codex / "hooks.json").symlink_to(target)
    with pytest.raises(SetupRefused, match="symlinked hooks"):
        configure(project2, tmp_path / "data")


def test_exact_command_has_expected_script_and_all_three_events(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    data = tmp_path / "data with spaces"
    configure(project, data, python_executable=sys.executable)
    value = json.loads(_config(project).read_text())
    commands = {}
    for event in ("PreToolUse", "SubagentStart", "SubagentStop"):
        group = value["hooks"][event][0]
        commands[event] = group["hooks"][0]["command"]
        assert group["hooks"][0]["statusMessage"] == MANAGED_STATUS
        assert "codex_intercept.py" in commands[event]
        assert " hook " in f" {commands[event]} "
        assert "session_scope" not in commands[event]
    assert value["hooks"]["PreToolUse"][0]["matcher"] == "^Bash$"
    assert commands["PreToolUse"] == commands["SubagentStart"] == commands["SubagentStop"]


@pytest.mark.parametrize("raw", [b'{"hooks":{},"hooks":{}}', b'{"hooks":null}', b'{"value":NaN}'])
def test_ambiguous_or_nonstandard_json_is_preserved_not_normalized(tmp_path, raw):
    codex = tmp_path / ".codex"
    codex.mkdir()
    hooks = codex / "hooks.json"
    hooks.write_bytes(raw)
    with pytest.raises(SetupRefused):
        configure(tmp_path, tmp_path / "data")
    assert hooks.read_bytes() == raw


def test_unmanaged_existing_adapter_prevents_duplicate_installation(tmp_path):
    codex = tmp_path / ".codex"
    codex.mkdir()
    hooks = codex / "hooks.json"
    raw = json.dumps({"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "python /old/codex_intercept.py hook /data"}]}]}}).encode()
    hooks.write_bytes(raw)
    with pytest.raises(SetupRefused, match="unmanaged"):
        configure(tmp_path, tmp_path / "data")
    assert hooks.read_bytes() == raw


def test_concurrent_change_detected_after_backup_is_not_overwritten(tmp_path, monkeypatch):
    from helixengine import codex_setup
    codex = tmp_path / ".codex"
    codex.mkdir()
    hooks = codex / "hooks.json"
    hooks.write_bytes(b'{}')
    atomic = codex_setup._atomic_bytes
    changed = b'{"user":"concurrent edit"}'
    def backup_then_edit(*args):
        atomic(*args)
        hooks.write_bytes(changed)
    monkeypatch.setattr(codex_setup, "_atomic_bytes", backup_then_edit)
    with pytest.raises(SetupRefused, match="changed"):
        configure(tmp_path, tmp_path / "data")
    assert hooks.read_bytes() == changed
    assert not (codex / ".hooks.json.helix.lock").exists()


def test_failed_publication_keeps_original_and_allows_explicit_later_install(tmp_path, monkeypatch):
    from helixengine import codex_setup
    codex = tmp_path / ".codex"
    codex.mkdir()
    hooks = codex / "hooks.json"
    original = b'{"description":"original"}'
    hooks.write_bytes(original)
    replace = codex_setup.os.replace
    def fail_config(source, target):
        if Path(target) == hooks:
            raise OSError("injected publication failure")
        return replace(source, target)
    with monkeypatch.context() as context:
        context.setattr(codex_setup.os, "replace", fail_config)
        with pytest.raises(OSError, match="injected"):
            configure(tmp_path, tmp_path / "data")
    assert hooks.read_bytes() == original
    assert not (codex / ".hooks.json.helix.lock").exists()
    assert configure(tmp_path, tmp_path / "data")["installed"] is True
    assert any(p.read_bytes() == original for p in codex.glob("hooks.json.helix-*.bak"))


def test_existing_cooperative_lock_prevents_config_mutation(tmp_path):
    codex = tmp_path / ".codex"
    codex.mkdir()
    lock = codex / ".hooks.json.helix.lock"
    lock.write_bytes(b"another writer")
    with pytest.raises(SetupRefused, match="cooperative"):
        configure(tmp_path, tmp_path / "data")
    assert lock.read_bytes() == b"another writer"
    assert not (codex / "hooks.json").exists()
