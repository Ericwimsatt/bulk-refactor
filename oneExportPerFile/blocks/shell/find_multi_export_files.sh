#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <repo_root> <target_dir>" >&2
  exit 1
fi

repo_root="$1"
target_dir="$2"

cd "$repo_root"

# Heuristic pre-filter: files with at least two lines starting with export.
# Final decision is made in Python with a parser-like pass.
rg --files "$target_dir" -g '*.js' -g '*.jsx' -g '*.ts' -g '*.tsx' | while read -r file; do
  export_count=$(rg --line-number '^\s*export\s+' "$file" | wc -l | tr -d ' ')
  if [[ "$export_count" -ge 2 ]]; then
    echo "$file"
  fi
done
