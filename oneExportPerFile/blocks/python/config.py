from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json


@dataclass
class WorkflowConfig:
    repo_root: Path
    target_dir: str
    state_dir: Path
    max_files: int
    verbose: bool


def detect_typecheck_command(repo_root: Path) -> list[str] | None:
    package_json = repo_root / "package.json"
    if package_json.exists():
        try:
            pkg = json.loads(package_json.read_text(encoding="utf-8"))
            scripts = pkg.get("scripts", {}) if isinstance(pkg, dict) else {}
            if isinstance(scripts, dict) and "typecheck" in scripts:
                return ["npm", "run", "typecheck"]
        except Exception:
            return None

    tsconfig = repo_root / "tsconfig.json"
    if tsconfig.exists():
        return ["npx", "tsc", "--noEmit"]

    return None
