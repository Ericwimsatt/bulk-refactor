#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gitOperations.branch_manager import BRANCH_PREFIX, delete_prefixed_branches


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Delete all local branches in a target repo that start with the "
            f"configured prefix ('{BRANCH_PREFIX}')."
        )
    )
    parser.add_argument("--repo", required=True, help="Target repo root")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    deleted, skipped = delete_prefixed_branches(Path(args.repo).resolve())

    print(f"Deleted {len(deleted)} branch(es) with prefix '{BRANCH_PREFIX}'.")
    for branch in deleted:
        print(f"- {branch}")

    if skipped:
        print("Skipped current branch(es):")
        for branch in skipped:
            print(f"- {branch}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
