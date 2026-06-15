#!/usr/bin/env python3
"""
collectPageSpecificFiles.py — Move page-specific files from a shared directory into the page's own folder.

Usage:
    python -m tasks.collectPageSpecificFiles.collectPageSpecificFiles \\
        --repo /path/to/repo \\
        --roots-dir app \\
        --target-dir components \\
        --verbose

Algorithm:
  1. Establish lines of ancestry: build an importer map for every file in target_dir.
     A file is claimed by root page R when all of its importers are either R itself
     or other files already claimed by R (fixed-point iteration).
  2. Create destination folders.  If a root file lives directly inside roots_dir
     and file_based_routing_pages=True, create a sub-folder named after the root
     file's stem and move the root file to index.tsx inside it.
  3. Move the claimed files into that folder and update all @/ import paths across
     the project to reflect the new locations.

Git workflow:
  - A single base branch + worktree is created for the run.
  - All moves and import fixes happen in that worktree.
  - The worktree is removed after the branch is created (caller merges manually).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from utils.gitOperations.branch_manager import (
    build_main_branch_names,
    get_current_branch,
    get_git_root,
    ensure_clean_worktree,
    commit_all,
    create_branch_with_worktree,
    remove_worktree,
    get_staged_diff,
)
from tasks.oneExportPerFile.shell_runner import run_cmd
from utils.progressTracker.progressTracker import ProgressTracker

# ── import resolution ─────────────────────────────────────────────────────────

_EXCLUDED_DIRS = {"node_modules", ".git", ".bulk-refactor-worktrees", "_generated", ".expo"}


def _try_extensions(base: Path) -> Path | None:
    """Try .ts / .tsx extensions and /index.{ts,tsx} variants."""
    for ext in (".ts", ".tsx"):
        c = base.with_suffix(ext)
        if c.exists():
            return c
    for ext in (".ts", ".tsx"):
        c = base / f"index{ext}"
        if c.exists():
            return c
    return None


def resolve_import_path(import_str: str, importer: Path, repo_root: Path) -> Path | None:
    """Resolve a TypeScript import string to an absolute file path.

    Handles:
    - ``@/`` alias → repo_root/
    - Relative paths (./foo, ../foo)
    Returns None for external packages.
    """
    if import_str.startswith("@/"):
        base = repo_root / import_str[2:]
    elif import_str.startswith("."):
        base = (importer.parent / import_str).resolve()
    else:
        return None  # external package

    if base.exists() and base.is_file():
        return base
    return _try_extensions(base)


def find_all_ts_files(directory: Path) -> list[Path]:
    """Return all .ts/.tsx files in *directory* recursively, excluding common noise dirs."""
    results: list[Path] = []
    for p in directory.rglob("*"):
        if p.is_file() and p.suffix in (".ts", ".tsx"):
            # Only check relative parts (not the ancestor dirs like .bulk-refactor-worktrees)
            try:
                rel_parts = p.relative_to(directory).parts
            except ValueError:
                rel_parts = p.parts
            if not any(part in _EXCLUDED_DIRS for part in rel_parts):
                results.append(p)
    return results


# ── importer map ──────────────────────────────────────────────────────────────

_IMPORT_FROM_RE = re.compile(r"""from\s+['"]([^'"]+)['"]""")


def _importers_of(
    target_file: Path,
    all_ts_files: list[Path],
    repo_root: Path,
) -> list[Path]:
    """Return every .ts/.tsx file that imports *target_file*."""
    target_resolved = target_file.resolve()
    importers: list[Path] = []
    for candidate in all_ts_files:
        if candidate.resolve() == target_resolved:
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        for m in _IMPORT_FROM_RE.finditer(text):
            resolved = resolve_import_path(m.group(1), candidate, repo_root)
            if resolved and resolved.resolve() == target_resolved:
                importers.append(candidate)
                break
    return importers


# ── ancestry / claim algorithm ────────────────────────────────────────────────

def compute_page_claims(
    roots_dir: Path,
    target_files: list[Path],
    root_files: list[Path],
    all_ts_files: list[Path],
    repo_root: Path,
    progress: ProgressTracker,
) -> dict[Path, Path]:
    """Return {resolved_target_file: root_file} for every exclusively-claimable file.

    Uses fixed-point iteration: in each round we expand the set of claimed files
    until no new claims can be made.
    """
    progress.section("Building importer map")
    importer_map: dict[Path, list[Path]] = {}
    for tf in target_files:
        importers = _importers_of(tf, all_ts_files, repo_root)
        importer_map[tf.resolve()] = importers
        progress.log(f"  {tf.relative_to(repo_root)}: imported by {[p.name for p in importers]}")

    root_file_resolved: dict[Path, Path] = {rf.resolve(): rf for rf in root_files}

    claims: dict[Path, Path] = {}  # resolved → original root_file

    changed = True
    while changed:
        changed = False
        for tf in target_files:
            tf_res = tf.resolve()
            if tf_res in claims:
                continue

            importers = importer_map[tf_res]
            if not importers:
                continue  # orphan — leave in place

            claiming_roots: set[Path] = set()
            all_covered = True

            for imp in importers:
                imp_res = imp.resolve()
                if imp_res in root_file_resolved:
                    claiming_roots.add(imp_res)
                elif imp_res in claims:
                    claiming_roots.add(claims[imp_res].resolve())
                else:
                    all_covered = False
                    break

            if all_covered and len(claiming_roots) == 1:
                root_res = next(iter(claiming_roots))
                claims[tf_res] = root_file_resolved[root_res]
                changed = True
                progress.log(
                    f"  Claimed {tf.relative_to(repo_root)} → "
                    f"{root_file_resolved[root_res].name}"
                )

    return claims


# ── destination folder helpers ────────────────────────────────────────────────

def _compute_dest_folder(
    root_file: Path,
    roots_dir: Path,
    file_based_routing_pages: bool,
    wt_root: Path,
    git_root: Path,
) -> Path | None:
    """Return the worktree destination folder for files claimed by *root_file*.

    Returns None for special files that should not trigger folder creation
    (files starting with ``_`` or named ``index``).

    *git_root* is the actual git repository root (may differ from repo_root
    when the app lives in a subdirectory of the git repo).
    """
    if root_file.parent.resolve() == roots_dir.resolve():
        stem = root_file.stem
        # Skip Expo Router layout / index files — moving them breaks routing
        if stem.startswith("_") or stem == "index":
            return None
        if not file_based_routing_pages:
            raise NotImplementedError(
                "file_based_routing_pages=False is not yet implemented"
            )
        wt_roots = wt_root / roots_dir.relative_to(git_root)
        return wt_roots / stem
    else:
        # Root file is already inside a sub-folder of roots_dir — use that folder
        wt_root_file = wt_root / root_file.relative_to(git_root)
        return wt_root_file.parent


# ── move files & fix imports ──────────────────────────────────────────────────

def perform_moves(
    claims: dict[Path, Path],
    roots_dir: Path,
    repo_root: Path,
    git_root: Path,
    wt_root: Path,
    file_based_routing_pages: bool,
    progress: ProgressTracker,
) -> dict[Path, Path]:
    """Execute ``git mv`` for all claimed files (and their root pages).

    Returns ``{old_original_path: new_original_path}`` for import-path rewriting.
    Paths in the dict are absolute paths under *repo_root* (for ``@/`` import
    string computation).

    *git_root* is the actual git repository root used to map files into the
    worktree (files live at ``wt_root / file.relative_to(git_root)``).
    """
    # Group by root file
    by_root: dict[Path, list[Path]] = {}
    for tf_res, root_file in claims.items():
        by_root.setdefault(root_file.resolve(), []).append(Path(tf_res))

    moves: dict[Path, Path] = {}

    for root_res, claimed in by_root.items():
        root_file = Path(root_res)
        dest = _compute_dest_folder(root_file, roots_dir, file_based_routing_pages, wt_root, git_root)

        if dest is None:
            progress.log(f"Skipping special root file {root_file.name} — not moving")
            continue

        dest.mkdir(parents=True, exist_ok=True)
        progress.log(f"Destination folder: {dest.relative_to(wt_root)}")

        # Move the root file itself (only when it's a direct child of roots_dir)
        if root_file.parent.resolve() == roots_dir.resolve():
            wt_src = wt_root / root_file.relative_to(git_root)
            wt_dst = dest / "index.tsx"
            progress.log(f"  git mv {wt_src.relative_to(wt_root)} → {wt_dst.relative_to(wt_root)}")
            run_cmd(["git", "mv", str(wt_src), str(wt_dst)], cwd=wt_root)
            # Store in moves dict with repo_root-relative absolute paths
            moves[root_file] = git_root / wt_dst.relative_to(wt_root)

        # Move claimed component files
        for tf in claimed:
            wt_src = wt_root / tf.relative_to(git_root)
            wt_dst = dest / tf.name
            progress.log(f"  git mv {wt_src.relative_to(wt_root)} → {wt_dst.relative_to(wt_root)}")
            run_cmd(["git", "mv", str(wt_src), str(wt_dst)], cwd=wt_root)
            moves[tf] = git_root / wt_dst.relative_to(wt_root)

    return moves


def _update_imports_in_file(
    file_path: Path,
    moves: dict[Path, Path],
    repo_root: Path,
) -> bool:
    """Rewrite @/-prefixed import paths in *file_path* for every moved file.

    Returns True if the file was modified.
    """
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError:
        return False

    original = text

    for old_path, new_path in moves.items():
        old_rel = old_path.relative_to(repo_root).with_suffix("")
        new_rel = new_path.relative_to(repo_root).with_suffix("")
        old_import = "@/" + str(old_rel).replace("\\", "/")
        new_import = "@/" + str(new_rel).replace("\\", "/")

        if old_import == new_import:
            continue

        # Replace occurrences inside import / export from '...' or "..."
        text = re.sub(
            rf"""(['"])({re.escape(old_import)})(['"])""",
            lambda m, ni=new_import: m.group(1) + ni + m.group(3),
            text,
        )

    if text != original:
        file_path.write_text(text, encoding="utf-8")
        return True
    return False


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Move page-specific files from a shared directory into each page's folder.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--repo", required=True, help="Path to the target repository root")
    p.add_argument(
        "--roots-dir",
        required=True,
        help="Directory containing root page files, relative to --repo (e.g. app)",
    )
    p.add_argument(
        "--target-dir",
        required=True,
        help="Directory to pull files out of, relative to --repo (e.g. components)",
    )
    p.add_argument(
        "--file-based-routing-pages",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "When True (default), root files that are direct children of roots-dir "
            "are moved into a new sub-folder of the same name as index.tsx. "
            "False is not yet implemented."
        ),
    )
    p.add_argument("--verbose", action="store_true", help="Print progress to stdout")
    return p


