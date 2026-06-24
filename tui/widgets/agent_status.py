# tui/widgets/agent_status.py
"""Agent pipeline status board — no emojis, pure ASCII symbols."""
from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Label, Static

_AGENTS: list[tuple[str, str]] = [
    ("translator", "Gemma 4 31B"),
    ("reviewer",   "Nemotron 120B"),
    ("corrector",  "GPT-OSS 120B"),
]

_STATUS_ICON = {
    "pending": "[ ]",
    "running": "[~]",
    "done":    "[+]",
    "fail":    "[!]",
}


class AgentRow(Static):

    def __init__(self, agent_id: str, label: str, model: str) -> None:
        super().__init__(
            classes="agent-row status-pending",
            id=f"row-{agent_id}",
        )
        self._agent_id = agent_id
        self._label    = label
        self._model    = model
        self._start: float | None = None

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label(
                _STATUS_ICON["pending"],
                id=f"icon-{self._agent_id}",
                classes="agent-icon",
            )
            yield Label(
                f" {self._label}",
                id=f"name-{self._agent_id}",
                classes="agent-name",
            )
            yield Label(
                self._model,
                id=f"model-{self._agent_id}",
                classes="agent-model",
            )
            yield Label("", id=f"time-{self._agent_id}", classes="agent-time")

    def set_status(self, status: str) -> None:
        self.set_classes(f"agent-row status-{status}")
        self.query_one(f"#icon-{self._agent_id}", Label).update(
            _STATUS_ICON[status]
        )
        if status == "running":
            self._start = time.perf_counter()
        elif status in ("done", "fail") and self._start:
            elapsed = time.perf_counter() - self._start
            self.query_one(f"#time-{self._agent_id}", Label).update(
                f"[dim]{elapsed:.1f}s[/]"
            )
            self._start = None


class AgentStatusPanel(Static):

    def compose(self) -> ComposeResult:
        with Vertical(id="agent-panel"):
            yield Label(" PIPELINE", id="pipeline-title")
            for agent_id, model in _AGENTS:
                yield AgentRow(agent_id, agent_id, model)

    def set_status(self, name: str, status: str) -> None:
        try:
            self.query_one(f"#row-{name}", AgentRow).set_status(status)
        except Exception:
            pass
