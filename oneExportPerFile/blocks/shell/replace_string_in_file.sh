#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <file> <old> <new>" >&2
  exit 1
fi

file="$1"
old="$2"
new="$3"

if [[ ! -f "$file" ]]; then
  echo "File not found: $file" >&2
  exit 1
fi

python3 - <<'PY' "$file" "$old" "$new"
from pathlib import Path
import sys

path = Path(sys.argv[1])
old = sys.argv[2]
new = sys.argv[3]
text = path.read_text(encoding='utf-8')
if old not in text:
    print(f"No match found for: {old}", file=sys.stderr)
    raise SystemExit(2)
path.write_text(text.replace(old, new), encoding='utf-8')
print(f"Updated: {path}")
PY
