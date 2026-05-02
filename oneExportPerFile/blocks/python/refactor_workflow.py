from __future__ import annotations

from pathlib import Path
import subprocess
import os

from gitOperations.branch_manager import (
    checkout_branch,
    commit_all,
    create_branch,
    ensure_clean_worktree,
    get_current_branch,
)
from .config import WorkflowConfig, detect_typecheck_command
from .deterministic_refactor import run_deterministic_refactor
from .file_inventory import find_candidate_files
from .state_store import create_state


def _vlog(cfg: WorkflowConfig, message: str) -> None:
    if cfg.verbose:
        print(f"[oneExportPerFile] {message}")


def _is_typescript_file(path: str) -> bool:
    return path.endswith(".ts") or path.endswith(".tsx")


def _sanitize_filename_for_branch(filename: str) -> str:
    """Convert a filename to a git branch-safe name."""
    # Remove directory separators and file extensions
    name = filename.replace("/", "-").replace("\\", "-")
    name = name.rsplit(".", 1)[0]  # Remove extension
    # Keep only alphanumeric, hyphens, underscores
    name = "".join(c if c.isalnum() or c in "-_" else "-" for c in name)
    # Remove leading/trailing hyphens
    name = name.strip("-")
    return name


def _generate_branch_name(repo_root: Path, target_file_rel: str, action: str) -> str:
    """Generate a git branch name based on the action and target file."""
    sanitized = _sanitize_filename_for_branch(target_file_rel)
    
    action_prefix = {
        "delete": "delete",
        "no-new-files": "keep",
        "shared-split": "split",
        "shared-split-review": "split-review",
        "no-action": "no-op",
    }.get(action, "process")
    
    return f"{action_prefix}/{sanitized}"



def _run_typecheck_if_needed(repo_root: Path, target_file: str) -> tuple[bool, list[str]]:
    if not _is_typescript_file(target_file):
        return True, []

    command = detect_typecheck_command(repo_root)
    if not command:
        return True, ["No typecheck command found; skipped TypeScript gate"]

    proc = subprocess.run(
        command,
        cwd=str(repo_root),
        check=False,
        text=True,
        capture_output=True,
    )

    if proc.returncode == 0:
        return True, [f"Typecheck passed: {' '.join(command)}"]

    details = (
        f"Typecheck failed for {target_file} using {' '.join(command)}\n"
        f"stdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}"
    )
    return False, [details]


def run_one_export_workflow(cfg: WorkflowConfig) -> Path:
    repo_root = cfg.repo_root.resolve()
    _vlog(cfg, f"Starting workflow for repo={repo_root} dir={cfg.target_dir}")
    ensure_clean_worktree(repo_root)
    base_branch = get_current_branch(repo_root)
    _vlog(cfg, f"Detected base branch: {base_branch}")
    state = create_state(cfg.state_dir, repo_root, cfg.target_dir, base_branch)
    _vlog(cfg, f"State file created: {state.file_path}")

    operation_branch = create_branch(repo_root, base_branch, f"operation-{cfg.target_dir}")
    state.data["operation_branch"] = operation_branch
    state.save()
    _vlog(cfg, f"Created operation branch: {operation_branch}")

    # Ensure shared folder exists on the operation branch for split outputs.
    shared_dir = (repo_root / "shared").resolve()
    try:
        shared_dir.mkdir(parents=True, exist_ok=True)
        _vlog(cfg, f"shared directory ready: {shared_dir}")
    except Exception as e:
        error_msg = f"Failed to create or access shared directory at {shared_dir}: {e}"
        _vlog(cfg, error_msg)
        state.add_error(error_msg)
        state.set_status("error")
        return state.file_path

    candidates = find_candidate_files(repo_root, cfg.target_dir, cfg.max_files)
    state.data["candidates"] = candidates
    state.save()
    _vlog(cfg, f"Found {len(candidates)} candidate files")

    if not candidates:
        _vlog(cfg, "No candidates found; exiting")
        state.set_status("no-op")
        return state.file_path

    for target_file in candidates:
        _vlog(cfg, f"Processing file: {target_file}")
        state.mark_file(target_file, "started")
        
        try:
            _vlog(cfg, f"Running deterministic export split for: {target_file}")
            deterministic = run_deterministic_refactor(repo_root, target_file, shared_dir)
            action = deterministic.get("action", "no-action")
            notes = deterministic.get("notes", [])
            _vlog(cfg, f"Action: {action}; " + "; ".join(notes) if notes else "Deterministic pass completed")

            # Generate branch name based on action
            branch = _generate_branch_name(repo_root, target_file, action)
            _vlog(cfg, f"Generated branch name: {branch}")
            branch = create_branch(repo_root, operation_branch, branch)  # create_branch will make it unique if needed
            state.mark_file(target_file, "branch-created", branch=branch)
            _vlog(cfg, f"Created and checked out branch: {branch}")

            # Handle file deletion if needed
            if action == "delete":
                target_file_path = (repo_root / target_file).resolve()
                target_file_path.unlink()
                _vlog(cfg, f"Deleted file: {target_file}")
                notes.append(f"File deleted: {target_file}")

            # Check for manual review needed
            if deterministic.get("manual_review_required", False):
                _vlog(cfg, "Manual review required; pausing")
                state.add_branch_record(
                    branch=branch,
                    file_path=target_file,
                    status="manual-review-required",
                    approved=False,
                    notes=notes,
                )
                state.mark_file(target_file, "manual-review-required", branch=branch)
                state.set_status("paused-for-manual-review")
                return state.file_path

            typecheck_ok, typecheck_notes = _run_typecheck_if_needed(repo_root, target_file)
            if not typecheck_ok:
                _vlog(cfg, "Typecheck failed; pausing for manual review")
                state.add_branch_record(
                    branch=branch,
                    file_path=target_file,
                    status="manual-review-required",
                    approved=False,
                    notes=[*notes, *typecheck_notes],
                )
                state.mark_file(target_file, "manual-review-required", branch=branch)
                state.set_status("paused-for-manual-review")
                return state.file_path
            if typecheck_notes:
                _vlog(cfg, "; ".join(typecheck_notes))

            commit = commit_all(repo_root, f"refactor({target_file}): {action}")
            _vlog(cfg, f"Commit created={bool(commit)}")
            state.add_branch_record(
                branch=branch,
                file_path=target_file,
                status="committed" if commit else "no-changes",
                commit=commit,
                approved=True,
                notes=[*notes, *typecheck_notes],
            )
            state.mark_file(target_file, "committed" if commit else "no-changes", branch=branch)
            checkout_branch(repo_root, operation_branch)
            _vlog(cfg, f"Returned to operation branch: {operation_branch}")
        except Exception as exc:
            _vlog(cfg, f"Error while processing {target_file}: {exc}")
            state.add_error(f"{target_file}: {exc}")
            state.mark_file(target_file, "error", branch=target_file)
            state.set_status("error")
            return state.file_path

    _vlog(cfg, "Workflow completed successfully")
    state.set_status("completed")
    return state.file_path
