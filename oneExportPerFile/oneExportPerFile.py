#!/usr/bin/env python3
"""
oneExportPerFile.py — Refactor a directory so every .ts/.tsx file has exactly one export.

Usage:
    python -m oneExportPerFile.oneExportPerFile \\
        --repo /path/to/stemwise \\
        --dir src/hooks \\
        --max-files 5 \\
        --verbose

For each file with multiple exports the script will:
  1. Create a per-file git branch.
  2. Strip 'export' from any declaration that is not imported elsewhere (regex + grep).
  3. If multiple exports still remain, defer the opencode call to a parallel phase.
  4. After all deterministic (pass-1) work is done, run all deferred opencode tasks
     concurrently in a thread pool.
  5. Once every branch is finished, merge them all back to the main branch together.

Progress is written to jedi/Progress/process_{HHMMSS}_{YYYYMMDD}_{uid}/progress.md.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

JEDI_ROOT = Path(__file__).resolve().parents[1]

from gitOperations.branch_manager import (
    BRANCH_PREFIX,
    get_current_branch,
    ensure_clean_worktree,
    commit_all,
    create_branch_with_worktree,
    remove_worktree,
    merge_branch,
    get_staged_diff,
)
from oneExportPerFile.checkIsImportedElsewhere import is_imported_elsewhere
from oneExportPerFile.runOpenCode import run_opencode
from oneExportPerFile.tsxConstants import EXPORT_DECL_RE, EXPORT_BRACE_RE

# ── export helpers ────────────────────────────────────────────────────────────


def find_export_names(content: str) -> list[str]:
    """Return all exported symbol names (in order) from TypeScript source text.

    Covers both declaration-style  (export function foo)  and
    brace-style  (export { foo, bar as baz }).
    """
    names: list[str] = [m.group(1) for m in EXPORT_DECL_RE.finditer(content)]
    for m in EXPORT_BRACE_RE.finditer(content):
        for item in m.group(1).split(","):
            item = item.strip()
            if not item:
                continue
            # Handle  foo as Bar  — the exported name is after 'as'
            parts = re.split(r"\bas\b", item)
            exported_name = parts[-1].strip()
            if exported_name and exported_name not in names:
                names.append(exported_name)
    return names


def strip_export_keyword(content: str, name: str) -> str:
    """Remove *name* from the file's exports without deleting its declaration.

    Handles:
    * Declaration style:  export function foo(...)  →  function foo(...)
    * Brace style:        export { foo, bar }       →  export { bar }
                          export { foo }            →  (line removed)
    """
    # 1. Try declaration-style first
    decl_pat = re.compile(
        rf"^(export\s+(?:default\s+)?)((?:async\s+)?(?:(?:abstract\s+)?class\s+|function\s*\*?\s*|interface\s+|type\s+|enum\s+|(?:const|let|var)\s+){re.escape(name)}\b)",
        re.MULTILINE,
    )
    new_content, n = decl_pat.subn(r"\2", content, count=1)
    if n:
        return new_content

    # 2. Try brace-style:  export { ..., name, ... }
    def _remove_from_brace(m: re.Match) -> str:
        items = [i.strip() for i in m.group(1).split(",") if i.strip()]
        # Remove the item that exports `name` (matches "name" or "localName as name")
        filtered = [
            i for i in items
            if re.split(r"\bas\b", i)[-1].strip() != name
        ]
        if not filtered:
            return ""  # remove entire export { } line
        return f"export {{ {', '.join(filtered)} }};"

    new_content, n = EXPORT_BRACE_RE.subn(_remove_from_brace, content, count=1)
    if n:
        # Clean up any blank lines left by removing an empty export
        new_content = re.sub(r"\n{3,}", "\n\n", new_content)
        return new_content

    return content  # no change


# ── task data structures ──────────────────────────────────────────────────────


@dataclass
class AgentTodo:
    """An opencode task deferred from deterministic pass 1."""

    file: Path
    file_wt: Path
    rel: Path
    export_names: list[str]  # names kept after pass 1 (used in the prompt)


@dataclass
class FileResult:
    """Tracks the per-file branch created in pass 1, used for merge & cleanup."""

    file: Path
    file_branch: str
    file_wt: Path


# ── progress tracking ─────────────────────────────────────────────────────────


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
            f"# oneExportPerFile run\n\n"
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


# ── per-file processing ───────────────────────────────────────────────────────
def remove_unused_exports(
    file: Path,
    repo_root: Path,
    main_branch: str,
    main_wt: Path,
    run_prefix: str,
    args: argparse.Namespace,
    progress: ProgressTracker,
    summary: dict,
    summary_lock: threading.Lock,
) -> tuple[FileResult | None, AgentTodo | None]:
    """Run deterministic pass 1 for a file.

    Returns (FileResult, AgentTodo|None).
    FileResult is None when the file was skipped (≤1 export).
    AgentTodo is non-None when opencode is still needed after pass 1.
    """
    progress.section(f"File: {file.name}")

    # Relative path inside the repo (same in any worktree)
    rel = file.relative_to(repo_root)

    # Quick pre-check on the main worktree before creating a branch
    content = (main_wt / rel).read_text(encoding="utf-8")
    export_names = find_export_names(content)
    progress.log(f"Exports found ({len(export_names)}): {export_names}")

    if len(export_names) <= 1:
        progress.log("Only 1 export — skipping.")
        with summary_lock:
            summary["skipped"] += 1
        return None, None

    # ── create per-file branch with its own worktree ──────────────────────────
    file_branch = f"{run_prefix}/{file.stem}"
    file_wt = create_branch_with_worktree(repo_root, file_branch, main_branch)
    progress.log(f"Created file branch: {file_branch} (worktree: {file_wt})")

    wt_file = file_wt / rel
    file_result = FileResult(file=file, file_branch=file_branch, file_wt=file_wt)

    # deterministically strip 'export' from non-imported symbols ──────────────────────
    content = wt_file.read_text(encoding="utf-8")
    export_names = find_export_names(content)

    for name in list(export_names):
        if is_imported_elsewhere(name, file_wt, wt_file):
            progress.log(f"  '{name}' is imported elsewhere — keeping export.")
        else:
            # Safe to remove — nothing outside this file references it
            content = wt_file.read_text(encoding="utf-8")
            updated = strip_export_keyword(content, name)
            if updated == content:
                progress.log(f"  '{name}' — could not find export declaration to strip (skipping).")
                continue
            wt_file.write_text(updated, encoding="utf-8")
            diff = get_staged_diff(file_wt)
            sha = commit_all(file_wt, f"Remove unused export '{name}' from {file.name}")
            progress.log(f"  Removed 'export' from '{name}' — committed {sha or '(nothing staged)'}.")
            progress.log_diff(diff)
            export_names.remove(name)

    # Check what remains after pass 1
    content = wt_file.read_text(encoding="utf-8")
    remaining = find_export_names(content)
    progress.log(f"After pass 1: {len(remaining)} export(s) remain — {remaining}")

    if len(remaining) > 1:
        # Use coding agent for more complex task
        todo = AgentTodo(file=file, file_wt=file_wt, rel=rel, export_names=export_names)
        return file_result, todo
    else:
        with summary_lock:
            summary["split"] += 1
        progress.log(f"Done with {file.name} (no opencode needed).")
        return file_result, None


def split_exports_to_separate_files(
    todo: AgentTodo,
    progress: ProgressTracker,
    summary: dict,
    summary_lock: threading.Lock,
) -> None:
    """Run the opencode pass for a single file. Designed to run in a thread pool."""
    file = todo.file
    file_wt = todo.file_wt
    rel = todo.rel
    export_names = todo.export_names

    progress.section(f"OpenCode: {file.name}")

    PROMPT_TEMPLATE = """Refactor the file `{rel_path}` in this TypeScript/React project.

        The file currently has {count} top-level exports: {names}.

        Your task:
        1. Split these exports so that each ends up in its OWN dedicated file with exactly ONE export.
        2. If helpers (types, constants, utilities) are shared by multiple exports, extract those helpers to their own single-export file too - never put multiple exports in one file.
        3. Use the same directory as the original file for all new files.
        4. Name each new file after the symbol it exports (e.g. useGoals -> useGoals.tsx). If the new filename wouldn't be understandable, add an additional word to make it more specific.
        5. Update every import across the ENTIRE project to point to the new file paths.
        6. The original file may be deleted or reduced to a single export - whatever is cleanest.
        7. Do NOT create any file with more than one export.
        8. Do NOT commit any changes - leave them as uncommitted edits.
        9. After making all changes verify the linter passes by running: bun run lint
        10. Output a brief summary of what files you created/modified when done.
        """
    prompt = PROMPT_TEMPLATE.format(
        rel_path=rel,
        count=len(export_names),
        names=", ".join(export_names),
    )

    run_opencode(file_wt, prompt, progress)

    # Commit whatever opencode changed (it was instructed not to self-commit)
    diff = get_staged_diff(file_wt)
    sha = commit_all(file_wt, f"Split multiple exports in {file.name} via opencode")
    if sha:
        progress.log(f"  Committed opencode changes — {sha}")
        progress.log_diff(diff)
    else:
        progress.log("  No uncommitted changes after opencode (may have self-committed or no changes).")

    with summary_lock:
        summary["opencode_used"] = summary.get("opencode_used", 0) + 1
        summary["split"] += 1

    progress.log(f"Done with {file.name}.")

def process_all_files(
    files: list[Path],
    repo_root: Path,
    main_branch: str,
    main_wt: Path,
    run_prefix: str,
    args: argparse.Namespace,
    progress: ProgressTracker,
    summary: dict,
    summary_lock: threading.Lock,
) -> list[FileResult]:

    # ── phase 1: deterministic pass-1 processing (sequential) ────────────────
    progress.section("Phase 1: Deterministic processing")
    file_results: list[FileResult] = []
    agent_todo: list[AgentTodo] = []

    for file in files:
        try:
            file_result, todo = remove_unused_exports(
                file, repo_root, main_branch, main_wt,
                run_prefix, args, progress, summary, summary_lock,
            )
            if file_result is not None:
                file_results.append(file_result)
            if todo is not None:
                agent_todo.append(todo)
        except Exception as exc:
            progress.log(f"ERROR processing {file.name}: {exc}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            with summary_lock:
                summary["errors"] += 1

    # ── phase 2: parallel opencode ────────────────────────────────────────────
    if agent_todo:
        max_workers = min(len(agent_todo), os.cpu_count() or 4)
        progress.section(f"Phase 2: Parallel OpenCode ({len(agent_todo)} tasks, {max_workers} workers)")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(split_exports_to_separate_files, todo, progress, summary, summary_lock): todo
                for todo in agent_todo
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

    return file_results


# ── CLI ───────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Ensure each .ts/.tsx file in a directory has exactly one export.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--repo", required=True, help="Path to the target repository root")
    p.add_argument(
        "--dir",
        required=True,
        help="Directory path relative to --repo (e.g. src/hooks)",
    )
    p.add_argument(
        "--max-files",
        type=int,
        default=None,
        metavar="N",
        help="Process at most N files (useful for testing)",
    )
    p.add_argument("--verbose", action="store_true", help="Print progress to stdout")
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
    target_dir = repo_root / args.dir

    if not target_dir.is_dir():
        print(f"Error: '{target_dir}' is not a directory.", file=sys.stderr)
        return 1

    # ── initialise progress tracker before touching the target repo ───────────
    progress = ProgressTracker(JEDI_ROOT, verbose=args.verbose)
    progress.log(f"repo:        {repo_root}")
    progress.log(f"target dir:  {target_dir}")
    progress.log(f"max-files:   {args.max_files}")
    progress.log(f"merge-file-branches: {args.merge_file_branches}")
    progress.log(f"Progress log: {progress.log_file}")

    # ── assert clean working tree ─────────────────────────────────────────────
    original_branch = get_current_branch(repo_root)
    try:
        ensure_clean_worktree(repo_root)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    progress.log(f"Original branch: {original_branch}")

    # ── create main oneExportPerFile branch with its own worktree ──────────────
    stamp = datetime.now(timezone.utc).strftime("%H%M%S-%Y%m%d")
    run_prefix = f"{BRANCH_PREFIX}/oneExportPerFile/{stamp}"
    main_branch = f"{run_prefix}/base"
    main_wt = create_branch_with_worktree(repo_root, main_branch, original_branch)
    progress.log(f"Main branch:     {main_branch}")
    progress.log(f"Main worktree:   {main_wt}")

    # ── collect target files ──────────────────────────────────────────────────
    files: list[Path] = sorted(
        list(target_dir.glob("*.ts")) + list(target_dir.glob("*.tsx"))
    )
    if args.max_files is not None:
        files = files[: args.max_files]

    summary: dict[str, int] = {
        "total_files": len(files),
        "skipped": 0,
        "split": 0,
        "merged": 0,
        "errors": 0,
        "opencode_used": 0,
    }
    summary_lock = threading.Lock()
    file_results = process_all_files(
        files, repo_root, main_branch, main_wt,
        run_prefix, args, progress, summary, summary_lock,
    )
    # ── merge all file branches back to main ─────────────────────────
    if args.merge_file_branches and file_results:
        progress.section("Phase 3: Merging all file branches")
        for fr in file_results:
            try:
                sha = merge_branch(main_wt, fr.file_branch)
                progress.log(f"Merged {fr.file_branch} → {main_branch} (sha: {sha})")
                with summary_lock:
                    summary["merged"] += 1
            except Exception as exc:
                progress.log(f"ERROR merging {fr.file_branch}: {exc}")
                if args.verbose:
                    import traceback
                    traceback.print_exc()
                with summary_lock:
                    summary["errors"] += 1

    # ── phase 4: remove all worktrees ─────────────────────────────────────────
    progress.section("Phase 4: Cleanup")
    for fr in file_results:
        try:
            remove_worktree(repo_root, fr.file_wt)
            progress.log(f"Removed worktree: {fr.file_wt}")
        except Exception as exc:
            progress.log(f"Warning: could not remove worktree {fr.file_wt}: {exc}")

    # ── final summary ─────────────────────────────────────────────────────────
    progress.section("Summary")
    for k, v in summary.items():
        progress.log(f"{k}: {v}")

    oepf_count = summary["opencode_used"]
    print()
    print("╔═══════════════════════════════════════════════╗")
    print("║        oneExportPerFile — complete            ║")
    print("╠═══════════════════════════════════════════════╣")
    print(f"║  Files examined:         {summary['total_files']:<22} ║")
    print(f"║  Already 1 export (skipped): {summary['skipped']:<18} ║")
    print(f"║  Refactored:             {summary['split']:<22} ║")
    print(f"║  Used opencode:          {oepf_count:<22} ║")
    print(f"║  Branches merged:        {summary['merged']:<22} ║")
    print(f"║  Errors:                 {summary['errors']:<22} ║")
    print("╠═══════════════════════════════════════════════╣")
    print(f"║  Main branch: {main_branch[-35:]:<35} ║")
    print("╚═══════════════════════════════════════════════╝")
    print(f"\nProgress log: {progress.log_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
