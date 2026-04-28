from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from .shell_runner import run_cmd


def parse_json_response(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("{"):
        return json.loads(raw)
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        raise ValueError(f"Could not parse JSON from model response: {raw[:200]}")
    return json.loads(match.group(0))


@dataclass
class AgentConfig:
    repo_root: Path
    model_id: str


class RefactorAgent:
    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        try:
            from smolagents import CodeAgent, LiteLLMModel, tool
        except Exception as exc:
            raise RuntimeError(
                "smolagents is required. Install dependencies from oneExportPerFile/requirements.txt"
            ) from exc

        repo_root = config.repo_root

        @tool
        def list_repo_files(glob_pattern: str = "**/*") -> str:
            """List files in repo for the provided glob pattern."""
            matches = [
                str(p.relative_to(repo_root))
                for p in repo_root.glob(glob_pattern)
                if p.is_file() and ".git/" not in str(p)
            ]
            return "\n".join(matches[:500])

        @tool
        def read_repo_file(relative_path: str) -> str:
            """Read a text file from repo using a relative path."""
            path = (repo_root / relative_path).resolve()
            if not str(path).startswith(str(repo_root.resolve())):
                raise ValueError("Path escapes repo root")
            return path.read_text(encoding="utf-8")

        @tool
        def run_repo_shell(command: str) -> str:
            """Run a safe shell command in repo. Prefer rg, git diff, ls, cat."""
            return run_cmd(["bash", "-lc", command], cwd=repo_root)

        self._model = LiteLLMModel(model_id=config.model_id)
        self._agent = CodeAgent(
            tools=[list_repo_files, read_repo_file, run_repo_shell],
            model=self._model,
        )

    def run_prompt(self, prompt: str) -> str:
        return str(self._agent.run(prompt))
