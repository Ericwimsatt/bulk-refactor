#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <repo_root> <old_path> <new_path>" >&2
  exit 1
fi

repo_root="$1"
old_path="$2"
new_path="$3"

cd "$repo_root"

# Intentionally broad; caller should run in a feature branch.
rg --files -g '*.js' -g '*.jsx' -g '*.ts' -g '*.tsx' | while read -r f; do
  if rg -q "${old_path}" "$f"; then
    "$(dirname "$0")/replace_string_in_file.sh" "$f" "$old_path" "$new_path"
  fi
done
