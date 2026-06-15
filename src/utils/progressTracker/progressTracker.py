from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from utils.format_timestamp import format_timestamp

JEDI_ROOT = Path(__file__).resolve().parents[2]


class ProgressTracker:
    """Append-only progress logger used across automation scripts."""

    def __init__(self, run_name: str, verbose: bool = False) -> None:
        print(JEDI_ROOT)
        ts = format_timestamp()
        uid = uuid.uuid4().hex[:8]
        self.run_dir = JEDI_ROOT / "Progress" / f"process_{ts}_{uid}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.run_dir / "progress.md"
        self.verbose = verbose
        self._lock = threading.Lock()
        self._write(
            f"# {run_name} run\n\n"
            f"Started: {datetime.now(timezone.utc).isoformat()}\n\n"
        )

    def _write(self, text: str) -> None:
        with self._lock:
            with self.log_file.open("a", encoding="utf-8") as fh:
                fh.write(text)

    def log(self, message: str) -> None:
        if self.verbose:
            print(message)
        self._write(f"- {message}\n")

    def section(self, title: str) -> None:
        if self.verbose:
            print(f"\n=== {title} ===")
        self._write(f"\n## {title}\n\n")

    def log_diff(self, diff: str) -> None:
        if not diff:
            return
        self._write(f"\n```diff\n{diff}\n```\n\n")

    def log_output(self, label: str, output: str) -> None:
        if self.verbose and output:
            print(f"[{label}]:\n{output}")
        if output:
            self._write(f"\n### {label}\n\n```\n{output}\n```\n\n")

