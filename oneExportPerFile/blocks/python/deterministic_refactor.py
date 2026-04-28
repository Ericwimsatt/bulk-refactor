from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
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
    if not specifier.startswith("."):
        return None

    base = (importer.parent / specifier).resolve()
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
    m = re.search(r"import\s*\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]", statement, flags=re.DOTALL)
    if not m:
        return []
    raw = m.group(1)
    symbols: list[str] = []
    for piece in raw.split(","):
        part = piece.strip()
        if not part:
            continue
        left = part.split(" as ")[0].strip()
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


def _module_specifier(from_file: Path, to_file: Path) -> str:
    rel = os.path.relpath(str(to_file), str(from_file.parent))
    spec = rel.replace("\\", "/")
    if not spec.startswith("."):
        spec = f"./{spec}"
    # Prefer extensionless import specifiers for JS/TS projects.
    return re.sub(r"\.(ts|tsx|js|jsx)$", "", spec)


def _safe_wrapper_filename(symbol: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_$]+", "_", symbol).strip("_")
    return clean or "exported_symbol"


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

    blockers: list[str] = []
    for decl in used_decls:
        for usage in usage_map[decl.name]:
            if not usage.is_single_symbol_named_import:
                rel_importer = usage.importer.relative_to(repo_root)
                blockers.append(
                    f"Unsupported multi-symbol import usage for {decl.name} in {rel_importer}: {usage.statement.strip()}"
                )

    if blockers:
        return {
            "notes": [
                "Deterministic splitter paused because some imports cannot be safely rewritten automatically.",
                *blockers,
            ],
            "manual_review_required": True,
        }

    replacements: list[tuple[int, int, str]] = []
    for decl in decls:
        replacements.append((decl.start, decl.end, _strip_export_keyword(decl.snippet)))
    rewritten_target_content = _replace_ranges(content, replacements)

    target_file.write_text(rewritten_target_content, encoding="utf-8")

    target_ext = target_file.suffix
    target_stem = target_file.stem
    wrapper_for_symbol: dict[str, Path] = {}
    for decl in used_decls:
        wrapper_name = f"{target_stem}.{_safe_wrapper_filename(decl.name)}{target_ext}"
        wrapper_path = target_file.parent / wrapper_name
        rel_to_wrapper_target = _module_specifier(wrapper_path, target_file)
        wrapper_content = f"export {{ {decl.name} }} from \"{rel_to_wrapper_target}\";\n"
        wrapper_path.write_text(wrapper_content, encoding="utf-8")
        wrapper_for_symbol[decl.name] = wrapper_path

    import_pattern = re.compile(
        r"import\s*\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]\s*;?",
        flags=re.MULTILINE,
    )

    for decl in used_decls:
        symbol = decl.name
        wrapper_path = wrapper_for_symbol[symbol]
        for usage in usage_map[symbol]:
            importer_text = usage.importer.read_text(encoding="utf-8")

            def _rewriter(m: re.Match[str]) -> str:
                names = [p.strip() for p in m.group(1).split(",") if p.strip()]
                left_names = [p.split(" as ")[0].strip() for p in names]
                if len(left_names) != 1 or left_names[0] != symbol:
                    return m.group(0)

                new_spec = _module_specifier(usage.importer.resolve(), wrapper_path.resolve())
                return f'import {{ {m.group(1).strip()} }} from "{new_spec}";'

            updated = import_pattern.sub(_rewriter, importer_text)
            usage.importer.write_text(updated, encoding="utf-8")

    notes.append(
        f"Processed {len(decls)} exports: {len(used_decls)} used (split to wrappers), {len(unused_decls)} unused (unexported)."
    )

    return {"notes": notes, "manual_review_required": False}
