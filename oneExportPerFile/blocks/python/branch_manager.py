from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path
import re

from .shell_runner import run_cmd


def get_current_branch(repo_root: Path) -> str:
    return run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)


def ensure_clean_worktree(repo_root: Path) -> None:
    status = run_cmd(["git", "status", "--porcelain"], cwd=repo_root)
    if status:
        raise RuntimeError(
            "Working tree is not clean. Commit or stash changes before running this workflow."
        )


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug[:40] if slug else "file"


def create_branch(repo_root: Path, base_branch: str, target_file: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    name = f"one-export/{stamp}-{_slug(target_file)}"
    run_cmd(["git", "checkout", base_branch], cwd=repo_root)
    run_cmd(["git", "checkout", "-b", name], cwd=repo_root)
    return name


def checkout_branch(repo_root: Path, branch: str) -> None:
    run_cmd(["git", "checkout", branch], cwd=repo_root)


def commit_all(repo_root: Path, message: str) -> str | None:
    run_cmd(["git", "add", "-A"], cwd=repo_root)
    diff = run_cmd(["git", "diff", "--cached", "--name-only"], cwd=repo_root)
    if not diff:
        return None
    run_cmd(["git", "commit", "-m", message], cwd=repo_root)
    return run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_root)
