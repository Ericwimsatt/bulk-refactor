"""findSingleUseExports.py — locate exported TypeScript functions used in exactly one other file."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tasks.oneExportPerFile.shell_runner import run_cmd
from tasks.oneExportPerFile.tsxConstants import EXPORT_DECL_RE, EXPORT_BRACE_RE


# ── data classes ──────────────────────────────────────────────────────────────


@dataclass
class FunctionTarget:
    """An exported function that is imported by exactly one other file."""

    name: str
    source_file: Path  # file that defines/exports this name
    caller_file: Path  # the single file that imports it
    body_lines: int    # non-blank lines inside the function body (0 if not a function)
    body_text: str     # text between outer { ... } (or full decl for arrow expressions)


# ── helper: find all TypeScript/TSX files that import a given name ────────────


def find_all_importers(name: str, repo_root: Path, exclude_file: Path) -> list[Path]:
    """Return all .ts/.tsx files that reference *name* in an import statement.

    Searches the entire repo (not just src/) to handle monorepos.
    """
    try:
        hits_raw = run_cmd(
            [
                "grep",
                "-rl",
                "--include=*.ts",
                "--include=*.tsx",
                rf"\b{name}\b",
                str(repo_root),
                "--exclude-dir=node_modules",
                "--exclude-dir=.git",
                "--exclude-dir=.bulk-refactor-worktrees",
            ],
            cwd=repo_root,
            check=False,
        )
    except Exception:
        return []

    importers: list[Path] = []
    for hit_path_str in hits_raw.splitlines():
        candidate = Path(hit_path_str).resolve()
        if candidate == exclude_file.resolve():
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        if re.search(
            rf"(?:import|export)\b[^;]*\b{re.escape(name)}\b",
            text,
        ):
            importers.append(candidate)

    return importers


# ── helper: extract function bounds from TypeScript source ────────────────────


def extract_function_bounds(content: str, name: str) -> tuple[int, int] | None:
    """Return (start_pos, end_pos) character offsets for the function named *name*.

    Handles:
    - function name(...) { ... }
    - async function name(...) { ... }
    - export function name(...) { ... }
    - const name = (...) => { ... }
    - const name = (...) => expr   (no braces — returns expr span)
    - export const name = ...

    Returns None if the function cannot be found.
    """
    # Pattern 1: function declaration style
    fn_decl_pat = re.compile(
        rf"(?:export\s+)?(?:async\s+)?function\s+{re.escape(name)}\s*[<(]",
        re.MULTILINE,
    )
    # Pattern 2: const arrow function style
    arrow_pat = re.compile(
        rf"(?:export\s+)?const\s+{re.escape(name)}\s*[=:][^;{{]*?(?:async\s+)?(?:\([^)]*\)|[A-Za-z_]\w*)\s*=>",
        re.MULTILINE | re.DOTALL,
    )

    m = fn_decl_pat.search(content)
    if m is None:
        m = arrow_pat.search(content)
    if m is None:
        return None

    start = m.start()

    # Find the opening brace for the body
    brace_search_start = m.end()
    brace_pos = content.find("{", brace_search_start)

    # Check if this is an arrow function with an expression body (no brace after =>)
    arrow_indicator = content[m.end() : brace_search_start + 80]
    semicolon_pos = content.find(";", brace_search_start)
    newline_pos = content.find("\n", brace_search_start)

    if brace_pos == -1 or (
        semicolon_pos != -1
        and semicolon_pos < brace_pos
        and not re.search(r"\(|\[", content[brace_search_start:semicolon_pos])
    ):
        # Expression body arrow: "const name = x => expr;"
        end = (semicolon_pos + 1) if semicolon_pos != -1 else len(content)
        return start, end

    # Walk forward matching braces
    depth = 0
    i = brace_pos
    while i < len(content):
        ch = content[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
        # Skip strings to avoid false brace matches
        elif ch in ('"', "'", "`"):
            quote = ch
            i += 1
            while i < len(content):
                if content[i] == "\\" :
                    i += 2
                    continue
                if content[i] == quote:
                    break
                i += 1
        i += 1

    return None


def count_body_lines(content: str, start: int, end: int) -> tuple[int, str]:
    """Return (non_blank_line_count, body_text) for the function slice content[start:end].

    Body lines are lines between the first '{' and last '}' of the slice,
    or the entire slice for expression-body arrows.
    """
    func_text = content[start:end]

    brace_open = func_text.find("{")
    brace_close = func_text.rfind("}")

    if brace_open == -1 or brace_close == -1:
        # Expression body
        body = func_text
    else:
        body = func_text[brace_open + 1 : brace_close]

    non_blank = [ln for ln in body.splitlines() if ln.strip()]
    return len(non_blank), body


# ── main entry point ──────────────────────────────────────────────────────────


def find_single_use_exports(
    target_files: list[Path],
    repo_root: Path,
    max_body_lines: int | None = None,
) -> list[FunctionTarget]:
    """Scan *target_files* and return exported symbols used in exactly 1 other file.

    Args:
        target_files: .ts/.tsx files to analyse (from the target directory).
        repo_root:    root of the repository to search for importers.
        max_body_lines: if set, only include candidates whose body is at most this many lines.
                        If None, include all single-use exports regardless of size.
    """
    targets: list[FunctionTarget] = []

    for source_file in target_files:
        try:
            content = source_file.read_text(encoding="utf-8")
        except OSError:
            continue

        # Collect all exported names from this file
        names: list[str] = [m.group(1) for m in EXPORT_DECL_RE.finditer(content)]
        for m in EXPORT_BRACE_RE.finditer(content):
            for item in m.group(1).split(","):
                item = item.strip()
                if not item:
                    continue
                parts = re.split(r"\bas\b", item)
                exported_name = parts[-1].strip()
                if exported_name and exported_name not in names:
                    names.append(exported_name)

        for name in names:
            importers = find_all_importers(name, repo_root, source_file)
            if len(importers) != 1:
                continue  # 0 or >1 consumers — skip

            caller_file = importers[0]

            # Extract function body to count lines
            bounds = extract_function_bounds(content, name)
            if bounds is None:
                # Can't find function — treat as 0 body lines (e.g. type, interface)
                body_lines, body_text = 0, ""
            else:
                body_lines, body_text = count_body_lines(content, *bounds)

            if max_body_lines is not None and body_lines > max_body_lines:
                continue

            targets.append(
                FunctionTarget(
                    name=name,
                    source_file=source_file,
                    caller_file=caller_file,
                    body_lines=body_lines,
                    body_text=body_text,
                )
            )

    return targets
