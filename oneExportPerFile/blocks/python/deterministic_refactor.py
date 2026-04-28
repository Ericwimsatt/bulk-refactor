from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


JS_TS_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}


@dataclass
class ExportDecl:
    name: str
    kind: str
    start: int
    end: int
    snippet: str


@dataclass
class ImportUsage:
    importer: Path
    statement: str
    symbol: str
    is_single_symbol_named_import: bool


def _line_starts(text: str) -> list[int]:
    starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            starts.append(i + 1)
    return starts


def _line_start_offset(text: str, line_no: int) -> int:
    starts = _line_starts(text)
    idx = max(0, line_no - 1)
    if idx >= len(starts):
        return len(text)
    return starts[idx]


def _scan_balanced_block(text: str, open_index: int) -> int:
    depth = 0
    i = open_index
    in_string: str | None = None
    in_line_comment = False
    in_block_comment = False

    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == in_string:
                in_string = None
            i += 1
            continue

        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if ch in {"\"", "'", "`"}:
            in_string = ch
            i += 1
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1

    return len(text)


def _scan_to_semicolon(text: str, start_index: int) -> int:
    depth_paren = 0
    depth_brace = 0
    depth_bracket = 0
    i = start_index
    in_string: str | None = None
    in_line_comment = False
    in_block_comment = False

    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == in_string:
                in_string = None
            i += 1
            continue

        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if ch in {"\"", "'", "`"}:
            in_string = ch
            i += 1
            continue

        if ch == "(":
            depth_paren += 1
        elif ch == ")":
            depth_paren = max(0, depth_paren - 1)
        elif ch == "{":
            depth_brace += 1
        elif ch == "}":
            depth_brace = max(0, depth_brace - 1)
        elif ch == "[":
            depth_bracket += 1
        elif ch == "]":
            depth_bracket = max(0, depth_bracket - 1)

        if ch == ";" and depth_paren == 0 and depth_brace == 0 and depth_bracket == 0:
            return i + 1
        i += 1

    return len(text)


def parse_export_decls(content: str) -> list[ExportDecl]:
    pattern = re.compile(
        r"^\s*export\s+(?:async\s+)?(function|class|enum|interface|type|const|let|var)\s+([A-Za-z_$][\w$]*)",
        flags=re.MULTILINE,
    )

    decls: list[ExportDecl] = []
    for m in pattern.finditer(content):
        kind = m.group(1)
        name = m.group(2)
        start = m.start()
        end = len(content)

        if kind in {"function", "class", "enum", "interface"}:
            open_brace = content.find("{", m.end())
            if open_brace == -1:
                continue
            end = _scan_balanced_block(content, open_brace)
            # include trailing semicolon for declarations like `export interface X { ... };`
            while end < len(content) and content[end] in {" ", "\t"}:
                end += 1
            if end < len(content) and content[end] == ";":
                end += 1
        else:
            end = _scan_to_semicolon(content, m.end())

        decls.append(ExportDecl(name=name, kind=kind, start=start, end=end, snippet=content[start:end]))

    return decls


def _candidate_source_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in repo_root.rglob("*"):
        if not path.is_file() or path.suffix not in JS_TS_EXTENSIONS:
            continue
        s = str(path)
        if "/.git/" in s or "/node_modules/" in s:
            continue
        files.append(path)
    return files


def _resolve_import_target(importer: Path, specifier: str) -> Path | None:
    if specifier.startswith("."):
        base = (importer.parent / specifier).resolve()
    elif specifier.startswith("@/"):
        # Common Vite/TS alias where @ maps to repo_root/src.
        repo_root = importer
        while (repo_root / ".git").exists() is False and repo_root.parent != repo_root:
            repo_root = repo_root.parent
        base = (repo_root / "src" / specifier[2:]).resolve()
    elif specifier.startswith("src/"):
        repo_root = importer
        while (repo_root / ".git").exists() is False and repo_root.parent != repo_root:
            repo_root = repo_root.parent
        base = (repo_root / specifier).resolve()
    else:
        return None

    candidates = [base]
    for ext in [".ts", ".tsx", ".js", ".jsx"]:
        candidates.append(Path(str(base) + ext))
    for ext in [".ts", ".tsx", ".js", ".jsx"]:
        candidates.append(base / f"index{ext}")

    for c in candidates:
        if c.exists() and c.is_file():
            return c
    return None


