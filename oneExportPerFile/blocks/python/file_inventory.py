from __future__ import annotations

from pathlib import Path
import re


EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}


def _count_named_reexports(content: str) -> int:
    count = 0
    for match in re.finditer(r"export\s*\{([^}]*)\}", content, flags=re.MULTILINE | re.DOTALL):
        inside = match.group(1)
        entries = [part.strip() for part in inside.split(",") if part.strip()]
        count += len(entries)
    return count


def count_exports(content: str) -> int:
    default_exports = len(re.findall(r"^\s*export\s+default\b", content, flags=re.MULTILINE))
    declarations = len(
        re.findall(
            r"^\s*export\s+(?:async\s+)?(?:const|let|var|function|class|interface|type|enum)\s+[A-Za-z_$][\w$]*",
            content,
            flags=re.MULTILINE,
        )
    )
    named_reexports = _count_named_reexports(content)
    return default_exports + declarations + named_reexports


def find_candidate_files(repo_root: Path, target_dir: str, max_files: int) -> list[str]:
    root = repo_root / target_dir
    if not root.exists():
        raise FileNotFoundError(f"Target dir does not exist: {root}")

    candidates: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in EXTENSIONS:
            continue
        content = path.read_text(encoding="utf-8")
        if count_exports(content) > 1:
            candidates.append(str(path.relative_to(repo_root)))
            if 0 < max_files <= len(candidates):
                break
    return candidates
