from __future__ import annotations

import json
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
from .file_inventory import find_candidate_files
from .shell_runner import run_cmd
from .state_store import create_state


def _load_prompt(prompt_dir: Path, name: str) -> str:
    return (prompt_dir / name).read_text(encoding="utf-8")


def _safe_repo_path(repo_root: Path, relative_path: str) -> Path:
    candidate = (repo_root / relative_path).resolve()
    if not str(candidate).startswith(str(repo_root.resolve())):
        raise ValueError(f"Path escapes repo root: {relative_path}")
    return candidate


def _apply_operations(repo_root: Path, operations: list[dict]) -> None:
    for op in operations:
        op_type = op.get("type")
        rel_path = op.get("path")
        if not rel_path:
            raise ValueError(f"Invalid operation missing path: {op}")

        abs_path = _safe_repo_path(repo_root, rel_path)

        if op_type in {"rewrite_file", "create_file"}:
            content = op.get("content")
            if content is None:
                raise ValueError(f"Operation missing content: {op}")
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(content, encoding="utf-8")
            continue

        if op_type == "delete_file":
            if abs_path.exists():
                abs_path.unlink()
            continue

        raise ValueError(f"Unknown operation type: {op_type}")


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
    ensure_clean_worktree(repo_root)
    base_branch = get_current_branch(repo_root)
    state = create_state(cfg.state_dir, repo_root, cfg.target_dir, base_branch)

    candidates = find_candidate_files(repo_root, cfg.target_dir, cfg.max_files)
    state.data["candidates"] = candidates
    state.save()

    if not candidates:
        state.set_status("no-op")
        return state.file_path

    if cfg.dry_run:
        state.set_status("dry-run-ready")
        return state.file_path

    agent = RefactorAgent(AgentConfig(repo_root=repo_root, model_id=cfg.model_id))
    refactor_template = _load_prompt(cfg.prompt_dir, "one_export_instructions.txt")
    review_template = _load_prompt(cfg.prompt_dir, "review_changes.txt")

    for target_file in candidates:
        state.mark_file(target_file, "started")
        branch = create_branch(repo_root, base_branch, target_file)
        state.mark_file(target_file, "branch-created", branch=branch)

        content = (repo_root / target_file).read_text(encoding="utf-8")
        sibling_files = sorted(
            str(p.relative_to(repo_root))
            for p in (repo_root / target_file).parent.glob("*")
            if p.is_file()
        )[:50]

        refactor_prompt = (
            f"{refactor_template}\n\n"
            f"target_file: {target_file}\n"
            f"nearby_files: {json.dumps(sibling_files)}\n"
            f"file_content:\n{content}\n"
        )

        try:
            refactor_raw = agent.run_prompt(refactor_prompt)
            refactor_plan = parse_json_response(refactor_raw)
            operations = refactor_plan.get("operations", [])
            notes = refactor_plan.get("notes", [])

            _apply_operations(repo_root, operations)
            typecheck_ok, typecheck_notes = _run_typecheck_if_needed(repo_root, target_file)
            if not typecheck_ok:
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

            diff = run_cmd(["git", "diff", "--", "."], cwd=repo_root)

            review_prompt = f"{review_template}\n\nDiff:\n{diff}\n"
            review_raw = agent.run_prompt(review_prompt)
            review = parse_json_response(review_raw)
            approved = bool(review.get("approve", False))
            reasons = review.get("reasons", [])
            risks = review.get("risks", [])

            if not approved:
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
        except Exception as exc:
            state.add_error(f"{target_file}: {exc}")
            state.mark_file(target_file, "error", branch=branch)
            state.set_status("error")
            return state.file_path

    state.set_status("completed")
    return state.file_path
