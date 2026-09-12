import json
from pathlib import Path
import runpy
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "native_budget_gate.py"
assess = runpy.run_path(str(SCRIPT))["assess"]


def payload(**overrides):
    value = {
        "control_input": 5,
        "control_output": 10,
        "segments": [
            {"id": "a", "input_tokens": 1, "output_tokens": 2},
            {"id": "b", "input_tokens": 2, "output_tokens": 3},
        ],
        "fixed_segment_ids": ["a"],
        "target_input_saving": 0.8,
        "target_output_saving": 0.5,
    }
    value.update(overrides)
    return value


def test_assess_returns_conditional_floor_and_not_ruled_out_at_exact_boundary():
    result = assess(payload(fixed_segment_ids=["a", "b"], target_input_saving=0.4, target_output_saving=0.5))

    assert result == {
        "status": "NOT_RULED_OUT",
        "fixed_segment_ids": ["a", "b"],
        "known_floor": True,
        "conditional_floor": {"input_tokens": 3, "output_tokens": 5},
    }


def test_decimal_boundary_uses_exact_arithmetic_instead_of_binary_float():
    result = assess(payload(target_input_saving=0.8, target_output_saving=0.5))

    assert result["status"] == "NOT_RULED_OUT"
    assert result["conditional_floor"]["input_tokens"] == 1


def test_any_axis_over_budget_rules_out_under_fixed_segments():
    result = assess(payload(target_input_saving=0.4, target_output_saving=0.9))

    assert result["status"] == "RULED_OUT_UNDER_FIXED_SEGMENTS"
    assert result["conditional_floor"] == {"input_tokens": 1, "output_tokens": 2}


def test_empty_fixed_set_is_allowed_but_has_no_known_floor():
    result = assess(payload(fixed_segment_ids=[]))

    assert result == {
        "status": "NOT_RULED_OUT",
        "fixed_segment_ids": [],
        "known_floor": False,
        "conditional_floor": None,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("control_input", True),
        ("control_output", 0),
        ("segments", {"id": "a"}),
        ("fixed_segment_ids", "a"),
        ("target_input_saving", float("nan")),
        ("target_output_saving", float("inf")),
    ],
)
def test_malformed_values_are_rejected(field, value):
    with pytest.raises(ValueError):
        assess(payload(**{field: value}))


@pytest.mark.parametrize(
    "bad_payload",
    [
        payload(segments=[{"id": "a", "input_tokens": 1, "output_tokens": 2}, {"id": "a", "input_tokens": 0, "output_tokens": 0}]),
        payload(fixed_segment_ids=["a", "a"]),
        payload(fixed_segment_ids=["missing"]),
        payload(extra=True),
        payload(segments=[{"id": "a", "input_tokens": 1, "output_tokens": 2, "extra": 0}]),
    ],
)
def test_duplicate_unknown_and_unresolved_fields_are_rejected(bad_payload):
    with pytest.raises(ValueError):
        assess(bad_payload)


@pytest.mark.parametrize(
    ("target_input_saving", "target_output_saving", "expected"),
    [
        (0, 0, "NOT_RULED_OUT"),
        (1, 1, "RULED_OUT_UNDER_FIXED_SEGMENTS"),
        (0.4, 0.5, "NOT_RULED_OUT"),
    ],
)
def test_fraction_boundaries(target_input_saving, target_output_saving, expected):
    assert assess(
        payload(
            target_input_saving=target_input_saving,
            target_output_saving=target_output_saving,
        )
    )["status"] == expected


def run_cli(raw: str, *args: str):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=raw,
        text=True,
        capture_output=True,
        check=False,
    )


def test_cli_reads_stdin_and_returns_exit_zero_for_not_ruled_out():
    result = run_cli(json.dumps(payload()))

    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "NOT_RULED_OUT"
    assert result.stderr == ""


def test_cli_reads_file_and_returns_exit_two_for_ruled_out(tmp_path):
    path = tmp_path / "gate.json"
    path.write_text(json.dumps(payload(target_input_saving=0.9)), encoding="utf-8")

    result = run_cli("", str(path))

    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "RULED_OUT_UNDER_FIXED_SEGMENTS"
    assert result.stderr == ""


def test_cli_returns_exit_one_and_json_report_for_invalid_json():
    result = run_cli("{not json")

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["status"] == "INVALID"
    assert report["error"]
    assert result.stderr == ""


def test_cli_preserves_decimal_just_above_equality():
    # Rounding to float would turn this into 0.8 and incorrectly admit floor=1.
    raw = json.dumps(payload()).replace('0.8', '0.800000000000000000000000000001')
    result = run_cli(raw)
    assert result.returncode == 2
    assert json.loads(result.stdout)['status'] == 'RULED_OUT_UNDER_FIXED_SEGMENTS'
