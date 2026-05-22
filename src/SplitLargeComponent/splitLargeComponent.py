#!/usr/bin/env python3
"""
splitLargeComponent.py — Split large React components into smaller, reusable components.

Usage:
    python -m SplitLargeComponent.splitLargeComponent \\
        --repo /path/to/manhunt/manhunt-app \\
        --dir app \\
        --components-dir components \\
        --max-files 5 \\
        --verbose

    # Or target a specific file:
    python -m SplitLargeComponent.splitLargeComponent \\
        --repo /path/to/manhunt/manhunt-app \\
        --file app/lobby.tsx \\
        --components-dir components \\
        --verbose

For each .tsx file in the target directory (or the specific file) the script will:
  1. Quick-scan to check whether the file has splitting candidates:
     - Conditional branches that render different JSX sub-trees (admin vs non-admin, etc.)
     - Iteration over a list to produce JSX (.map(...) returning JSX)
  2. If splitting candidates are found, start a parallel opencode agent per file.
  3. The agent extracts the identified sub-trees into new files in the components folder,
     passes appropriate props, and updates the original file to import and use them.
  4. Per-file git branches + worktrees isolate each file's changes.
  5. All per-file branches are optionally merged back to the base branch at the end.

Splitting rules passed to the opencode agent:
  - Split whenever there is a conditional branch where both arms render meaningful JSX
    (e.g. "if admin show AdminControls else show GuestNotice").
  - Split whenever a .map() call returns JSX that is more than ~3 lines.
  - Do NOT create separate components purely for mobile vs desktop styling differences.
    Only extract a component for a specific form factor when that component should be
    entirely absent on the other form factor.
  - Data-fetching patterns should be identical across devices; the same component must
    handle both.
  - Pass props to make extracted components reusable wherever possible.
  - Put new files in the provided components directory.
  - This is an intermediate step toward a unified component library; favour generic,
    prop-driven components over highly specialised one-off components.

Progress is written to jedi/Progress/process_{HHMMSS}_{YYYYMMDD}_{uid}/progress.md.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from gitOperations.branch_manager import (
    BRANCH_PREFIX,
    get_current_branch,
    get_git_root,
    ensure_clean_worktree,
    commit_all,
    create_branch_with_worktree,
    remove_worktree,
    merge_branch,
    get_staged_diff,
)
from oneExportPerFile.runOpenCode import run_opencode
from progressTracker.progressTracker import ProgressTracker


# ── heuristic scanner ─────────────────────────────────────────────────────────

# Matches JSX map patterns: something.map(( or something.map(item =>
_MAP_JSX_RE = re.compile(
    r"\.map\s*\(\s*(?:\([^)]*\)|[a-zA-Z_$][a-zA-Z0-9_$]*)\s*(?:=>|,)",
)

# Matches conditional JSX rendering patterns:
#   - ternary with JSX:  condition ? (<...  OR  condition ? <...
#   - short-circuit:     condition && (<  OR  condition && <
#   - if (...) { return (<  inside a component function
_CONDITIONAL_JSX_RE = re.compile(
    r"(?:"
    r"\?\s*[\(\<]"             # ternary true branch opening JSX
    r"|&&\s*[\(\<]"            # short-circuit rendering
    r"|if\s*\([^)]*\)\s*\{"   # if statement block (likely conditional render)
    r")",
)

# Minimum line-count threshold for a file to be considered "large"
_MIN_LINES_THRESHOLD = 30


def is_split_candidate(content: str, path: Path) -> tuple[bool, list[str]]:
    """Return (is_candidate, reasons) for a TSX file.

    A file is a candidate if it contains JSX and has at least one of:
      - A .map() call that returns JSX
      - Conditional rendering of non-trivial JSX sub-trees
      - More than _MIN_LINES_THRESHOLD lines (general complexity indicator)
    """
    reasons: list[str] = []

    # Must be a React component file (contains JSX)
    if "<" not in content or "return" not in content:
        return False, []

    # Must be long enough to bother splitting
    lines = content.splitlines()
    if len(lines) < _MIN_LINES_THRESHOLD:
        return False, []

    if _MAP_JSX_RE.search(content):
        reasons.append("contains .map() with JSX iteration")

    conditional_matches = _CONDITIONAL_JSX_RE.findall(content)
    if len(conditional_matches) >= 2:
        reasons.append(f"contains {len(conditional_matches)} conditional JSX branches")

    return bool(reasons), reasons


# ── data structures ───────────────────────────────────────────────────────────


@dataclass
class AgentTodo:
    """An opencode task for a single component file."""

    file: Path
    file_wt: Path
    rel: Path          # relative to git_root = relative to file_wt (for worktree paths and prompts)
    rel_repo: Path     # relative to repo_root (for display only)
    repo_subdir: Path  # repo_root.relative_to(git_root); the subdir within the worktree
    reasons: list[str]
    components_dir_rel: str  # relative path from repo root to components dir


@dataclass
class FileBranchData:
    """Tracks the per-file branch created in pass 1, used for merge & cleanup."""

    file: Path
    file_branch: str
    file_wt: Path


# ── per-file processing ───────────────────────────────────────────────────────


def prepare_file(
    file: Path,
    repo_root: Path,
    git_root: Path,
    main_branch: str,
    main_wt: Path,
    run_prefix: str,
    components_dir_rel: str,
    args: argparse.Namespace,
    progress: ProgressTracker,
    summary: dict,
    summary_lock: threading.Lock,
) -> tuple[FileBranchData | None, AgentTodo | None]:
    """Scan a file and create its branch/worktree if it's a candidate.

    Returns (FileBranchData, AgentTodo) or (None, None) if skipped.

    git_root may differ from repo_root when --repo targets a subdirectory;
    worktrees always mirror the git root structure.
    """
    progress.section(f"File: {file.name}")
    # Two relative paths: one for worktree addressing, one for prompts
    rel = file.relative_to(git_root)       # used to access file inside worktree
    rel_repo = file.relative_to(repo_root)  # used in prompts (more readable)
    repo_subdir = repo_root.relative_to(git_root)  # e.g. "manhunt-app"  (empty if same)

    content = (main_wt / rel).read_text(encoding="utf-8")
    is_candidate, reasons = is_split_candidate(content, file)

    if not is_candidate:
        progress.log(f"No splitting candidates found — skipping.")
        with summary_lock:
            summary["skipped"] += 1
        return None, None

    for reason in reasons:
        progress.log(f"  Candidate reason: {reason}")

    # Create per-file branch + worktree
    file_branch = f"{run_prefix}/{file.stem}"
    file_wt = create_branch_with_worktree(repo_root, file_branch, main_branch)
    progress.log(f"  Created file branch: {file_branch} (worktree: {file_wt})")

    file_branch_data = FileBranchData(file=file, file_branch=file_branch, file_wt=file_wt)
    todo = AgentTodo(
        file=file,
        file_wt=file_wt,
        rel=rel,
        rel_repo=rel_repo,
        repo_subdir=repo_subdir,
        reasons=reasons,
        components_dir_rel=components_dir_rel,
    )
    return file_branch_data, todo


# ── opencode prompt ───────────────────────────────────────────────────────────

PROMPT_TEMPLATE = """\
You are refactoring the file `{abs_file}` in a TypeScript/React Native project.

