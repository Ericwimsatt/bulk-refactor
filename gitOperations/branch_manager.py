from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path
import re
import sys

ONE_EXPORT_ROOT = Path(__file__).resolve().parents[1] / "oneExportPerFile"
if str(ONE_EXPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(ONE_EXPORT_ROOT))

from blocks.python.shell_runner import run_cmd

BRANCH_PREFIX = "JediBranch"


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
    name = f"{BRANCH_PREFIX}/one-export/{stamp}-{_slug(target_file)}"
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


def list_prefixed_branches(repo_root: Path, prefix: str = BRANCH_PREFIX) -> list[str]:
    branches = run_cmd(
        ["git", "for-each-ref", "--format=%(refname:short)", "refs/heads"], cwd=repo_root
    )
    return [branch for branch in branches.splitlines() if branch.startswith(prefix)]


def delete_prefixed_branches(repo_root: Path, prefix: str = BRANCH_PREFIX) -> tuple[list[str], list[str]]:
    current_branch = get_current_branch(repo_root)
    candidates = list_prefixed_branches(repo_root, prefix=prefix)

    if current_branch in candidates:
        checkout_branch(repo_root, "main")

    deleted: list[str] = []
    skipped: list[str] = []

    for branch in candidates:
        run_cmd(["git", "branch", "-D", branch], cwd=repo_root)
        deleted.append(branch)

    return deleted, skipped
