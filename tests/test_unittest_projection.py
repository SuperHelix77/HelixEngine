import json
import sys

from helixengine.core.evidence import reduce_stream
from helixengine.runtime import Runtime


def test_generic_keeps_unittest_counts_and_failure_locations():
    raw = (
        b"F.E\r\n===\r\nFAIL: test_order (suite.Check)\r\nAssertionError\r\n"
        b"===\r\nERROR: test_invalid (suite.Check)\r\nValueError\r\n"
        b"---\r\nRan 3 tests in 0.002s\r\n\r\nFAILED (failures=1, errors=1)\r\n"
    )
    view = reduce_stream(raw, "generic")
    assert view["summary_candidates"] == [
        {"line": 9, "text": "Ran 3 tests in 0.002s"},
        {"line": 11, "text": "FAILED (failures=1, errors=1)"},
    ]
    assert view["failure_section_index"] == [
        {"start": 3, "end": 5, "header": "FAIL: test_order (suite.Check)"},
        {"start": 6, "end": 11, "header": "ERROR: test_invalid (suite.Check)"},
    ]
    assert view["projection_only"] is True


def test_unittest_projection_discloses_omitted_failure_sections():
    raw = b"\n".join(f"FAIL: test_{i} (suite.Check)".encode() for i in range(12))
    view = reduce_stream(raw + b"\nRan 12 tests in 0.1s\nFAILED (failures=12)\n", "generic")
    assert len(view["failure_section_index"]) == 8
    assert view["failure_sections_omitted"] == 4
    assert view["diagnostic_lines_omitted"] == 5  # twelve labels plus FAILED
    assert view["summary_candidates"][-1]["text"] == "FAILED (failures=12)"


def test_enabled_runtime_delivers_real_unittest_failure_summary(tmp_path):
    code = '''import unittest
class Check(unittest.TestCase):
    def test_one(self): self.fail('long diagnostic ' * 600)
    def test_two(self): self.fail('second failure')
unittest.main()
'''
    runtime = Runtime(tmp_path / "engine")
    try:
        assert runtime.settings()["enabled"] is True
        result = runtime.run([sys.executable, "-c", code], tmp_path, kind="generic")
        assert result["exit_code"] == 1
        assert result["run"]["enabled"] is True
        visible, err = runtime.visible_output(result)
        assert err == b""
        assert result["run"]["reducer_status"] == "REDUCED"
        packet = json.loads(visible)
        stderr = packet["streams"]["stderr"]
        assert any(row["text"].startswith("Ran 2 tests in ") for row in stderr["summary_candidates"])
        assert stderr["summary_candidates"][-1]["text"] == "FAILED (failures=2)"
        assert len(stderr["failure_section_index"]) == 2
        # Exact diagnostics remain recoverable, including omitted long text.
        receipt = runtime.store.receipt(result["receipt"])
        exact = runtime.store.get(receipt["stderr"]["sha256"])
        assert exact == result["stderr"]
        assert b"long diagnostic " * 600 in exact
    finally:
        runtime.close()
