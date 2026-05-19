from __future__ import annotations

from pathlib import Path
from typing import Protocol

from oneExportPerFile.shell_runner import run_cmd


class _ProgressLike(Protocol):
    def log(self, message: str) -> None: ...

    def log_output(self, label: str, output: str) -> None: ...


def run_opencode(
    repo_root: Path,
    prompt: str,
    progress: _ProgressLike,
) -> None:
    """Invoke the opencode CLI to split remaining multiple exports in *file*."""

    progress.log(f"  Invoking opencode: {prompt}")
    try:
        output = run_cmd(
            ["opencode", "run", prompt],
            cwd=repo_root,
            check=False,
        )
        progress.log("  opencode step completed.")
    except Exception as exc:
        progress.log(f"  opencode error: {exc}")