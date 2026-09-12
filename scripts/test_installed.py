#!/usr/bin/env python3
"""Verify that the installed distribution is used from outside the checkout."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def _environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def _run(command: list[str], *, cwd: Path, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _assert_outside_source(module_file: Path) -> None:
    resolved_root = ROOT.resolve()
    try:
        module_file.relative_to(resolved_root)
    except ValueError:
        pass
    else:
        raise SystemExit(f"installed module unexpectedly resolves inside checkout: {module_file}")
    if not any(part in {"site-packages", "dist-packages"} for part in module_file.parts):
        raise SystemExit(f"installed module is not in site-packages/dist-packages: {module_file}")


def main() -> int:
    environment = _environment()
    with tempfile.TemporaryDirectory(prefix="helixengine-installed-") as temporary:
        outside = Path(temporary)
        probe = _run(
            [
                sys.executable,
                "-c",
                "import helixengine, json; print(json.dumps({'module_file': helixengine.__file__, 'version': helixengine.__version__}))",
            ],
            cwd=outside,
            environment=environment,
        )
        payload = json.loads(probe.stdout.strip())
        module_file = Path(payload["module_file"]).resolve()
        _assert_outside_source(module_file)
        if payload.get("version") != "0.1.0":
            raise SystemExit(f"unexpected installed version: {payload.get('version')!r}")

        executable_names = ("helixengine.exe", "helixengine") if os.name == "nt" else ("helixengine",)
        # Venv Python may be a symlink to the base interpreter.  The console
        # script is beside the venv path, so do not resolve that symlink.
        bin_dir = Path(sys.executable).parent
        console_path = next((bin_dir / name for name in executable_names if (bin_dir / name).is_file()), None)
        if console_path is None:
            raise SystemExit(f"installed console entry point not found beside {sys.executable}")
        help_result = _run([str(console_path), "--help"], cwd=outside, environment=environment)
        if "usage:" not in help_result.stdout.lower():
            raise SystemExit(f"console help did not contain usage:\n{help_result.stdout}")

        _run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--import-mode=importlib",
                str(ROOT / "tests"),
            ],
            cwd=outside,
            environment=environment,
        )

    print(json.dumps({"installed_module": str(module_file), "console": str(console_path), "outside": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
