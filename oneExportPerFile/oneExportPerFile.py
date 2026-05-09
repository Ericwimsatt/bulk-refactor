#!/usr/bin/env python3
"""
oneExportPerFile.py — Refactor a directory so every .ts/.tsx file has exactly one export.

Usage:
    python oneExportPerFile.py \\
        --repo /path/to/stemwise \\
        --dir src/hooks \\
        --max-files 5 \\
        --verbose

For each file with multiple exports the script will:
  1. Create a per-file git branch.
  2. Strip 'export' from any declaration that is not imported elsewhere (regex + grep).
  3. If multiple exports still remain, delegate to the opencode CLI to split them into
     separate single-export files.
  4. Commit the result and optionally merge the per-file branch back to the main branch.

Progress is written to jedi/Progress/process_{HHMMSS}_{YYYYMMDD}_{uid}/progress.md.
"""
from __future__ import annotations

import argparse
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ── path setup ────────────────────────────────────────────────────────────────
JEDI_ROOT = Path(__file__).resolve().parents[1]
OEPF_ROOT = Path(__file__).resolve().parent

for _p in (str(JEDI_ROOT), str(OEPF_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from gitOperations.branch_manager import (  # noqa: E402
    BRANCH_PREFIX,
    get_current_branch,
    ensure_clean_worktree,
    checkout_branch,
    commit_all,
)
from blocks.python.shell_runner import run_cmd  # noqa: E402

# ── constants ─────────────────────────────────────────────────────────────────

# Matches top-level TypeScript declaration-style exports (export function foo, etc.)
# and captures the exported name in group 1.
EXPORT_DECL_RE = re.compile(
    r"^export\s+"
    r"(?:default\s+)?"
    r"(?:async\s+)?"
    r"(?:"
    r"(?:abstract\s+)?class\s+|"
    r"function\s*\*?\s*|"
    r"interface\s+|"
    r"type\s+|"
    r"enum\s+|"
    r"(?:const|let|var)\s+"
    r")"
    r"(\w+)",
    re.MULTILINE,
)

# Matches  export { Foo, Bar as Baz }  (named group exports, not re-exports from another module)
# We exclude  export { ... } from '...'  because those are re-exports of another file's symbols.
EXPORT_BRACE_RE = re.compile(
    r"^export\s*\{([^}]*)\}(?!\s*from\b)[;]?",
    re.MULTILINE,
)


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


# ── import-usage detection ────────────────────────────────────────────────────


def is_imported_elsewhere(name: str, repo_root: Path, exclude_file: Path) -> bool:
    """Return True if *name* appears in an import or re-export in any file other than *exclude_file*.

    Uses grep to locate candidate files quickly, then verifies with a tighter Python regex.
    """
    src_dir = repo_root / "src"
    try:
        hits_raw = run_cmd(
            [
                "grep",
                "-rl",
                "--include=*.ts",
                "--include=*.tsx",
                f"\\b{name}\\b",
                str(src_dir),
            ],
            cwd=repo_root,
            check=False,
        )
    except Exception:
        return False

    for hit_path_str in hits_raw.splitlines():
        candidate = Path(hit_path_str).resolve()
        if candidate == exclude_file.resolve():
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        # Accept both import and re-export patterns
        if re.search(
            rf"(?:import|export)\b[^;]*\b{re.escape(name)}\b",
            text,
        ):
            return True

    return False


# ── git helpers ───────────────────────────────────────────────────────────────


def create_branch(repo_root: Path, branch_name: str, base_branch: str) -> None:
    """Checkout *base_branch*, then create and switch to *branch_name*."""
    run_cmd(["git", "checkout", base_branch], cwd=repo_root)
    run_cmd(["git", "checkout", "-b", branch_name], cwd=repo_root)


def merge_branch(repo_root: Path, source: str, target: str) -> str:
    """Merge *source* into *target* with a no-ff merge; return the new HEAD sha."""
    run_cmd(["git", "checkout", target], cwd=repo_root)
    run_cmd(
        ["git", "merge", "--no-ff", source, "-m", f"Merge {source} into {target}"],
        cwd=repo_root,
    )
    return run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_root)


def get_staged_diff(repo_root: Path) -> str:
    return run_cmd(["git", "diff", "HEAD"], cwd=repo_root)


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
        self._write(
            f"# oneExportPerFile run\n\n"
            f"Started: {datetime.now(timezone.utc).isoformat()}\n\n"
        )

    def _write(self, text: str) -> None:
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


# ── opencode integration ──────────────────────────────────────────────────────


OPENCODE_PROMPT_TEMPLATE = """Refactor the file `{rel_path}` in this TypeScript/React project.

The file currently has {count} top-level exports: {names}.

Your task:
1. Split these exports so that each ends up in its OWN dedicated file with exactly ONE export.
2. If helpers (types, constants, utilities) are shared by multiple exports, extract those helpers to their own single-export file too — never put multiple exports in one file.
3. Use the same directory as the original file for all new files.
4. Name each new file after the symbol it exports (e.g. useGoals → useGoals.ts).
5. Update every import across the ENTIRE project to point to the new file paths.
6. The original file may be deleted or reduced to a single export — whatever is cleanest.
7. Do NOT create any file with more than one export.
8. Do NOT commit any changes — leave them as uncommitted edits.
9. After making all changes verify the linter passes by running: bun run lint
10. Output a brief summary of what files you created/modified when done.
"""


def run_opencode(
    repo_root: Path,
    file: Path,
    export_names: list[str],
    progress: ProgressTracker,
) -> None:
    """Invoke the opencode CLI to split remaining multiple exports in *file*."""
    rel = file.relative_to(repo_root)
    prompt = OPENCODE_PROMPT_TEMPLATE.format(
        rel_path=rel,
        count=len(export_names),
        names=", ".join(export_names),
    )
    progress.log(f"  Invoking opencode to split {file.name} (exports: {', '.join(export_names)})")
    try:
        output = run_cmd(
            ["opencode", "run", prompt],
            cwd=repo_root,
            check=False,
        )
        progress.log_output(f"opencode/{file.name}", output)
        progress.log("  opencode step completed.")
    except Exception as exc:
        progress.log(f"  opencode error: {exc}")


# ── per-file processing ───────────────────────────────────────────────────────


def process_file(
    file: Path,
    repo_root: Path,
    main_branch: str,
    run_prefix: str,
    args: argparse.Namespace,
    progress: ProgressTracker,
    summary: dict,
) -> None:
    progress.section(f"File: {file.name}")

    content = file.read_text(encoding="utf-8")
    export_names = find_export_names(content)
    progress.log(f"Exports found ({len(export_names)}): {export_names}")

    if len(export_names) <= 1:
        progress.log("Only 1 export — skipping.")
        summary["skipped"] += 1
        return

    # ── create per-file branch ────────────────────────────────────────────────
    # File branches live at run_prefix/{file.stem} (sibling to base, not nested under it)
    file_branch = f"{run_prefix}/{file.stem}"
    create_branch(repo_root, file_branch, main_branch)
    progress.log(f"Created file branch: {file_branch}")

    # ── pass 1: strip 'export' from non-imported symbols ─────────────────────
    # Re-read content on the new branch (should be identical, but be explicit)
    content = file.read_text(encoding="utf-8")
    export_names = find_export_names(content)

    for name in list(export_names):
        if is_imported_elsewhere(name, repo_root, file):
            progress.log(f"  '{name}' is imported elsewhere — keeping export.")
        else:
            # Safe to remove — nothing outside this file references it
            content = file.read_text(encoding="utf-8")
            updated = strip_export_keyword(content, name)
            if updated == content:
                progress.log(f"  '{name}' — could not find export declaration to strip (skipping).")
                continue
            file.write_text(updated, encoding="utf-8")
            diff = get_staged_diff(repo_root)
            sha = commit_all(repo_root, f"Remove unused export '{name}' from {file.name}")
            progress.log(f"  Removed 'export' from '{name}' — committed {sha or '(nothing staged)'}.")
            progress.log_diff(diff)
            export_names.remove(name)

    # ── pass 2: opencode for remaining multiple exports ───────────────────────
    content = file.read_text(encoding="utf-8")
    remaining = find_export_names(content)
    progress.log(f"After pass 1: {len(remaining)} export(s) remain — {remaining}")

    if len(remaining) > 1:
        run_opencode(repo_root, file, remaining, progress)

        # Commit whatever opencode changed (it was instructed not to self-commit)
        diff = get_staged_diff(repo_root)
        sha = commit_all(repo_root, f"Split multiple exports in {file.name} via opencode")
        if sha:
            progress.log(f"  Committed opencode changes — {sha}")
            progress.log_diff(diff)
        else:
            progress.log("  No uncommitted changes after opencode (may have self-committed or no changes).")
        summary["opencode_used"] = summary.get("opencode_used", 0) + 1

    # ── optional: merge file branch back to main branch ───────────────────────
    if args.merge_file_branches:
        sha = merge_branch(repo_root, file_branch, main_branch)
        progress.log(f"Merged {file_branch} → {main_branch} (sha: {sha})")
        summary["merged"] += 1

    summary["split"] += 1
    progress.log(f"Done with {file.name}.")


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

    # ── create main oneExportPerFile branch ───────────────────────────────────
    # Note: file branches are nested as  .../run/{stamp}/{file.stem}
    #       so the run base is           .../run/{stamp}/base
    #       to avoid the git "file vs directory" naming conflict.
    stamp = datetime.now(timezone.utc).strftime("%H%M%S-%Y%m%d")
    run_prefix = f"{BRANCH_PREFIX}/oneExportPerFile/{stamp}"
    main_branch = f"{run_prefix}/base"
    create_branch(repo_root, main_branch, original_branch)
    progress.log(f"Main branch:     {main_branch}")

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
    }

    # ── process each file ─────────────────────────────────────────────────────
    for file in files:
        try:
            process_file(file, repo_root, main_branch, run_prefix, args, progress, summary)
        except Exception as exc:
            progress.log(f"ERROR processing {file.name}: {exc}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            summary["errors"] += 1
            # Attempt recovery: return to main branch so we can keep going
            try:
                checkout_branch(repo_root, main_branch)
            except Exception:
                pass

    # ── return to original branch ─────────────────────────────────────────────
    try:
        checkout_branch(repo_root, original_branch)
        progress.log(f"Returned to original branch: {original_branch}")
    except Exception as exc:
        progress.log(f"Warning: could not return to {original_branch}: {exc}")

    # ── final summary ─────────────────────────────────────────────────────────
    # Include opencode_used in summary dict so it logs once
    if "opencode_used" not in summary:
        summary["opencode_used"] = 0

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
