from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol

from functions.oneExportPerFile.shell_runner import run_cmd


class _ProgressLike(Protocol):
    def log(self, message: str) -> None: ...

    def log_output(self, label: str, output: str) -> None: ...


def run_opencode(
    repo_root: Path,
    prompt: str,
    progress: _ProgressLike,
) -> None:
    """Invoke the opencode CLI to split remaining multiple exports in *file*."""

    progress.log(f"  Invoking opencode: {prompt[:120]}...")
    # Allow opencode to access paths outside its session's project root.
    # By default, external_directory permission defaults to "ask", which
    # auto-rejects in non-interactive (no-TTY) mode.  Override it to "allow".
    _config = json.dumps({"permission": {"external_directory": "allow"}})
    # Opencode installs to ~/.opencode/bin which may not be on the subprocess
    # PATH (non-interactive shell).  Prepend it so "opencode" resolves correctly.
    _path = str(Path.home() / ".opencode" / "bin") + ":" + os.environ.get("PATH", "")
    _env = {**os.environ, "OPENCODE_CONFIG_CONTENT": _config, "PATH": _path}
    try:
        output = run_cmd(
            ["opencode", "run", prompt],
            cwd=repo_root,
            check=False,
            env=_env,
        )
        progress.log("  opencode step completed.")
        if output:
            progress.log_output("opencode output", output)
    except Exception as exc:
        progress.log(f"  opencode error: {exc}")