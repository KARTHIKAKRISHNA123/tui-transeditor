# orchestration/agents.py
"""Builds the four Agent objects from config + prompts. Injects LLMs via the
router and tools via the caller. Knows nothing about tasks or the crew."""
from __future__ import annotations

from pathlib import Path

import yaml
from crewai import Agent

from llm.router import ModelRouter


class AgentFactory:
    def __init__(self, config_dir: Path, prompts_dir: Path, agents_dir: Path,
                 router: ModelRouter) -> None:
        self._router = router
        self._prompts_dir = prompts_dir
        self._agents_dir = agents_dir
        self._cfg = yaml.safe_load((config_dir / "agents.yaml").read_text("utf-8"))
        # NO tools. Tools forced CrewAI into the ReAct "Thought/Action" loop,
        # which free models (Llama 4 Scout etc.) handle badly — they burned the
        # turn on tool-reasoning, leaked meta-commentary, and lost the context
        # passed between stages. Plain direct-output agents produce clean text
        # and properly use each prior stage's output. Glossary/language checks
        # are deterministic and live in the service layer instead.
        self._tools = {}

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