#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <repo_root> <symbol_or_path>" >&2
  exit 1
fi

repo_root="$1"
needle="$2"

cd "$repo_root"
rg --line-number --glob '!node_modules' --glob '!.git' "${needle}" .
