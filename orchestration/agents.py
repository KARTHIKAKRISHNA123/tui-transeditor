# orchestration/agents.py
"""Builds the four Agent objects from config + prompts. Injects LLMs via the
router and tools via the caller. Knows nothing about tasks or the crew."""
from __future__ import annotations

from pathlib import Path

import yaml
from crewai import Agent

from llm.router import ModelRouter
from orchestration.tools import glossary_tool, language_tool


class AgentFactory:
    def __init__(self, config_dir: Path, prompts_dir: Path, agents_dir: Path,
                 router: ModelRouter) -> None:
        self._router = router
        self._prompts_dir = prompts_dir
        self._agents_dir = agents_dir
        self._cfg = yaml.safe_load((config_dir / "agents.yaml").read_text("utf-8"))
        # Each agent's tool loadout. Deterministic guards are NOT here — they
        # run in the service layer. (See the Slice 2 lesson.)
        self._tools = {
            "translator": [glossary_tool, language_tool],
            "reviewer":   [glossary_tool, language_tool],
            "corrector":  [glossary_tool],
            "qa":         [language_tool],
        }

    def _full_backstory(self, name: str) -> str:
        """Merge the three sources of truth: yaml backstory + prompt body +
        skills playbook. This is where the 'one fact, one home' contract pays off."""
        parts = [self._cfg[name]["backstory"]]
        prompt = self._prompts_dir / f"{name}.md"
        skills = self._agents_dir / name / "skills.md"
        if prompt.exists():
            parts.append(prompt.read_text("utf-8"))
        if skills.exists():
            parts.append(skills.read_text("utf-8"))
        return "\n\n".join(parts)

    def build(self, name: str) -> Agent:
        cfg = self._cfg[name]
        return Agent(
            role=cfg["role"],
            goal=cfg["goal"],
            backstory=self._full_backstory(name),
            llm=self._router.for_role(name),     # ← role→model indirection
            tools=self._tools.get(name, []),
            allow_delegation=False,              # sequential pipeline: no delegation
            verbose=False,
        )

    def build_all(self) -> dict[str, Agent]:
        # QA agent removed — no longer in the pipeline
        return {name: self.build(name)
                for name in ("translator", "reviewer", "corrector")}