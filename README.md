# jedi
Tools to make similar changes to many files across a repo. 
Tries to use deterministic string manipulation and falls back to agent calls to complete tasks.

# setup
Jedi makes calls to the OpenCode cli. OpenCode terminal must be installed on the machine before using Jedi.
https://opencode.ai/download

# Example Usage

## 1. Run a single function from the terminal

Inline short single-use exports in the `lib/` directory of a target repo:

```bash
python -m functions.inlineShortFunctions.inlineShortFunctions \
  --repo /path/to/manhunt/manhunt-app \
  --dir lib \
  --short-threshold 3 \
  --verbose
```

Or enforce one export per file across a hooks directory (A common pattern in lovable projects):

```bash
python -m functions.oneExportPerFile.oneExportPerFile \
  --repo /path/to/my-app \
  --dir src/hooks \
  --verbose
```

Progress is written to `jedi/src/Progress/process_{HHMMSS}_{YYYYMMDD}_{uid}/progress.md`.

---

Split large components first, then collect the resulting page-specific files into their page folders:

```bash
cd /path/to/jedi/src

python -m functions.splitLargeComponents.splitLargeComponents \
  --repo /path/to/manhunt/manhunt-app \
  --dir app \
  --components-dir components \
  --verbose

python -m functions.collectPageSpecificFiles.collectPageSpecificFiles \
  --repo /path/to/manhunt/manhunt-app \
  --roots-dir app \
  --target-dir components \
  --verbose
```

Each function creates its own git branch. Review and merge them in order once both finish.

---

## 3. Run the full refactor pipeline via an agent

Give a coding agent these instructions to run the complete pipeline with quality gates at each step. 
Inexpensive/free models are sufficient. The tasks are simple enough with enough safety checks that this works reliably.

```
1. Open a browser and manually verify the app works end-to-end.
2. Run `fallow --json > fallow_before.json` to capture a baseline score.
3. Run inlineShortFunctions:
     python -m functions.inlineShortFunctions.inlineShortFunctions \
       --repo /path/to/manhunt/manhunt-app --dir lib --verbose
4. Run static analysis and unit tests. Open a browser and confirm behavior is unchanged.
5. Run splitLargeComponents:
     python -m functions.splitLargeComponents.splitLargeComponents \
       --repo /path/to/manhunt/manhunt-app --dir app --components-dir components --verbose
6. Run static analysis and unit tests. Open a browser and confirm behavior is unchanged.
7. Run oneExportPerFile:
     python -m functions.oneExportPerFile.oneExportPerFile \
       --repo /path/to/manhunt/manhunt-app --dir src/hooks --verbose
8. Run static analysis and unit tests. Open a browser and confirm behavior is unchanged.
9. Run collectPageSpecificFiles:
     python -m functions.collectPageSpecificFiles.collectPageSpecificFiles \
       --repo /path/to/manhunt/manhunt-app --roots-dir app --target-dir components --verbose
10. Run static analysis and unit tests. Open a browser and confirm behavior is unchanged.
11. Run `fallow --json > fallow_after.json` and diff the two reports to show the score improvement.
```


# Progress tracking
The function runs can take a long time. Progress is tracked in a decicated folder per run in the jedi/Progress folder.

# Branch management
Each Jedi call will create at least one new branch, often multiple branches. It will automatically clean them up at the end of the runs if the merge branches flag is set to true.

```bash
cd /path/to/jedi/src
python -m lib.gitOperations.deleteJediBranches --repo /path/to/manhunt/manhunt-app
```