def main() -> int:
    args = build_parser().parse_args()
    repo_root = Path(args.repo).resolve()
    roots_dir = (repo_root / args.roots_dir).resolve()
    target_dir = (repo_root / args.target_dir).resolve()
    file_based_routing_pages: bool = args.file_based_routing_pages

    if not roots_dir.is_dir():
        print(f"Error: '{roots_dir}' is not a directory.", file=sys.stderr)
        return 1
    if not target_dir.is_dir():
        print(f"Error: '{target_dir}' is not a directory.", file=sys.stderr)
        return 1

    progress = ProgressTracker(run_name="collectPageSpecificFiles", verbose=args.verbose)
    progress.log(f"repo:                     {repo_root}")
    progress.log(f"roots_dir:                {roots_dir}")
    progress.log(f"target_dir:               {target_dir}")
    progress.log(f"file_based_routing_pages: {file_based_routing_pages}")

    # ── assert clean working tree ─────────────────────────────────────────────
    original_branch = get_current_branch(repo_root)
    try:
        ensure_clean_worktree(repo_root)
    except RuntimeError as exc:
        warning = f"Warning: {exc} Proceeding anyway because this workflow uses an isolated worktree."
        print(warning, file=sys.stderr)
        progress.log(warning)

    progress.log(f"Original branch: {original_branch}")

    # ── find actual git root (may differ from repo_root for monorepos) ────────
    git_root = get_git_root(repo_root)
    progress.log(f"git_root:                 {git_root}")

    # ── create main branch + worktree ─────────────────────────────────────────
    run_prefix, main_branch = build_main_branch_names("collectPageSpecificFiles")
    main_wt = create_branch_with_worktree(repo_root, main_branch, original_branch)
    progress.log(f"Main branch:   {main_branch}")
    progress.log(f"Main worktree: {main_wt}")

    # ── collect files ─────────────────────────────────────────────────────────
    # Root files: direct .ts/.tsx children of roots_dir only
    root_files: list[Path] = [
        p for p in roots_dir.iterdir()
        if p.is_file() and p.suffix in (".ts", ".tsx")
    ]
    # Target files: all .ts/.tsx files in target_dir (recursive)
    target_files = find_all_ts_files(target_dir)
    # All TS files in the repo (for importer map)
    all_ts_files = find_all_ts_files(repo_root)

    progress.log(f"Root files ({len(root_files)}): {[p.name for p in root_files]}")
    progress.log(f"Target files: {len(target_files)}")
    progress.log(f"Total TS files scanned: {len(all_ts_files)}")

    # ── compute ancestry claims ───────────────────────────────────────────────
    claims = compute_page_claims(
        roots_dir, target_files, root_files, all_ts_files, repo_root, progress
    )

    if not claims:
        progress.log("No page-specific files found — nothing to move.")
        print("No page-specific files found.")
        try:
            remove_worktree(repo_root, main_wt)
        except Exception:
            pass
        return 0

    progress.section(f"Moving {len(claims)} file(s)")
    moves = perform_moves(
        claims, roots_dir, repo_root, git_root, main_wt, file_based_routing_pages, progress
    )

    if not moves:
        progress.log("No moves performed (all root files were special/skipped).")
        print("No files moved (all root files were skipped).")
        try:
            remove_worktree(repo_root, main_wt)
        except Exception:
            pass
        return 0

    # ── fix import paths in all worktree TS files ─────────────────────────────
    progress.section("Updating import paths")
    wt_app_dir = main_wt / repo_root.relative_to(git_root)
    wt_all_ts = find_all_ts_files(wt_app_dir)
    updated_count = 0
    for wt_file in wt_all_ts:
        if _update_imports_in_file(wt_file, moves, repo_root):
            progress.log(f"  Updated imports in {wt_file.relative_to(main_wt)}")
            updated_count += 1

    progress.log(f"Files with updated imports: {updated_count}")

    # ── commit ────────────────────────────────────────────────────────────────
    progress.section("Committing")
    diff = get_staged_diff(main_wt)
    sha = commit_all(main_wt, "collectPageSpecificFiles: move page-specific files")
    progress.log(f"Committed: {sha}")
    progress.log_diff(diff)

    # ── cleanup ───────────────────────────────────────────────────────────────
    progress.section("Cleanup")
    try:
        remove_worktree(repo_root, main_wt)
        progress.log(f"Removed worktree: {main_wt}")
    except Exception as exc:
        progress.log(f"Warning: could not remove worktree {main_wt}: {exc}")

    # ── summary ───────────────────────────────────────────────────────────────
    progress.section("Summary")
    progress.log(f"Branch: {main_branch}")
    for old, new in moves.items():
        progress.log(f"  {old.relative_to(repo_root)} → {new.relative_to(repo_root)}")

    print()
    print("╔═══════════════════════════════════════════════════╗")
    print("║       collectPageSpecificFiles — complete         ║")
    print("╠═══════════════════════════════════════════════════╣")
    print(f"║  Files moved:   {len(moves):<35} ║")
    print(f"║  Imports fixed: {updated_count:<35} ║")
    print("╠═══════════════════════════════════════════════════╣")
    for old, new in moves.items():
        line = f"{old.relative_to(repo_root)} → {new.relative_to(repo_root)}"
        print(f"║  {line:<49} ║")
    print("╠═══════════════════════════════════════════════════╣")
    print(f"║  Branch: {main_branch[-42:]:<42} ║")
    print("╚═══════════════════════════════════════════════════╝")
    print(f"\nProgress log: {progress.log_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
