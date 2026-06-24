# tui/widgets/translation_panel.py
"""Translation output panel — no emojis."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, Static


class TranslationPanel(Static):

    def compose(self) -> ComposeResult:
        with Vertical(id="output-area"):
            yield Label(" TRANSLATION OUTPUT", id="output-title")
            yield Static(
                "[dim]Translation will appear here...[/]",
                id="output-body",
            )

    def set_output(self, text: str) -> None:
        body = self.query_one("#output-body", Static)
        if text.strip():
            # Escape [ so Tamil/Unicode text never parses as Rich markup tags
            safe = text.replace("[", "\\[")
            body.update(safe)
        else:
            body.update("[dim]Translation will appear here...[/]")
