# oneExportPerFile

Refactor JavaScript/TypeScript files to one exported symbol per file.

## What It Does

- Scans a target directory for files with multiple exports.
- Creates a fresh git branch per target file.
- Uses a deterministic Python pipeline to refactor exports:
  - discovers exported declarations
  - checks whether each export is imported elsewhere
  - unexports declarations that are unused
  - splits used exports to one-export wrapper files and rewrites safe imports
- For `.ts`/`.tsx` files, runs type checking and pauses for manual review if type checking fails.
- Commits deterministic changes automatically when present.
- Persists process state to JSON for tracking and undo workflows.

## Layout

- `oneExportPerFile.py`: CLI entrypoint
- `blocks/shell/`: reusable shell scripts
- `blocks/python/`: orchestration + deterministic refactor logic
- `state/`: process state JSON files
- `logs/`: optional future logs

## Setup

```bash
cd /home/user/git/jedi/oneExportPerFile
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Run

Dry run to inspect candidate files:

```bash
python oneExportPerFile.py -repo /home/user/git/stemwise -dir src/hooks --dry-run
```

Execute workflow:

```bash
python oneExportPerFile.py -repo /home/user/git/stemwise -dir src/hooks
```

Execute with detailed progress logs:

```bash
python oneExportPerFile.py -repo /home/user/git/stemwise -dir src/hooks --verbose
```

## Important Safety Constraint

The workflow currently requires a clean git working tree in the target repo before it runs.

## State File

Each run creates:

- `state/process-<timestamp>-<id>.json`

It records:

- process status
- base branch
- branches created
- per-file progress
- commit hashes
- errors and review notes

This makes cleanup and undo operations scriptable later.
