from __future__ import annotations

import re

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

# Matches export { Foo, Bar as Baz } (named group exports, not re-exports from another module).
# We exclude export { ... } from '...' because those are re-exports of another file's symbols.
EXPORT_BRACE_RE = re.compile(
    r"^export\s*\{([^}]*)\}(?!\s*from\b)[;]?",
    re.MULTILINE,
)