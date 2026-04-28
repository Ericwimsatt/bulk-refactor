#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from blocks.python.config import WorkflowConfig, resolve_model_id
from blocks.python.refactor_workflow import run_one_export_workflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refactor JS/TS files to one export per file using a smolagents Kimi agent."
    )
    parser.add_argument("-repo", "--repo", default=".", help="Repo root to refactor")
    parser.add_argument("-dir", "--dir", required=True, help="Target directory inside repo")
    parser.add_argument(
        "--model-id",
        default=None,
        help="LiteLLM model id. Defaults to $KIMI_MODEL or openrouter/moonshotai/kimi-k2-instruct",
    )
    parser.add_argument(
        "--latest-kimi-coding",
        action="store_true",
        help="Use the latest Kimi coding model preset ($KIMI_CODING_MODEL or built-in default).",
    )
    parser.add_argument("--max-files", type=int, default=0, help="Limit number of files (0 = no limit)")
    parser.add_argument("--dry-run", action="store_true", help="Only build state + candidates")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(__file__).resolve().parent

    cfg = WorkflowConfig(
        repo_root=Path(args.repo).resolve(),
        target_dir=args.dir,
        state_dir=root / "state",
        prompt_dir=root / "blocks" / "prompts",
        model_id=resolve_model_id(args.model_id, use_latest_kimi_coding=args.latest_kimi_coding),
        max_files=args.max_files,
        dry_run=args.dry_run,
    )

    state_file = run_one_export_workflow(cfg)
    print(f"Process state: {state_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
