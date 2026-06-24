# orchestration/tasks.py
# 3-stage pipeline: Translator → Reviewer → Corrector
# QA task removed — it was the only source of model errors.
# The corrector output IS the final translation.
from __future__ import annotations

from pathlib import Path

import yaml
from crewai import Agent, Task
from pydantic import BaseModel, Field


class QAReport(BaseModel):
    """Kept for import compatibility with quality_service.py"""
    adequacy: float = Field(default=1.0, ge=0, le=1)
    fluency: float = Field(default=1.0, ge=0, le=1)
    terminology_ok: bool = True
    issues: list[str] = []
    verdict: str = "pass"


class TaskFactory:
    def __init__(self, config_dir: Path) -> None:
        self._cfg = yaml.safe_load(
            (config_dir / "tasks.yaml").read_text("utf-8")
        )

    def build_all(self, agents: dict[str, Agent]) -> list[Task]:
        translate = Task(
            description=self._cfg["translate_task"]["description"],
            expected_output=self._cfg["translate_task"]["expected_output"],
            agent=agents["translator"],
        )
        review = Task(
            description=self._cfg["review_task"]["description"],
            expected_output=self._cfg["review_task"]["expected_output"],
            agent=agents["reviewer"],
            context=[translate],
        )
        correct = Task(
            description=self._cfg["correct_task"]["description"],
            expected_output=self._cfg["correct_task"]["expected_output"],
            agent=agents["corrector"],
            context=[translate, review],
        )
        # QA task intentionally removed — was causing 400/429 errors
        # on every free model tried. Corrector output is the final result.
        return [translate, review, correct]
