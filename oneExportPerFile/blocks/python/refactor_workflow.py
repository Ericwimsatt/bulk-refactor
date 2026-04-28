from __future__ import annotations

from pathlib import Path
import subprocess

from .agent_runtime import AgentConfig, RefactorAgent, parse_json_response
from .branch_manager import (
    checkout_branch,
    commit_all,
    create_branch,
    ensure_clean_worktree,
    get_current_branch,
)
from .config import WorkflowConfig, detect_typecheck_command
from .deterministic_refactor import run_deterministic_refactor
from .file_inventory import find_candidate_files
from .shell_runner import run_cmd
from .state_store import create_state


def _vlog(cfg: WorkflowConfig, message: str) -> None:
    if cfg.verbose:
        print(f"[oneExportPerFile] {message}")


def _load_prompt(prompt_dir: Path, name: str) -> str:
    return (prompt_dir / name).read_text(encoding="utf-8")


def _is_typescript_file(path: str) -> bool:
    return path.endswith(".ts") or path.endswith(".tsx")


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

    candidates = find_candidate_files(repo_root, cfg.target_dir, cfg.max_files)
    state.data["candidates"] = candidates
    state.save()
    _vlog(cfg, f"Found {len(candidates)} candidate files")

    if not candidates:
        _vlog(cfg, "No candidates found; exiting")
        state.set_status("no-op")
        return state.file_path

    if cfg.dry_run:
        _vlog(cfg, "Dry run requested; saved candidates and exiting")
        state.set_status("dry-run-ready")
        return state.file_path

    _vlog(cfg, f"Initializing review agent with model: {cfg.model_id}")
    agent = RefactorAgent(AgentConfig(repo_root=repo_root, model_id=cfg.model_id))
    review_template = _load_prompt(cfg.prompt_dir, "review_changes.txt")

    for target_file in candidates:
        _vlog(cfg, f"Processing file: {target_file}")
        state.mark_file(target_file, "started")
        branch = create_branch(repo_root, base_branch, target_file)
        state.mark_file(target_file, "branch-created", branch=branch)
        _vlog(cfg, f"Created and checked out branch: {branch}")

        try:
            _vlog(cfg, f"Running deterministic export split for: {target_file}")
            deterministic = run_deterministic_refactor(repo_root, target_file)
            notes = deterministic.get("notes", [])
            _vlog(cfg, "; ".join(notes) if notes else "Deterministic pass completed")

            if deterministic.get("manual_review_required", False):
                _vlog(cfg, "Deterministic pass requires manual review; pausing")
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

            diff = run_cmd(["git", "diff", "--", "."], cwd=repo_root)
            _vlog(cfg, "Running agent review on generated diff")

            review_prompt = f"{review_template}\n\nDiff:\n{diff}\n"
            review_raw = agent.run_prompt(review_prompt)
            review = parse_json_response(review_raw)
            approved = bool(review.get("approve", False))
            reasons = review.get("reasons", [])
            risks = review.get("risks", [])
            _vlog(cfg, f"Agent review approved={approved}")

            if not approved:
                _vlog(cfg, "Agent review rejected changes; pausing for manual review")
                state.add_branch_record(
                    branch=branch,
                    file_path=target_file,
                    status="manual-review-required",
                    approved=False,
                    notes=[*notes, *typecheck_notes, *reasons, *risks],
                )
                state.mark_file(target_file, "manual-review-required", branch=branch)
                state.set_status("paused-for-manual-review")
                return state.file_path

            commit = commit_all(repo_root, f"refactor: one export per file for {target_file}")
            _vlog(cfg, f"Commit created={bool(commit)}")
            state.add_branch_record(
                branch=branch,
                file_path=target_file,
                status="committed" if commit else "no-changes",
                commit=commit,
                approved=True,
                notes=[*notes, *typecheck_notes, *reasons],
            )
            state.mark_file(target_file, "committed" if commit else "no-changes", branch=branch)
            checkout_branch(repo_root, base_branch)
            _vlog(cfg, f"Returned to base branch: {base_branch}")
        except Exception as exc:
            _vlog(cfg, f"Error while processing {target_file}: {exc}")
            state.add_error(f"{target_file}: {exc}")
            state.mark_file(target_file, "error", branch=branch)
            state.set_status("error")
            return state.file_path

    _vlog(cfg, "Workflow completed successfully")
    state.set_status("completed")
    return state.file_path
