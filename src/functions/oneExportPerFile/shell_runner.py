"""Simple shell command runner used across jedi scripts."""
from __future__ import annotations

import subprocess
from pathlib import Path


def run_cmd(
    cmd: list[str],
    cwd: Path | None = None,
    check: bool = True,
    capture: bool = True,
    env: dict | None = None,
) -> str:
    """Run *cmd* and return stripped stdout.

    Raises ``RuntimeError`` on non-zero exit when *check* is True.
    """
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=capture,
        text=True,
        env=env,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed (exit {result.returncode}): {' '.join(str(c) for c in cmd)}\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
    return result.stdout.strip()