def _extract_named_import_symbols(statement: str) -> list[str]:
    brace_match = re.search(r"\{([^}]*)\}", statement, flags=re.DOTALL)
    if not brace_match:
        return []
    raw = brace_match.group(1)
    symbols: list[str] = []
    for piece in raw.split(","):
        part = piece.strip()
        if not part:
            continue
        left = part.split(" as ")[0].strip()
        left = re.sub(r"^type\s+", "", left)
        if not left:
            continue
        symbols.append(left)
    return symbols


def collect_import_usages(repo_root: Path, target_file: Path, symbol: str) -> list[ImportUsage]:
    usages: list[ImportUsage] = []
    pattern = re.compile(
        r"import\s+[\s\S]*?from\s*['\"]([^'\"]+)['\"]\s*;?",
        flags=re.MULTILINE,
    )

    target_resolved = target_file.resolve()
    for path in _candidate_source_files(repo_root):
        if path.resolve() == target_resolved:
            continue
        text = path.read_text(encoding="utf-8")

        for m in pattern.finditer(text):
            statement = m.group(0)
            specifier = m.group(1)
            resolved = _resolve_import_target(path, specifier)
            if not resolved or resolved.resolve() != target_resolved:
                continue

            symbols = _extract_named_import_symbols(statement)
            if symbol not in symbols:
                continue

            usages.append(
                ImportUsage(
                    importer=path,
                    statement=statement,
                    symbol=symbol,
                    is_single_symbol_named_import=(len(symbols) == 1),
                )
            )

    return usages


def _strip_export_keyword(decl_text: str) -> str:
    return re.sub(r"^(\s*)export\s+", r"\1", decl_text, count=1)


def _replace_ranges(text: str, replacements: list[tuple[int, int, str]]) -> str:
    if not replacements:
        return text
    out: list[str] = []
    cursor = 0
    for start, end, repl in sorted(replacements, key=lambda x: x[0]):
        out.append(text[cursor:start])
        out.append(repl)
        cursor = end
    out.append(text[cursor:])
    return "".join(out)


def run_deterministic_refactor(repo_root: Path, target_file_rel: str) -> dict:
    repo_root = repo_root.resolve()
    target_file = (repo_root / target_file_rel).resolve()
    content = target_file.read_text(encoding="utf-8")
    decls = parse_export_decls(content)

    notes: list[str] = []
    if len(decls) <= 1:
        return {"notes": ["No deterministic split needed (0 or 1 export declaration)."], "manual_review_required": False}

    usage_map: dict[str, list[ImportUsage]] = {}
    for decl in decls:
        usage_map[decl.name] = collect_import_usages(repo_root, target_file, decl.name)

    used_decls = [d for d in decls if usage_map[d.name]]
    unused_decls = [d for d in decls if not usage_map[d.name]]

    # Never generate wrapper files or rewrite imports.
    # If multiple exports are currently used, deterministic automation cannot
    # enforce one-export-per-file without moving code and changing imports.
    if len(used_decls) > 1:
        return {
            "notes": [
                "Manual review required: multiple exports are used by other files.",
                "This mode never creates new files or rewrites imports.",
                "Only files with <= 1 used export can be auto-cleaned by unexporting unused declarations.",
                f"Used exports: {', '.join(d.name for d in used_decls)}",
            ],
            "manual_review_required": True,
        }

    replacements: list[tuple[int, int, str]] = []
    for decl in unused_decls:
        replacements.append((decl.start, decl.end, _strip_export_keyword(decl.snippet)))
    rewritten_target_content = _replace_ranges(content, replacements)

    if rewritten_target_content != content:
        target_file.write_text(rewritten_target_content, encoding="utf-8")

    notes.append(
        f"Processed {len(decls)} exports: {len(used_decls)} used (kept exported), {len(unused_decls)} unused (unexported)."
    )

    return {"notes": notes, "manual_review_required": False}
