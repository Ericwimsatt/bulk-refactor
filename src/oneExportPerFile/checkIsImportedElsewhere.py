from __future__ import annotations

import re
from pathlib import Path

from oneExportPerFile.shell_runner import run_cmd


def is_imported_elsewhere(name: str, repo_root: Path, exclude_file: Path) -> bool:
    """Return True if *name* appears in an import or re-export outside *exclude_file*."""
    src_dir = repo_root / "src"
    try:
        hits_raw = run_cmd(
            [
                "grep",
                "-rl",
                "--include=*.ts",
                "--include=*.tsx",
                f"\\b{name}\\b",
                str(src_dir),
            ],
            cwd=repo_root,
            check=False,
        )
    except Exception:
        return False

    for hit_path_str in hits_raw.splitlines():
        candidate = Path(hit_path_str).resolve()
        if candidate == exclude_file.resolve():
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue

        if re.search(
            rf"(?:import|export)\b[^;]*\b{re.escape(name)}\b",
            text,
        ):
            return True

    return False