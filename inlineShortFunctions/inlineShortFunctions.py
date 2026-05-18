#!/usr/bin/env python3
"""
inlineShortFunctions.py — Inline exported functions that are only used in one other file.

Usage:
    python -m inlineShortFunctions.inlineShortFunctions \\
        --repo /path/to/repo \\
        --dir src/lib \\
        --short-threshold 3 \\
        --max-files 10 \\
        --verbose

For each exported function in the target directory that is imported by exactly
one other file:
  1. If the function body is ≤ --short-threshold non-blank lines:
       a. Try to inline it deterministically (simple expression-body functions).
       b. Fall back to opencode if the body is too complex to copy-paste safely.
  2. If the function body is > --short-threshold lines:
       Defer directly to opencode with a targeted prompt.

Git workflow mirrors oneExportPerFile:
  - A base branch + worktree is created for the run.
  - Each source file gets its own per-file branch + worktree.
  - All per-file branches are merged back to the base branch at the end.
  - Progress is written to jedi/Progress/process_{HHMMSS}_{YYYYMMDD}_{uid}/progress.md.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

JEDI_ROOT = Path(__file__).resolve().parents[1]

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
from inlineShortFunctions.findSingleUseExports import (
    FunctionTarget,
    find_single_use_exports,
    extract_function_bounds,
)


# ── progress tracker (mirrors oneExportPerFile) ───────────────────────────────


class ProgressTracker:
    """Append-only progress log written to jedi/Progress/process_{ts}_{uid}/progress.md."""

    def __init__(self, jedi_root: Path, verbose: bool = False) -> None:
        ts = datetime.now(timezone.utc).strftime("%H%M%S_%Y%m%d")
        uid = uuid.uuid4().hex[:8]
        self.run_dir = jedi_root / "Progress" / f"process_{ts}_{uid}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.run_dir / "progress.md"
        self.verbose = verbose
        self._lock = threading.Lock()
        self._write(
            f"# inlineShortFunctions run\n\n"
            f"Started: {datetime.now(timezone.utc).isoformat()}\n\n"
        )

    def _write(self, text: str) -> None:
        with self._lock:
            with self.log_file.open("a", encoding="utf-8") as fh:
                fh.write(text)

    def log(self, message: str) -> None:
        if self.verbose:
            print(message)
        self._write(f"- {message}\n")

    def section(self, title: str) -> None:
        if self.verbose:
            print(f"\n=== {title} ===")
        self._write(f"\n## {title}\n\n")

    def log_diff(self, diff: str) -> None:
        if not diff:
            return
        self._write(f"\n```diff\n{diff}\n```\n\n")

    def log_output(self, label: str, output: str) -> None:
        if self.verbose and output:
            print(f"[{label}]:\n{output}")
        if output:
            self._write(f"\n### {label}\n\n```\n{output}\n```\n\n")


# ── data structures ───────────────────────────────────────────────────────────


@dataclass
class AgentTodo:
    """An opencode task for a single FunctionTarget."""

    target: FunctionTarget
    source_wt_file: Path   # path to source file inside the worktree
    caller_wt_file: Path   # path to caller file inside the worktree
    wt_root: Path          # worktree root
    repo_root: Path        # original repo root (for relative path computation)


@dataclass
class FileResult:
    """Tracks the per-file branch created for merging."""

    source_file: Path
    file_branch: str
    file_wt: Path


# ── deterministic inlining ────────────────────────────────────────────────────


def _try_deterministic_inline(
    target: FunctionTarget,
    source_wt_file: Path,
    caller_wt_file: Path,
    progress: ProgressTracker,
) -> bool:
    """Attempt to inline a short function without opencode.

    Returns True if inlining succeeded, False to fall through to opencode.

    Handles two simple patterns deterministically:
      1. Expression-body arrow:  export const name = (p) => expr
         Replace `name(arg)` with the expression (with param substituted if trivial).
      2. Single-statement body: export function name() { return expr; }
         with ZERO parameters — replace `name()` with `(expr)`.

    Anything more complex returns False.
    """
    content = source_wt_file.read_text(encoding="utf-8")
    bounds = extract_function_bounds(content, target.name)
    if bounds is None:
        return False

    func_text = content[bounds[0] : bounds[1]]

    # ── Pattern A: zero-param expression-body arrow  `const name = () => expr` ──
    expr_arrow_no_params = re.compile(
        rf"(?:export\s+)?const\s+{re.escape(target.name)}\s*=\s*(?:async\s+)?\(\s*\)\s*=>\s*(.+?)\s*;?\s*$",
        re.MULTILINE | re.DOTALL,
    )
    m = expr_arrow_no_params.match(func_text.strip())
    if m:
        inline_expr = m.group(1).strip().rstrip(";")
        return _apply_inline(
            target,
            inline_expr,
            params=[],
            source_wt_file=source_wt_file,
            caller_wt_file=caller_wt_file,
            content=content,
            bounds=bounds,
            progress=progress,
        )

    # ── Pattern B: zero-param function with single return ────────────────────
    single_return_no_params = re.compile(
        rf"(?:export\s+)?(?:async\s+)?function\s+{re.escape(target.name)}\s*\(\s*\)\s*(?::[^{{]*)?\{{\s*return\s+(.+?);\s*\}}\s*$",
        re.MULTILINE | re.DOTALL,
    )
    m = single_return_no_params.match(func_text.strip())
    if m:
        inline_expr = m.group(1).strip()
        return _apply_inline(
            target,
            inline_expr,
            params=[],
            source_wt_file=source_wt_file,
            caller_wt_file=caller_wt_file,
            content=content,
            bounds=bounds,
            progress=progress,
        )

    return False  # complex — defer to opencode


def _apply_inline(
    target: FunctionTarget,
    inline_expr: str,
    params: list[str],
    source_wt_file: Path,
    caller_wt_file: Path,
    content: str,
    bounds: tuple[int, int],
    progress: ProgressTracker,
) -> bool:
    """Replace `name()` call sites in the caller with *inline_expr*, remove definition."""
    caller_content = caller_wt_file.read_text(encoding="utf-8")

    # Remove the import of this name from the caller
    import_pat = re.compile(
        rf"import\s*\{{([^}}]*\b{re.escape(target.name)}\b[^}}]*)\}}\s*from\s*['\"][^'\"]+['\"];?\n?",
        re.MULTILINE,
    )
    updated_caller = caller_content

    def _remove_name_from_import(m: re.Match) -> str:
        specifiers = [s.strip() for s in m.group(1).split(",") if s.strip()]
        filtered = [s for s in specifiers if re.split(r"\bas\b", s)[-1].strip() != target.name]
        if not filtered:
            return ""  # entire import removed
        return f"import {{ {', '.join(filtered)} }} from {m.group(0).split('from')[1]}"

    updated_caller, n_import = import_pat.subn(_remove_name_from_import, updated_caller, count=1)
    if n_import == 0:
        progress.log(f"  Could not find import of '{target.name}' in caller — skipping deterministic inline.")
        return False

    # Replace call sites: name() → (inline_expr)
    call_pat = re.compile(rf"\b{re.escape(target.name)}\s*\(\s*\)")
    updated_caller, n_calls = call_pat.subn(f"({inline_expr})", updated_caller)
    if n_calls == 0:
        progress.log(f"  No call sites found for '{target.name}' in caller — reverting.")
        return False

    # Remove the function definition from source
    updated_source = content[: bounds[0]] + content[bounds[1] :]
    # Clean up extra blank lines
    updated_source = re.sub(r"\n{3,}", "\n\n", updated_source).strip() + "\n"

    caller_wt_file.write_text(updated_caller, encoding="utf-8")
    source_wt_file.write_text(updated_source, encoding="utf-8")

    progress.log(
        f"  Deterministically inlined '{target.name}' into {caller_wt_file.name} "
        f"({n_calls} call site(s) replaced)."
    )
    return True


# ── opencode inlining ─────────────────────────────────────────────────────────





def inline_via_opencode(
    todo: AgentTodo,
    progress: ProgressTracker,
    summary: dict,
    summary_lock: threading.Lock,
) -> None:
    """Run opencode to inline a single FunctionTarget. Designed for thread pool use."""
    target = todo.target
    # Relative paths are the same in the worktree as in the original repo
    source_rel = todo.source_wt_file.relative_to(todo.wt_root)
    caller_rel = todo.caller_wt_file.relative_to(todo.wt_root)

    progress.section(f"OpenCode: inline '{target.name}' ({target.body_lines} lines)")

    INLINE_PROMPT_TEMPLATE = """\
    Inline the function `{name}` from `{source_rel}` into `{caller_rel}`.

    Context:
    - `{name}` is defined in `{source_rel}` and is ONLY used in `{caller_rel}`.
    - The goal is to eliminate the indirection: move the logic directly into the call site(s) in `{caller_rel}`.

    Steps to perform:
    1. In `{caller_rel}`, find every place that calls or uses `{name}`.
    2. Replace each usage with the equivalent inline code (copy/expand the function body, substituting arguments for parameters where needed).
    3. Remove the import statement for `{name}` from `{caller_rel}`.
    4. In `{source_rel}`, delete the `{name}` function/export entirely.
    5. If `{source_rel}` becomes empty (or only has unused imports), delete the file.
    6. Update any other imports across the project if needed.
    7. Do NOT commit changes — leave them as uncommitted edits.
    8. After making all changes, verify the linter passes by running: bun run lint
    9. Output a brief summary of what you changed.
    """
    
    prompt = INLINE_PROMPT_TEMPLATE.format(
        name=target.name,
        source_rel=source_rel,
        caller_rel=caller_rel,
    )
    run_opencode(todo.wt_root, prompt, progress)

    diff = get_staged_diff(todo.wt_root)
    sha = commit_all(
        todo.wt_root,
        f"Inline '{target.name}' from {source_rel.name} into {caller_rel.name} via opencode",
    )
    if sha:
        progress.log(f"  Committed opencode changes — {sha}")
        progress.log_diff(diff)
    else:
        progress.log("  No uncommitted changes after opencode (may have self-committed or no changes).")

    with summary_lock:
        summary["opencode_used"] = summary.get("opencode_used", 0) + 1
        summary["inlined"] += 1

    progress.log(f"Done inlining '{target.name}'.")



# ── per-source-file processing ────────────────────────────────────────────────


def process_source_file(
    source_file: Path,
    targets_for_file: list[FunctionTarget],
    repo_root: Path,
    git_root: Path,
    main_branch: str,
    main_wt: Path,
    run_prefix: str,
    args: argparse.Namespace,
    progress: ProgressTracker,
    summary: dict,
    summary_lock: threading.Lock,
) -> tuple[FileResult | None, list[AgentTodo]]:
    """Process all single-use export targets from one source file.

    Pass 1 (deterministic): try to inline short functions directly.
    Defers complex/long functions to opencode (returned as AgentTodo list).

    git_root may differ from repo_root when --repo targets a subdirectory;
    worktrees always mirror the git root structure.
    """
    progress.section(f"Source file: {source_file.name}")
    progress.log(f"  {len(targets_for_file)} candidate(s): {[t.name for t in targets_for_file]}")

    # Create a per-file branch + worktree
    file_branch = f"{run_prefix}/{source_file.stem}"
    file_wt = create_branch_with_worktree(repo_root, file_branch, main_branch)
    progress.log(f"  Created branch: {file_branch}  (worktree: {file_wt})")

    # Paths inside the worktree are relative to the git root, not repo_root
    rel_source = source_file.relative_to(git_root)
    file_result = FileResult(source_file=source_file, file_branch=file_branch, file_wt=file_wt)
    agent_todos: list[AgentTodo] = []

    for target in targets_for_file:
        rel_caller = target.caller_file.relative_to(git_root)
        source_wt_file = file_wt / rel_source
        caller_wt_file = file_wt / rel_caller

        progress.log(
            f"  [{target.name}] body_lines={target.body_lines}, "
            f"caller={rel_caller}"
        )

        if target.body_lines <= args.short_threshold:
            # Attempt deterministic inlining
            success = _try_deterministic_inline(
                target,
                source_wt_file=source_wt_file,
                caller_wt_file=caller_wt_file,
                progress=progress,
            )
            if success:
                diff = get_staged_diff(file_wt)
                sha = commit_all(
                    file_wt,
                    f"Inline '{target.name}' from {source_file.name} (deterministic)",
                )
                progress.log(f"  Committed deterministic inline — {sha or '(nothing staged)'}")
                progress.log_diff(diff)
                with summary_lock:
                    summary["inlined"] += 1
                continue
            else:
                progress.log(f"  Deterministic inline failed for '{target.name}' — deferring to opencode.")

        # Defer to opencode
        agent_todos.append(
            AgentTodo(
                target=target,
                source_wt_file=source_wt_file,
                caller_wt_file=caller_wt_file,
                wt_root=file_wt,
                repo_root=repo_root,
            )
        )

    return file_result, agent_todos


# ── orchestration ─────────────────────────────────────────────────────────────


def process_all(
    targets: list[FunctionTarget],
    repo_root: Path,
    git_root: Path,
    main_branch: str,
    main_wt: Path,
    run_prefix: str,
    args: argparse.Namespace,
    progress: ProgressTracker,
    summary: dict,
    summary_lock: threading.Lock,
) -> list[FileResult]:
    """Orchestrate pass-1 (deterministic) and pass-2 (opencode) across all targets."""

    # Group targets by source file
    from collections import defaultdict
    by_source: dict[Path, list[FunctionTarget]] = defaultdict(list)
    for t in targets:
        by_source[t.source_file].append(t)

    # ── Phase 1: deterministic pass (sequential) ──────────────────────────────
    progress.section("Phase 1: Deterministic inlining")
    file_results: list[FileResult] = []
    all_agent_todos: list[AgentTodo] = []

    for source_file, file_targets in by_source.items():
        try:
            file_result, agent_todos = process_source_file(
                source_file,
                file_targets,
                repo_root,
                git_root,
                main_branch,
                main_wt,
                run_prefix,
                args,
                progress,
                summary,
                summary_lock,
            )
            if file_result is not None:
                file_results.append(file_result)
            all_agent_todos.extend(agent_todos)
        except Exception as exc:
            progress.log(f"ERROR processing {source_file.name}: {exc}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            with summary_lock:
                summary["errors"] += 1

    # ── Phase 2: parallel opencode ────────────────────────────────────────────
    if all_agent_todos:
        # Group todos by worktree: todos that share a worktree must run sequentially
        # to avoid git conflicts, but groups with different worktrees run in parallel.
        from collections import defaultdict as _dd
        todos_by_wt: dict[Path, list[AgentTodo]] = _dd(list)
        for todo in all_agent_todos:
            todos_by_wt[todo.wt_root].append(todo)

        wt_groups = list(todos_by_wt.values())
        max_workers = min(len(wt_groups), os.cpu_count() or 4)
        progress.section(
            f"Phase 2: Parallel OpenCode ({len(all_agent_todos)} tasks across "
            f"{len(wt_groups)} worktree(s), {max_workers} workers)"
        )

        def _run_wt_group(todos: list[AgentTodo]) -> None:
            for todo in todos:
                inline_via_opencode(todo, progress, summary, summary_lock)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_run_wt_group, group): group
                for group in wt_groups
            }
            for future in as_completed(futures):
                group = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    names = [t.target.name for t in group]
                    progress.log(
                        f"ERROR in opencode group {names}: {exc}"
                    )
                    if args.verbose:
                        import traceback
                        traceback.print_exc()
                    with summary_lock:
                        summary["errors"] += 1
                    with summary_lock:
                        summary["errors"] += 1

    return file_results


# ── CLI ───────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Inline exported TypeScript functions that are used in exactly one other file. "
            "Short functions (≤ --short-threshold lines) are inlined deterministically; "
            "larger functions are handled by opencode."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--repo", required=True, help="Path to the target repository root")
    p.add_argument(
        "--dir",
        required=False,
        default=None,
        help=(
            "Directory path relative to --repo to scan (e.g. src/lib). "
            "If omitted, the entire repo src/ is scanned."
        ),
    )
    p.add_argument(
        "--short-threshold",
        type=int,
        default=3,
        metavar="N",
        help="Function bodies with ≤ N non-blank lines are attempted deterministically (default: 3)",
    )
    p.add_argument(
        "--max-files",
        type=int,
        default=None,
        metavar="N",
        help="Process at most N source files",
    )
    p.add_argument("--verbose", action="store_true", help="Print progress to stdout")
    p.add_argument(
        "--merge-file-branches",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Merge each per-file branch back to the main branch after processing (default: on)",
    )
    p.add_argument(
        "--no-opencode",
        action="store_true",
        default=False,
        help="Skip opencode pass (only do deterministic inlining)",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()
    repo_root = Path(args.repo).resolve()

    # Determine scan directory
    if args.dir:
        scan_dir = repo_root / args.dir
        if not scan_dir.is_dir():
            print(f"Error: '{scan_dir}' is not a directory.", file=sys.stderr)
            return 1
    else:
        # Default to src/ if it exists, otherwise the repo root
        scan_dir = repo_root / "src" if (repo_root / "src").is_dir() else repo_root

    # ── initialise progress ───────────────────────────────────────────────────
    progress = ProgressTracker(JEDI_ROOT, verbose=args.verbose)
    progress.log(f"repo:             {repo_root}")
    progress.log(f"scan dir:         {scan_dir}")
    progress.log(f"short-threshold:  {args.short_threshold}")
    progress.log(f"max-files:        {args.max_files}")
    progress.log(f"no-opencode:      {args.no_opencode}")
    progress.log(f"Progress log:     {progress.log_file}")

    # ── assert clean working tree ─────────────────────────────────────────────
    original_branch = get_current_branch(repo_root)
    try:
        ensure_clean_worktree(repo_root)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    # Resolve the actual git root (may differ if --repo is a subdirectory)
    git_root = get_git_root(repo_root)
    progress.log(f"Original branch: {original_branch}")
    progress.log(f"Git root:        {git_root}")

    # ── collect .ts/.tsx files in the scan directory ──────────────────────────
    all_files: list[Path] = sorted(
        list(scan_dir.glob("*.ts")) + list(scan_dir.glob("*.tsx"))
    )
    if args.max_files is not None:
        all_files = all_files[: args.max_files]
    progress.log(f"Files to scan: {len(all_files)}")

    # ── find single-use exports ───────────────────────────────────────────────
    progress.section("Finding single-use exports")
    # When --no-opencode: only look at short functions so we don't waste time
    max_body = args.short_threshold if args.no_opencode else None
    targets = find_single_use_exports(all_files, repo_root, max_body_lines=max_body)
    progress.log(f"Candidates found: {len(targets)}")
    for t in targets:
        rel_src = t.source_file.relative_to(repo_root)
        rel_caller = t.caller_file.relative_to(repo_root)
        progress.log(
            f"  {t.name}  ({t.body_lines} body lines)  {rel_src} → {rel_caller}"
        )

    if not targets:
        progress.log("No single-use exports found. Nothing to do.")
        print("No candidates found.", file=sys.stderr)
        return 0

    summary: dict[str, int] = {
        "total_candidates": len(targets),
        "inlined": 0,
        "errors": 0,
        "opencode_used": 0,
    }
    summary_lock = threading.Lock()

    # ── create main run branch + worktree ─────────────────────────────────────
    stamp = datetime.now(timezone.utc).strftime("%H%M%S-%Y%m%d")
    run_prefix = f"{BRANCH_PREFIX}/inlineShortFunctions/{stamp}"
    main_branch = f"{run_prefix}/base"
    main_wt = create_branch_with_worktree(repo_root, main_branch, original_branch)
    progress.log(f"Main branch:   {main_branch}")
    progress.log(f"Main worktree: {main_wt}")

    # Remap target paths to the main worktree so scanning used the right source
    # (targets were discovered from the original working tree; we just keep paths)

    file_results = process_all(
        targets,
        repo_root,
        git_root,
        main_branch,
        main_wt,
        run_prefix,
        args,
        progress,
        summary,
        summary_lock,
    )

    # ── merge all per-file branches back to the main branch ───────────────────
    if args.merge_file_branches and file_results:
        progress.section("Phase 3: Merging all file branches")
        for fr in file_results:
            try:
                sha = merge_branch(main_wt, fr.file_branch)
                progress.log(f"Merged {fr.file_branch} → {main_branch}  (sha: {sha})")
            except Exception as exc:
                progress.log(f"ERROR merging {fr.file_branch}: {exc}")
                if args.verbose:
                    import traceback
                    traceback.print_exc()
                with summary_lock:
                    summary["errors"] += 1

    # ── final summary ─────────────────────────────────────────────────────────
    progress.section("Summary")
    for k, v in summary.items():
        progress.log(f"  {k}: {v}")

    print(f"\nDone. Inlined {summary['inlined']} function(s). "
          f"Errors: {summary['errors']}. "
          f"Progress log: {progress.log_file}")
    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
