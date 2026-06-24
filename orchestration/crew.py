# orchestration/crew.py
"""Assembles the translation crew from config. The only file that imports both
factories. Reads workflows.yaml for runtime toggles."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import yaml
from crewai import Crew, Process

from llm.router import ModelRouter
from orchestration.agents import AgentFactory
from orchestration.tasks import TaskFactory


class TranslationCrew:
    def __init__(self, base_dir: Path) -> None:
        config_dir = base_dir / "config"
        self._wf = yaml.safe_load((config_dir / "workflows.yaml").read_text("utf-8"))
        router = ModelRouter(config_dir / "models.yaml")
        self._agent_factory = AgentFactory(
            config_dir, base_dir / "prompts", base_dir / "agents", router)
        self._task_factory = TaskFactory(config_dir)

    def build(self, task_callback: Callable | None = None) -> Crew:
        agents = self._agent_factory.build_all()
        tasks = self._task_factory.build_all(agents)
        return Crew(
            agents=list(agents.values()),
            tasks=tasks,
            process=Process.sequential,   # strict Translator→Reviewer→Corrector→QA
            memory=False,                 # ← OpenRouter has no embeddings endpoint
            verbose=self._wf["runtime"]["verbose"],
            task_callback=task_callback,  # fires when EACH task finishes → streaming
        )