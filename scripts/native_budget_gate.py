#!/usr/bin/env python3
"""Apply an offline token-budget feasibility check to fixed segments.

The check is intentionally limited to arithmetic over the supplied token
counts.  It does not decide whether a candidate is semantically equivalent or
authorize any subsequent work.
"""

from __future__ import annotations

from decimal import Decimal
import json
import math
from pathlib import Path
import sys
from typing import Any


TOP_LEVEL_FIELDS = frozenset(
    {
        "control_input",
        "control_output",
        "segments",
        "fixed_segment_ids",
        "target_input_saving",
        "target_output_saving",
    }
)
SEGMENT_FIELDS = frozenset({"id", "input_tokens", "output_tokens"})


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} keys must be strings")
    return value


def _require_fields(value: dict[str, Any], allowed: frozenset[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"{label} has unknown field(s): {', '.join(unknown)}")
    missing = sorted(allowed - set(value))
    if missing:
        raise ValueError(f"{label} is missing field(s): {', '.join(missing)}")


def _require_integer(value: Any, label: str, *, positive: bool = False) -> int:
    if type(value) is not int:  # bool is an int subclass, but is invalid here.
        raise ValueError(f"{label} must be an integer")
    if positive and value <= 0:
        raise ValueError(f"{label} must be greater than zero")
    if not positive and value < 0:
        raise ValueError(f"{label} must be nonnegative")
    return value


def _fraction(value: Any, label: str) -> tuple[int, int]:
    """Return a finite fraction as an exact nonnegative numerator/denominator."""

    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{label} must be a finite number from 0 to 1")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise ValueError(f"{label} must be a finite number from 0 to 1") from exc
    if not decimal_value.is_finite():
        raise ValueError(f"{label} must be finite")
    numerator, denominator = decimal_value.as_integer_ratio()
    if numerator < 0 or numerator > denominator:
        raise ValueError(f"{label} must be between 0 and 1")
    return numerator, denominator


def _within_target(floor: int, control: int, fraction: tuple[int, int]) -> bool:
    """Compare floor <= control * (1 - fraction) without binary floats."""

    numerator, denominator = fraction
    return floor * denominator <= control * (denominator - numerator)


def assess(data: Any) -> dict[str, Any]:
    """Assess whether fixed token floors rule out the requested savings.

    ``NOT_RULED_OUT`` means the supplied fixed-segment arithmetic does not
    exceed either requested budget ceiling.  It is not an admission decision.
    """

    payload = _require_object(data, "payload")
    _require_fields(payload, TOP_LEVEL_FIELDS, "payload")

    control_input = _require_integer(payload["control_input"], "control_input", positive=True)
    control_output = _require_integer(payload["control_output"], "control_output", positive=True)

    segments_value = payload["segments"]
    if type(segments_value) is not list:
        raise ValueError("segments must be a list")
    segments: dict[str, tuple[int, int]] = {}
    for index, raw_segment in enumerate(segments_value):
        segment = _require_object(raw_segment, f"segments[{index}]")
        _require_fields(segment, SEGMENT_FIELDS, f"segments[{index}]")
        segment_id = segment["id"]
        if not isinstance(segment_id, str) or not segment_id:
            raise ValueError(f"segments[{index}].id must be a nonempty string")
        if segment_id in segments:
            raise ValueError(f"duplicate segment id: {segment_id}")
        input_tokens = _require_integer(segment["input_tokens"], f"segments[{index}].input_tokens")
        output_tokens = _require_integer(segment["output_tokens"], f"segments[{index}].output_tokens")
        segments[segment_id] = (input_tokens, output_tokens)

    fixed_value = payload["fixed_segment_ids"]
    if type(fixed_value) is not list:
        raise ValueError("fixed_segment_ids must be a list")
    fixed_ids: list[str] = []
    seen_fixed: set[str] = set()
    for index, segment_id in enumerate(fixed_value):
        if not isinstance(segment_id, str) or not segment_id:
            raise ValueError(f"fixed_segment_ids[{index}] must be a nonempty string")
        if segment_id in seen_fixed:
            raise ValueError(f"duplicate fixed segment id: {segment_id}")
        if segment_id not in segments:
            raise ValueError(f"unknown fixed segment id: {segment_id}")
        seen_fixed.add(segment_id)
        fixed_ids.append(segment_id)

    input_fraction = _fraction(payload["target_input_saving"], "target_input_saving")
    output_fraction = _fraction(payload["target_output_saving"], "target_output_saving")

    if not fixed_ids:
        return {
            "status": "NOT_RULED_OUT",
            "fixed_segment_ids": [],
            "known_floor": False,
            "conditional_floor": None,
        }

    floor_input = sum(segments[segment_id][0] for segment_id in fixed_ids)
    floor_output = sum(segments[segment_id][1] for segment_id in fixed_ids)
    input_ok = _within_target(floor_input, control_input, input_fraction)
    output_ok = _within_target(floor_output, control_output, output_fraction)
    status = "NOT_RULED_OUT" if input_ok and output_ok else "RULED_OUT_UNDER_FIXED_SEGMENTS"
    return {
        "status": status,
        "fixed_segment_ids": fixed_ids,
        "known_floor": True,
        "conditional_floor": {
            "input_tokens": floor_input,
            "output_tokens": floor_output,
        },
    }


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _load_json(text: str) -> Any:
    return json.loads(
        text,
        object_pairs_hook=_json_object,
        parse_constant=_reject_json_constant,
        parse_float=Decimal,
    )


def _invalid_report(error: Exception) -> dict[str, str]:
    return {"status": "INVALID", "error": str(error)}


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else list(argv)
    if len(arguments) > 1:
        report = _invalid_report(ValueError("expected zero or one JSON input path"))
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 1
    path = arguments[0] if arguments else "-"

    try:
        if path == "-":
            raw = sys.stdin.read()
        else:
            raw = Path(path).read_text(encoding="utf-8")
        report = assess(_load_json(raw))
    except (OSError, UnicodeError, ValueError) as exc:
        report = _invalid_report(exc)
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 1

    print(json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 2 if report["status"] == "RULED_OUT_UNDER_FIXED_SEGMENTS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
