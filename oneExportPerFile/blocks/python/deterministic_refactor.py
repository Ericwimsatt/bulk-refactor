from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess


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


@dataclass
class TopLevelDecl:
    name: str
    kind: str
    start: int
    end: int
    snippet: str


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


def _is_top_level_offset(text: str, offset: int) -> bool:
    depth = 0
    i = 0
    in_string: str | None = None
    in_line_comment = False
    in_block_comment = False

    while i < offset:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < offset else ""

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
            depth = max(0, depth - 1)
        i += 1

    return depth == 0


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

        if kind in {"function", "class", "enum", "interface"}:
            open_brace = content.find("{", m.end())
            if open_brace == -1:
                continue
            end = _scan_balanced_block(content, open_brace)
            while end < len(content) and content[end] in {" ", "\t"}:
                end += 1
            if end < len(content) and content[end] == ";":
                end += 1
        else:
            end = _scan_to_semicolon(content, m.end())

        decls.append(ExportDecl(name=name, kind=kind, start=start, end=end, snippet=content[start:end]))

    return decls


def parse_top_level_decls(content: str) -> list[TopLevelDecl]:
    patterns: list[tuple[str, re.Pattern[str]]] = [
        ("interface", re.compile(r"^\s*(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)", re.MULTILINE)),
        ("type", re.compile(r"^\s*(?:export\s+)?type\s+([A-Za-z_$][\w$]*)", re.MULTILINE)),
        ("enum", re.compile(r"^\s*(?:export\s+)?enum\s+([A-Za-z_$][\w$]*)", re.MULTILINE)),
        ("class", re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)", re.MULTILINE)),
        ("function", re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", re.MULTILINE)),
        ("const", re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)", re.MULTILINE)),
    ]

    decls: list[TopLevelDecl] = []
    for kind, pattern in patterns:
        for m in pattern.finditer(content):
            if not _is_top_level_offset(content, m.start()):
                continue
            name = m.group(1)
            start = m.start()
            if kind in {"interface", "enum", "class", "function"}:
                open_brace = content.find("{", m.end())
                if open_brace == -1:
                    continue
                end = _scan_balanced_block(content, open_brace)
                while end < len(content) and content[end] in {" ", "\t"}:
                    end += 1
                if end < len(content) and content[end] == ";":
                    end += 1
            else:
                end = _scan_to_semicolon(content, m.end())
            decls.append(TopLevelDecl(name=name, kind=kind, start=start, end=end, snippet=content[start:end]))

    decls.sort(key=lambda d: d.start)
    seen: set[str] = set()
    out: list[TopLevelDecl] = []
    for d in decls:
        if d.name in seen:
            continue
        seen.add(d.name)
        out.append(d)
    return out


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
        if left:
            symbols.append(left)
    return symbols


def collect_import_usages(repo_root: Path, target_file: Path, symbol: str) -> list[ImportUsage]:
    usages: list[ImportUsage] = []
    pattern = re.compile(r"import\s+[\s\S]*?from\s*['\"]([^'\"]+)['\"]\s*;?", flags=re.MULTILINE)

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


def _extract_imports_from_file(content: str) -> tuple[list[str], list[str]]:
    import_pattern = re.compile(r"^import\s+[\s\S]*?from\s*['\"]([^'\"]+)['\"]\s*;?", flags=re.MULTILINE)
    import_statements: list[str] = []
    imported_symbols_set: set[str] = set()
    for m in import_pattern.finditer(content):
        stmt = m.group(0)
        import_statements.append(stmt)
        imported_symbols_set.update(_extract_named_import_symbols(stmt))
    return import_statements, sorted(imported_symbols_set)


def _collect_identifiers(snippet: str) -> set[str]:
    ids = set(re.findall(r"\b([A-Za-z_$][A-Za-z0-9_$]*)\b", snippet))
    keywords = {
        "function", "class", "const", "let", "var", "return", "if", "else", "for", "while", "do", "switch",
        "case", "break", "continue", "try", "catch", "finally", "throw", "new", "typeof", "instanceof", "in", "of",
        "async", "await", "interface", "type", "export", "import", "from", "as", "default", "extends", "implements",
        "public", "private", "protected", "readonly", "static", "abstract", "declare", "enum", "namespace", "module",
        "true", "false", "null", "undefined", "this", "super", "void", "never", "any", "unknown", "string", "number",
        "boolean", "symbol", "object",
    }
    return ids - keywords


def _find_dependencies_in_snippet(snippet: str, available_symbols: set[str]) -> tuple[set[str], set[str]]:
    found = _collect_identifiers(snippet)
    return found & available_symbols, found - available_symbols


def _find_type_deps_for_snippet(snippet: str, all_decls: list[TopLevelDecl]) -> set[str]:
    names = {d.name for d in all_decls}
    used = _collect_identifiers(snippet) & names
    resolved = set(used)
    queue = list(used)
    by_name = {d.name: d for d in all_decls}
    while queue:
        name = queue.pop(0)
        decl = by_name.get(name)
        if not decl:
            continue
        nested = _collect_identifiers(decl.snippet) & names
        for dep in nested:
            if dep not in resolved:
                resolved.add(dep)
                queue.append(dep)
    return resolved


def _shared_filename(name: str, kind: str) -> str:
    base = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    suffix = {
        "function": "fn",
        "interface": "interface",
        "type": "type",
        "enum": "enum",
        "class": "class",
        "const": "const",
        "let": "const",
        "var": "const",
    }.get(kind, "const")
    return f"{base}.{suffix}.ts"


def _ensure_exported(snippet: str) -> str:
    stripped = snippet.lstrip()
    if stripped.startswith("export "):
        return snippet
    leading = snippet[: len(snippet) - len(stripped)]
    return f"{leading}export {stripped}"


def _filter_original_imports(import_statements: list[str], used_available: set[str]) -> list[str]:
    useful: list[str] = []
    for stmt in import_statements:
        symbols = _extract_named_import_symbols(stmt)
        used = [s for s in symbols if s in used_available]
        if not used:
            continue
        if len(used) == len(symbols):
            useful.append(stmt)
            continue
        match = re.search(r"from\s*['\"]([^'\"]+)['\"]", stmt)
        if not match:
            continue
        useful.append(f"import {{ {', '.join(used)} }} from '{match.group(1)}';")
    return useful


def _module_path_without_extension(file_path: Path) -> str:
    if file_path.suffix in {".ts", ".tsx", ".js", ".jsx"}:
        return str(file_path.with_suffix(""))
    return str(file_path)


def _build_new_import_specifier(importer: Path, original_specifier: str, destination: Path, repo_root: Path) -> str:
    destination_no_ext = Path(_module_path_without_extension(destination))

    if original_specifier.startswith("@/"):
        src_root = repo_root / "src"
        rel = destination_no_ext.relative_to(src_root).as_posix()
        return f"@/{rel}"

    if original_specifier.startswith("src/"):
        rel = destination_no_ext.relative_to(repo_root).as_posix()
        return rel

    import os
    rel_spec = os.path.relpath(str(destination_no_ext), start=str(importer.parent)).replace("\\", "/")
    if not rel_spec.startswith("."):
        rel_spec = f"./{rel_spec}"
    return rel_spec


def _parse_named_import_entries(statement: str) -> tuple[str, list[tuple[str, str, bool]]]:
    m = re.search(r"import\s+(.*?)\s+from\s*['\"]", statement, flags=re.DOTALL)
    if not m:
        return "", []
    import_clause = m.group(1).strip()
    brace_match = re.search(r"\{([^}]*)\}", import_clause, flags=re.DOTALL)
    if not brace_match:
        return import_clause, []

    default_part = import_clause[: brace_match.start()].strip().rstrip(",")
    raw_items = [p.strip() for p in brace_match.group(1).split(",") if p.strip()]

    entries: list[tuple[str, str, bool]] = []
    for raw in raw_items:
        is_type = raw.startswith("type ")
        item = raw[5:].strip() if is_type else raw
        if " as " in item:
            imported, local = [p.strip() for p in item.split(" as ", 1)]
        else:
            imported, local = item, item
        entries.append((imported, local, is_type))
    return default_part, entries


def _format_import_entries(entries: list[tuple[str, str, bool]], as_type: bool) -> str:
    rendered: list[str] = []
    for imported, local, _ in entries:
        if imported == local:
            rendered.append(imported)
        else:
            rendered.append(f"{imported} as {local}")
    kind = "import type" if as_type else "import"
    return f"{kind} {{ {', '.join(rendered)} }}"


def _rewrite_imports_to_split_files(
    repo_root: Path,
    target_file: Path,
    export_by_name: dict[str, ExportDecl],
    shared_dir: Path,
) -> tuple[int, list[str]]:
    pattern = re.compile(r"import\s+[\s\S]*?from\s*['\"]([^'\"]+)['\"]\s*;?", flags=re.MULTILINE)
    file_changes = 0
    notes: list[str] = []

    symbol_to_dest = {
        name: shared_dir / _shared_filename(name, decl.kind)
        for name, decl in export_by_name.items()
    }

    for importer in _candidate_source_files(repo_root):
        if importer.resolve() == target_file.resolve():
            continue
        text = importer.read_text(encoding="utf-8")
        replacements: list[tuple[int, int, str]] = []

        for m in pattern.finditer(text):
            statement = m.group(0)
            specifier = m.group(1)
            resolved = _resolve_import_target(importer, specifier)
            if not resolved or resolved.resolve() != target_file.resolve():
                continue

            default_part, entries = _parse_named_import_entries(statement)
            if not entries:
                continue

            keep_entries: list[tuple[str, str, bool]] = []
            moved_by_module_type: dict[tuple[str, bool], list[tuple[str, str, bool]]] = {}

            for imported, local, is_type in entries:
                dest = symbol_to_dest.get(imported)
                if not dest:
                    keep_entries.append((imported, local, is_type))
                    continue
                module = _build_new_import_specifier(importer, specifier, dest, repo_root)
                moved_by_module_type.setdefault((module, is_type), []).append((imported, local, is_type))

            new_lines: list[str] = []
            if default_part or keep_entries:
                parts: list[str] = []
                if default_part:
                    parts.append(default_part)
                if keep_entries:
                    keep_rendered = []
                    for imported, local, is_type in keep_entries:
                        prefix = "type " if is_type else ""
                        if imported == local:
                            keep_rendered.append(f"{prefix}{imported}")
                        else:
                            keep_rendered.append(f"{prefix}{imported} as {local}")
                    parts.append(f"{{ {', '.join(keep_rendered)} }}")
                new_lines.append(f"import {', '.join(parts)} from '{specifier}';")

            for (module, as_type), group_entries in sorted(moved_by_module_type.items(), key=lambda x: x[0][0]):
                new_lines.append(f"{_format_import_entries(group_entries, as_type)} from '{module}';")

            replacement = "\n".join(new_lines)
            replacements.append((m.start(), m.end(), replacement))

        if not replacements:
            continue

        new_text = _replace_ranges(text, replacements)
        if new_text != text:
            importer.write_text(new_text, encoding="utf-8")
            file_changes += 1

    notes.append(f"Updated imports in {file_changes} file(s) to use split Shared modules")
    return file_changes, notes


def _run_linter_on_shared_files(shared_dir: Path, repo_root: Path) -> tuple[bool, list[str]]:
    diagnostics: list[str] = []

    try:
        eslint = subprocess.run(
            ["npx", "eslint", str(shared_dir)],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=20,
        )
        if eslint.returncode != 0:
            out = (eslint.stdout or eslint.stderr or "").strip()
            diagnostics.append(f"ESLint found issues:\n{out}")
            return False, diagnostics
        diagnostics.append("ESLint passed")
    except Exception as exc:
        diagnostics.append(f"ESLint failed to run: {exc}")
        return False, diagnostics

    try:
        tsc = subprocess.run(
            ["npx", "tsc", "--noEmit", "--pretty", "false"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if tsc.returncode != 0:
            out = (tsc.stdout or tsc.stderr or "").strip()
            diagnostics.append(f"TypeScript check found issues:\n{out}")
            return False, diagnostics
        diagnostics.append("TypeScript check passed")
    except Exception as exc:
        diagnostics.append(f"TypeScript check failed to run: {exc}")
        return False, diagnostics

    return True, diagnostics


def _create_shared_exports(
    repo_root: Path,
    target_file: Path,
    used_decls: list[ExportDecl],
    content: str,
    shared_dir: Path,
) -> tuple[bool, list[str], list[str]]:
    notes: list[str] = []
    missing_deps_list: list[str] = []

    import_statements, imported_symbols = _extract_imports_from_file(content)
    available_symbols_set = set(imported_symbols)

    all_top_level = parse_top_level_decls(content)
    used_export_names = {d.name for d in used_decls}
    support_by_name: dict[str, TopLevelDecl] = {d.name: d for d in all_top_level if d.name not in used_export_names}
    export_by_name: dict[str, ExportDecl] = {d.name: d for d in used_decls}

    if not shared_dir.exists():
        shared_dir.mkdir(parents=True, exist_ok=True)
    notes.append(f"Using Shared directory: {shared_dir}")

    export_deps: dict[str, set[str]] = {}
    support_usage_count: dict[str, int] = {}
    for decl in used_decls:
        deps = _find_type_deps_for_snippet(decl.snippet, all_top_level)
        export_deps[decl.name] = deps
        for dep in deps:
            if dep in support_by_name:
                support_usage_count[dep] = support_usage_count.get(dep, 0) + 1

    shared_support = {name for name, count in support_usage_count.items() if count > 1}
    support_file_by_name = {name: _shared_filename(name, support_by_name[name].kind) for name in shared_support}
    export_file_by_name = {name: _shared_filename(name, export_by_name[name].kind) for name in export_by_name}

    # Emit helper/type files used by multiple exports.
    for name in sorted(shared_support):
        decl = support_by_name[name]
        used_available, _ = _find_dependencies_in_snippet(decl.snippet, available_symbols_set)
        import_lines = _filter_original_imports(import_statements, used_available)

        value_imports: list[str] = []
        for dep in sorted(_find_type_deps_for_snippet(decl.snippet, list(support_by_name.values()))):
            if dep in shared_support and dep != name:
                dep_decl = support_by_name[dep]
                module = f"./{support_file_by_name[dep].rsplit('.', 1)[0]}"
                if dep_decl.kind in {"interface", "type"}:
                    value_imports.append(f"import type {{ {dep} }} from '{module}';")
                else:
                    value_imports.append(f"import {{ {dep} }} from '{module}';")

        body = _ensure_exported(decl.snippet)
        file_content = "\n".join(import_lines + value_imports)
        if file_content:
            file_content += "\n\n"
        file_content += body + "\n"

        shared_path = shared_dir / support_file_by_name[name]
        shared_path.write_text(file_content, encoding="utf-8")
        notes.append(f"Created {shared_path.name} for shared symbol: {name}")

    for decl in used_decls:
        used_available, used_missing = _find_dependencies_in_snippet(decl.snippet, available_symbols_set)
        deps = export_deps.get(decl.name, set())

        type_imports: list[str] = []
        value_imports: list[str] = []
        inline_decls: list[TopLevelDecl] = []
        inlined_seen: set[str] = set()

        for dep in sorted(deps):
            if dep == decl.name:
                continue
            if dep in export_by_name:
                module = f"./{export_file_by_name[dep].rsplit('.', 1)[0]}"
                dep_kind = export_by_name[dep].kind
                if dep_kind in {"interface", "type"}:
                    type_imports.append(f"import type {{ {dep} }} from '{module}';")
                else:
                    value_imports.append(f"import {{ {dep} }} from '{module}';")
                continue
            if dep in support_file_by_name:
                module = f"./{support_file_by_name[dep].rsplit('.', 1)[0]}"
                dep_kind = support_by_name[dep].kind
                if dep_kind in {"interface", "type"}:
                    type_imports.append(f"import type {{ {dep} }} from '{module}';")
                else:
                    value_imports.append(f"import {{ {dep} }} from '{module}';")
                continue
            if dep in support_by_name and dep not in inlined_seen:
                inline_decls.append(support_by_name[dep])
                inlined_seen.add(dep)

        import_lines = _filter_original_imports(import_statements, used_available)
        prelude = "\n".join(import_lines + sorted(set(type_imports)) + sorted(set(value_imports)))

        inline_text = ""
        if inline_decls:
            inline_text = "\n\n".join(d.snippet for d in inline_decls) + "\n\n"

        file_content = ""
        if prelude:
            file_content += prelude + "\n\n"
        file_content += inline_text
        file_content += decl.snippet

        out_file = shared_dir / _shared_filename(decl.name, decl.kind)
        out_file.write_text(file_content, encoding="utf-8")
        notes.append(f"Created {out_file.name} with export: {decl.name}")

        known_symbols = set(export_by_name.keys()) | set(support_by_name.keys()) | available_symbols_set
        unresolved = sorted((used_missing - known_symbols) - {decl.name})
        if unresolved:
            missing_deps_list.append(f"{decl.name}: missing {', '.join(unresolved)}")

    rewritten_count, rewrite_notes = _rewrite_imports_to_split_files(
        repo_root=repo_root,
        target_file=target_file,
        export_by_name=export_by_name,
        shared_dir=shared_dir,
    )
    notes.extend(rewrite_notes)

    if rewritten_count == 0:
        notes.append("No importer files referenced the original module; split files are currently unreferenced")

    if target_file.exists():
        target_file.unlink()
        notes.append(f"Deleted original source file after split: {target_file.relative_to(repo_root)}")

    lint_ok, lint_notes = _run_linter_on_shared_files(shared_dir, repo_root)
    notes.extend(lint_notes)

    if not lint_ok:
        notes.append("Lint/typecheck issues detected; manual review required")
        return False, notes, missing_deps_list

    if missing_deps_list:
        notes.append("Possible missing dependencies detected:")
        notes.extend([f"  - {dep}" for dep in missing_deps_list])
        return False, notes, missing_deps_list

    return True, notes, missing_deps_list


def run_deterministic_refactor(repo_root: Path, target_file_rel: str, shared_dir: Path) -> dict:
    repo_root = repo_root.resolve()
    target_file = (repo_root / target_file_rel).resolve()
    content = target_file.read_text(encoding="utf-8")
    decls = parse_export_decls(content)

    notes: list[str] = []
    if len(decls) <= 1:
        return {
            "notes": ["No deterministic split needed (0 or 1 export declaration)."],
            "manual_review_required": False,
            "action": "no-action",
        }

    usage_map: dict[str, list[ImportUsage]] = {}
    for decl in decls:
        usage_map[decl.name] = collect_import_usages(repo_root, target_file, decl.name)

    used_decls = [d for d in decls if usage_map[d.name]]
    unused_decls = [d for d in decls if not usage_map[d.name]]
    notes.append(f"Scanned {len(decls)} exports: {len(used_decls)} used, {len(unused_decls)} unused")

    replacements: list[tuple[int, int, str]] = []
    for decl in unused_decls:
        replacements.append((decl.start, decl.end, _strip_export_keyword(decl.snippet)))
    rewritten_target_content = _replace_ranges(content, replacements)

    if rewritten_target_content != content:
        target_file.write_text(rewritten_target_content, encoding="utf-8")
        notes.append(f"Removed 'export' keyword from {len(unused_decls)} unused declarations")

    if len(used_decls) == 0:
        notes.append("All exports are unused; file should be deleted")
        return {"notes": notes, "manual_review_required": False, "action": "delete"}

    if len(used_decls) == 1:
        notes.append(f"Only 1 used export ({used_decls[0].name}); no new files needed")
        return {"notes": notes, "manual_review_required": False, "action": "no-new-files"}

    success, split_notes, missing_deps = _create_shared_exports(
        repo_root, target_file, used_decls, rewritten_target_content, shared_dir
    )
    notes.extend(split_notes)

    if not success:
        return {
            "notes": notes,
            "manual_review_required": True,
            "action": "shared-split-review",
            "missing_dependencies": missing_deps,
        }

    return {"notes": notes, "manual_review_required": False, "action": "shared-split"}
