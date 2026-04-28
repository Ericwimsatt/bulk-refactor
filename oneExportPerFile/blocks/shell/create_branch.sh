#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <repo_root> <base_branch> <new_branch>" >&2
  exit 1
fi

repo_root="$1"
base_branch="$2"
new_branch="$3"

cd "$repo_root"

git checkout "$base_branch"
git checkout -b "$new_branch"
