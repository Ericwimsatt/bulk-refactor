#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <repo_root> <pathspec> <message>" >&2
  exit 1
fi

repo_root="$1"
pathspec="$2"
message="$3"

cd "$repo_root"

git add -- "$pathspec"
if git diff --cached --quiet; then
  echo "No staged changes to commit"
  exit 0
fi
git commit -m "$message"
