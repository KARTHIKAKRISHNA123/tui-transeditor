# tui/widgets/log_panel.py
"""Live scrolling log panel — no emojis."""
from __future__ import annotations

import time

from textual.widgets import RichLog


class LogPanel(RichLog):

    def __init__(self) -> None:
        super().__init__(
            id="live-log",
            highlight=True,
            markup=True,
            wrap=True,
            max_lines=200,
        )

    def line(self, text: str, level: str = "info") -> None:
        """Write one timestamped log line."""
        ts = time.strftime("%H:%M:%S")
        colour = {"error": "red", "warn": "yellow", "success": "green"}.get(
            level, ""
        )
        if colour:
            self.write(f"[dim]{ts}[/]  [{colour}]{text}[/]")
        else:
            self.write(f"[dim]{ts}[/]  {text}")
