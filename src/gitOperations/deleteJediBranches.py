#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from gitOperations.branch_manager import (
    BRANCH_PREFIX,
    delete_prefixed_branches,
    list_jedi_worktrees,
    remove_worktree,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Delete all local branches in a target repo that start with the "
            f"configured prefix ('{BRANCH_PREFIX}'), and remove any associated "
            "worktrees that have not yet been cleaned up."
        )
    )
    parser.add_argument("--repo", required=True, help="Target repo root")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repo_root = Path(args.repo).resolve()

    # Remove worktrees first (branches checked out in a worktree cannot be deleted)
    worktrees = list_jedi_worktrees(repo_root)
    removed_wt: list[Path] = []
    for wt in worktrees:
        try:
            remove_worktree(repo_root, wt)
            removed_wt.append(wt)
        except Exception as exc:
            print(f"Warning: could not remove worktree {wt}: {exc}")

    if removed_wt:
        print(f"Removed {len(removed_wt)} worktree(s):")
        for wt in removed_wt:
            print(f"- {wt}")
    else:
        print("No worktrees to remove.")

    deleted, skipped = delete_prefixed_branches(repo_root)

    print(f"\nDeleted {len(deleted)} branch(es) with prefix '{BRANCH_PREFIX}'.")
    for branch in deleted:
        print(f"- {branch}")

    if skipped:
        print("Skipped current branch(es):")
        for branch in skipped:
            print(f"- {branch}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
