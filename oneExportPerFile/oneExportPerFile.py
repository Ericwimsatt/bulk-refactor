#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from blocks.python.config import WorkflowConfig
from blocks.python.refactor_workflow import run_one_export_workflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refactor JS/TS files to one export per file using a deterministic pipeline."
    )
    parser.add_argument("-repo", "--repo", default=".", help="Repo root to refactor")
    parser.add_argument("-dir", "--dir", required=True, help="Target directory inside repo")
    parser.add_argument("--max-files", type=int, default=0, help="Limit number of files (0 = no limit)")
    parser.add_argument("--verbose", action="store_true", help="Print detailed workflow progress")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(__file__).resolve().parent

    cfg = WorkflowConfig(
        repo_root=Path(args.repo).resolve(),
        target_dir=args.dir,
        state_dir=root / "state",
        max_files=args.max_files,
        verbose=args.verbose,
    )

    state_file = run_one_export_workflow(cfg)
    print(f"Process state: {state_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
