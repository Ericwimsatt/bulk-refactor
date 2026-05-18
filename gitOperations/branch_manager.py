from __future__ import annotations

from pathlib import Path
import re

from oneExportPerFile.shell_runner import run_cmd

BRANCH_PREFIX = "JediBranch"


def get_current_branch(repo_root: Path) -> str:
    return run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)


def get_git_root(repo_path: Path) -> Path:
    """Return the actual git repository root for any path within the repo."""
    return Path(run_cmd(["git", "rev-parse", "--show-toplevel"], cwd=repo_path))


def ensure_clean_worktree(repo_root: Path) -> None:
    status = run_cmd(["git", "status", "--porcelain", "--untracked-files=no"], cwd=repo_root)
    if status:
        raise RuntimeError(
            "Working tree is not clean. Commit or stash changes before running this workflow."
        )


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug[:40] if slug else "file"


def _worktree_base(repo_root: Path) -> Path:
    """Root directory for all jedi-managed worktrees for the given repo."""
    return repo_root.parent / ".jedi-worktrees" / repo_root.name


def checkout_branch(repo_root: Path, branch: str) -> None:
    run_cmd(["git", "checkout", branch], cwd=repo_root)


def create_branch_with_worktree(repo_root: Path, branch_name: str, base_branch: str) -> Path:
    """Create *branch_name* starting at *base_branch* and attach a git worktree.

    The worktree is placed under ``_worktree_base(repo_root)`` using a
    directory-safe name (``/`` replaced by ``--``).  Returns the worktree path.
    """
    sanitized = branch_name.replace("/", "--")
    worktree_path = _worktree_base(repo_root) / sanitized
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    run_cmd(
        ["git", "worktree", "add", "-b", branch_name, str(worktree_path), base_branch],
        cwd=repo_root,
    )
    return worktree_path


def remove_worktree(repo_root: Path, worktree_path: Path) -> None:
    """Forcibly remove the git worktree at *worktree_path*."""
    run_cmd(["git", "worktree", "remove", "--force", str(worktree_path)], cwd=repo_root)


def list_jedi_worktrees(repo_root: Path, prefix: str = BRANCH_PREFIX) -> list[Path]:
    """Return paths of all worktrees whose checked-out branch starts with *prefix*."""
    # Prune stale entries first so we only see live worktrees.
    run_cmd(["git", "worktree", "prune"], cwd=repo_root)
    output = run_cmd(["git", "worktree", "list", "--porcelain"], cwd=repo_root)
    result: list[Path] = []
    current_path: Path | None = None
    for line in output.splitlines():
        if line.startswith("worktree "):
            current_path = Path(line[len("worktree "):])
        elif line.startswith("branch "):
            branch_ref = line[len("branch "):]
            branch_name = branch_ref.removeprefix("refs/heads/")
            if branch_name.startswith(prefix) and current_path is not None:
                result.append(current_path)
            current_path = None
        elif line == "":
            current_path = None
    return result


def merge_branch(target_wt: Path, source: str) -> str:
    """Merge *source* branch into the branch checked out at *target_wt*.

    Uses ``--no-ff`` to preserve history.  Returns HEAD sha after merge.
    """
    run_cmd(
        ["git", "merge", "--no-ff", source, "-m", f"Merge {source}"],
        cwd=target_wt,
    )
    return run_cmd(["git", "rev-parse", "HEAD"], cwd=target_wt)


def get_staged_diff(repo_root: Path) -> str:
    return run_cmd(["git", "diff", "HEAD"], cwd=repo_root)


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