The automated scanner flagged this file for component splitting because:
{reasons_list}

Your task — Component Extraction:
1. Identify JSX sub-trees that should become their own components:
   a. Any conditional branch where BOTH arms render meaningful JSX (e.g. admin panel vs
      guest notice). Create a separate component for each arm OR a unified component that
      accepts a prop to toggle the variant.
   b. Any `.map()` call that returns JSX longer than ~3 lines. Extract the item renderer
      into its own component (e.g. `PlayerRow`, `TeamCard`).
2. Create each new component as its OWN file in the directory `{abs_components_dir}`.
   - Name the file after the component (PascalCase, e.g. `AdminControls.tsx`).
   - Each new file must export EXACTLY ONE component.
3. Pass props to make the extracted components reusable:
   - Prefer generic, prop-driven designs over one-off specialised components.
   - Do NOT hard-code data that can be passed as a prop.
4. IMPORTANT — do NOT split for mobile/desktop differences:
   - Keep identical data-fetching hooks in the same component regardless of device.
   - Only extract a platform-specific component when it must be ENTIRELY ABSENT on the
     other platform (e.g. a map overlay that only exists on native).
5. Update `{abs_file}` to import and render the new components using relative import paths.
6. Do NOT modify any files outside of `{abs_components_dir}` and `{abs_file}`.
7. Do NOT commit any changes — leave them as uncommitted edits.
8. Output a brief summary listing every new file created and every existing file modified.

