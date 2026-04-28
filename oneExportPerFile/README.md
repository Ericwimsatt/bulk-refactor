# oneExportPerFile

Refactor JavaScript/TypeScript files to one exported symbol per file.

## What It Does

- Scans a target directory for files with multiple exports.
- Creates a fresh git branch per target file.
- Uses one general-purpose `smolagents` agent (Kimi model) to propose file operations.
- Applies those operations.
- For `.ts`/`.tsx` files, runs type checking and pauses for manual review if type checking fails.
- Uses the same agent to review the resulting diff.
- Commits only when review approves.
- Persists process state to JSON for tracking and undo workflows.

## Layout

- `oneExportPerFile.py`: CLI entrypoint
- `blocks/prompts/`: LLM prompt templates
- `blocks/shell/`: reusable shell scripts
- `blocks/python/`: orchestration + agent runtime
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

Optional model override:

```bash
python oneExportPerFile.py -repo /home/user/git/stemwise -dir src/hooks --model-id openrouter/moonshotai/kimi-k2-instruct
```

Use latest Kimi coding preset:

```bash
python oneExportPerFile.py -repo /home/user/git/stemwise -dir src/hooks --latest-kimi-coding
```

`--latest-kimi-coding` resolves model as:

- `$KIMI_CODING_MODEL` if set
- otherwise built-in default `openrouter/moonshotai/kimi-k2-instruct`

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
