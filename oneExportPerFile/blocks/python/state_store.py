from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
import json
from pathlib import Path
import uuid


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class ProcessState:
    file_path: Path
    data: dict

    def save(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")

    def add_branch_record(
        self,
        branch: str,
        file_path: str,
        status: str,
        commit: str | None = None,
        approved: bool | None = None,
        notes: list[str] | None = None,
    ) -> None:
        self.data.setdefault("branches", []).append(
            {
                "branch": branch,
                "file": file_path,
                "status": status,
                "commit": commit,
                "approved": approved,
                "notes": notes or [],
                "updated_at": _utc_now(),
            }
        )
        self.save()

    def mark_file(self, file_path: str, status: str, branch: str | None = None) -> None:
        files = self.data.setdefault("files", {})
        files[file_path] = {
            "status": status,
            "branch": branch,
            "updated_at": _utc_now(),
        }
        self.save()

    def add_error(self, message: str) -> None:
        self.data.setdefault("errors", []).append({"at": _utc_now(), "message": message})
        self.save()

    def set_status(self, status: str) -> None:
        self.data["status"] = status
        self.data["updated_at"] = _utc_now()
        self.save()


def create_state(state_dir: Path, repo_root: Path, target_dir: str, base_branch: str) -> ProcessState:
    process_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    state_path = state_dir / f"process-{process_id}.json"
    state = ProcessState(
        file_path=state_path,
        data={
            "process_id": process_id,
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "status": "started",
            "repo_root": str(repo_root),
            "target_dir": target_dir,
            "base_branch": base_branch,
            "branches": [],
            "files": {},
            "errors": [],
        },
    )
    state.save()
    return state