Keep the original component's overall logic and data-fetching unchanged. You are only
extracting pieces of the JSX render tree into dedicated component files.
"""


def split_component(
    todo: AgentTodo,
    progress: ProgressTracker,
    summary: dict,
    summary_lock: threading.Lock,
) -> None:
    """Run the opencode pass for a single file. Designed to run in a thread pool."""
    file = todo.file
    file_wt = todo.file_wt
    rel = todo.rel
    rel_repo = todo.rel_repo
    repo_subdir = todo.repo_subdir
    reasons = todo.reasons
    components_dir_rel = todo.components_dir_rel

    # Use absolute paths in the prompt so opencode writes to the worktree
    # rather than its session's original project root.  Since we pass
    # external_directory:allow via OPENCODE_CONFIG_CONTENT, opencode can
    # freely read/write any absolute path.
    abs_file = file_wt / rel
    abs_components_dir = file_wt / repo_subdir / components_dir_rel

    progress.section(f"OpenCode: {file.name}")

    reasons_list = "\n".join(f"  - {r}" for r in reasons)
    prompt = PROMPT_TEMPLATE.format(
        abs_file=abs_file,
        abs_components_dir=abs_components_dir,
        reasons_list=reasons_list,
    )
    progress.log(f"  opencode cwd: {file_wt}")
    progress.log(f"  abs file path in prompt: {abs_file}")
    progress.log(f"  abs components dir in prompt: {abs_components_dir}")

    run_opencode(file_wt, prompt, progress)

    # Commit whatever opencode changed.  If opencode made no changes on the first
    # call (it occasionally needs a "warm-up" call to initialise its project session
    # for a new worktree), retry once before giving up.
    sha = commit_all(file_wt, f"Split large component in {file.name} via opencode")
    if not sha:
        progress.log("  No changes after first opencode call — retrying once…")
        run_opencode(file_wt, prompt, progress)
        diff = get_staged_diff(file_wt)
        sha = commit_all(file_wt, f"Split large component in {file.name} via opencode (retry)")
    else:
        diff = get_staged_diff(file_wt)

    if sha:
        progress.log(f"  Committed opencode changes — {sha}")
        progress.log_diff(diff)
    else:
        progress.log(
            "  No uncommitted changes after opencode (may have self-committed or no changes)."
        )

    with summary_lock:
        summary["opencode_used"] = summary.get("opencode_used", 0) + 1
        summary["split"] += 1

    progress.log(f"Done with {file.name}.")


# ── orchestrator ──────────────────────────────────────────────────────────────


def process_all_files(
    files: list[Path],
    repo_root: Path,
    git_root: Path,
    main_branch: str,
    main_wt: Path,
    run_prefix: str,
    components_dir_rel: str,
    args: argparse.Namespace,
    progress: ProgressTracker,
    summary: dict,
    summary_lock: threading.Lock,
) -> list[FileBranchData]:

    # ── phase 1: scan + create branches (sequential) ─────────────────────────
    progress.section("Phase 1: Scanning files for split candidates")
    file_branch_datas: list[FileBranchData] = []
    agent_todos: list[AgentTodo] = []

    for file in files:
        try:
            file_branch_data, todo = prepare_file(
                file,
                repo_root,
                git_root,
                main_branch,
                main_wt,
                run_prefix,
                components_dir_rel,
                args,
                progress,
                summary,
                summary_lock,
            )
            if file_branch_data is not None:
                file_branch_datas.append(file_branch_data)
            if todo is not None:
                agent_todos.append(todo)
        except Exception as exc:
            progress.log(f"ERROR preparing {file.name}: {exc}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            with summary_lock:
                summary["errors"] += 1

    if not agent_todos:
        progress.log("No split candidates found — nothing to do.")
        return file_branch_datas

    # ── phase 2: parallel opencode ────────────────────────────────────────────
    max_workers = min(len(agent_todos), os.cpu_count() or 4)
    progress.section(
        f"Phase 2: Parallel OpenCode ({len(agent_todos)} tasks, {max_workers} workers)"
    )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                split_component,
                todo,
                progress,
                summary,
                summary_lock,
            ): todo
            for todo in agent_todos
        }
        for future in as_completed(futures):
            todo = futures[future]
            try:
                future.result()
            except Exception as exc:
                progress.log(f"ERROR in opencode for {todo.file.name}: {exc}")
                if args.verbose:
                    import traceback
                    traceback.print_exc()
                with summary_lock:
                    summary["errors"] += 1

    return file_branch_datas


# ── CLI ───────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Split large React components into smaller reusable components.",
    )
    target = p.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--dir",
        metavar="DIR",
        help="Directory (relative to --repo) whose .tsx files will be processed.",
    )
    target.add_argument(
        "--file",
        metavar="FILE",
        help="Single file (relative to --repo) to process.",
    )
    p.add_argument(
        "--repo",
        required=True,
        metavar="PATH",
        help="Path to the root of the target repository.",
    )
    p.add_argument(
        "--components-dir",
        required=True,
        metavar="DIR",
        help="Directory (relative to --repo) where new component files should be placed.",
    )
    p.add_argument(
        "--max-files",
        type=int,
        default=None,
        metavar="N",
        help="Process at most N files (useful for dry-run testing).",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Print progress to stdout in addition to the log file.",
    )
    p.add_argument(
        "--merge-file-branches",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Merge each per-file branch back to the main branch after processing (default: on)",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()
    repo_root = Path(args.repo).resolve()

    # Collect target files
    if args.file:
        target_path = repo_root / args.file
        if not target_path.is_file():
            print(f"Error: '{target_path}' is not a file.", file=sys.stderr)
            return 1
        files: list[Path] = [target_path]
        target_label = str(args.file)
    else:
        target_dir = repo_root / args.dir
        if not target_dir.is_dir():
            print(f"Error: '{target_dir}' is not a directory.", file=sys.stderr)
            return 1
        files = sorted(target_dir.glob("*.tsx"))
        target_label = args.dir

    if args.max_files is not None:
        files = files[: args.max_files]

    # Validate components dir
    components_dir_full = repo_root / args.components_dir
    if not components_dir_full.is_dir():
        print(f"Error: components dir '{components_dir_full}' is not a directory.", file=sys.stderr)
        return 1

    # ── initialise progress tracker ───────────────────────────────────────────
    progress = ProgressTracker(run_name="SplitLargeComponent", verbose=args.verbose)
    progress.log(f"repo:              {repo_root}")
    progress.log(f"target:            {target_label}")
    progress.log(f"components-dir:    {args.components_dir}")
    progress.log(f"max-files:         {args.max_files}")
    progress.log(f"merge-file-branches: {args.merge_file_branches}")
    progress.log(f"Progress log: {progress.log_file}")

    # ── assert clean working tree ─────────────────────────────────────────────
    original_branch = get_current_branch(repo_root)
    try:
        ensure_clean_worktree(repo_root)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Resolve actual git root (may differ when --repo targets a subdirectory)
    git_root = get_git_root(repo_root)
    progress.log(f"Original branch: {original_branch}")
    progress.log(f"Git root:        {git_root}")

    # ── create main base branch + worktree ───────────────────────────────────
    stamp = datetime.now(timezone.utc).strftime("%H%M%S-%Y%m%d")
    run_prefix = f"{BRANCH_PREFIX}/SplitLargeComponent/{stamp}"
    main_branch = f"{run_prefix}/base"
    main_wt = create_branch_with_worktree(repo_root, main_branch, original_branch)
    progress.log(f"Main branch:     {main_branch}")
    progress.log(f"Main worktree:   {main_wt}")

    summary: dict[str, int] = {
        "total_files": len(files),
        "skipped": 0,
        "split": 0,
        "merged": 0,
        "errors": 0,
        "opencode_used": 0,
    }
    summary_lock = threading.Lock()

    file_branch_datas = process_all_files(
        files,
        repo_root,
        git_root,
        main_branch,
        main_wt,
        run_prefix,
        args.components_dir,
        args,
        progress,
        summary,
        summary_lock,
    )

    # ── phase 3: merge all file branches back to main ────────────────────────
    if args.merge_file_branches and file_branch_datas:
        progress.section("Phase 3: Merging all file branches")
        for branch_data in file_branch_datas:
            try:
                sha = merge_branch(main_wt, branch_data.file_branch, source_wt=branch_data.file_wt)
                progress.log(f"Merged {branch_data.file_branch} → {main_branch} (sha: {sha})")
                with summary_lock:
                    summary["merged"] += 1
            except Exception as exc:
                progress.log(f"ERROR merging {branch_data.file_branch}: {exc}")
                if args.verbose:
                    import traceback
                    traceback.print_exc()
                with summary_lock:
                    summary["errors"] += 1

    # ── phase 4: cleanup main worktree ────────────────────────────────────────
    progress.section("Phase 4: Cleanup")
    try:
        remove_worktree(repo_root, main_wt)
        progress.log(f"Removed main worktree: {main_wt}")
    except Exception as exc:
        progress.log(f"Warning: could not remove main worktree {main_wt}: {exc}")

    # ── final summary ─────────────────────────────────────────────────────────
    progress.section("Summary")
    for k, v in summary.items():
        progress.log(f"{k}: {v}")

    print()
    print("╔═══════════════════════════════════════════════╗")
    print("║      SplitLargeComponent — complete           ║")
    print("╠═══════════════════════════════════════════════╣")
    print(f"║  Files examined:     {summary['total_files']:<26} ║")
    print(f"║  Skipped (no split): {summary['skipped']:<26} ║")
    print(f"║  Split:              {summary['split']:<26} ║")
    print(f"║  Used opencode:      {summary['opencode_used']:<26} ║")
    print(f"║  Branches merged:    {summary['merged']:<26} ║")
    print(f"║  Errors:             {summary['errors']:<26} ║")
    print("╠═══════════════════════════════════════════════╣")
    print(f"║  Main branch: {main_branch[-33:]:<33} ║")
    print("╚═══════════════════════════════════════════════╝")
    print(f"\nProgress log: {progress.log_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
