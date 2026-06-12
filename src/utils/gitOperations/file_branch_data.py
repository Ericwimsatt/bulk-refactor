from dataclasses import dataclass
from pathlib import Path

@dataclass
class FileBranchData:
    """Tracks a per-file branch/worktree pair used by refactor workflows."""

    file: Path
    file_branch: str
    file_wt: Path