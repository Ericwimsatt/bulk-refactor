from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import json


DEFAULT_MODEL_ID = "openrouter/moonshotai/kimi-k2-instruct"
LATEST_KIMI_CODING_MODEL_ID = "openrouter/moonshotai/kimi-k2-instruct"


@dataclass
class WorkflowConfig:
    repo_root: Path
    target_dir: str
    state_dir: Path
    prompt_dir: Path
    model_id: str
    max_files: int
    dry_run: bool


def resolve_model_id(cli_model_id: str | None, use_latest_kimi_coding: bool = False) -> str:
    if cli_model_id:
        return cli_model_id
    if use_latest_kimi_coding:
        return os.getenv("KIMI_CODING_MODEL", LATEST_KIMI_CODING_MODEL_ID)
    return os.getenv("KIMI_MODEL", DEFAULT_MODEL_ID)


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
