# tui/widgets/qa_panel.py
"""QA verdict panel — no emojis."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, ProgressBar, Static


class QAPanel(Static):

    def compose(self) -> ComposeResult:
        with Vertical(id="qa-panel"):
            yield Label(" QA VERDICT", id="qa-title")
            yield ProgressBar(total=100, show_eta=False, id="qa-score-bar")
            yield Static("[dim]Awaiting pipeline run...[/]", id="qa-body")

    def set_verdict(self, passed: bool, score: float, reasons: list[str]) -> None:
        self.query_one("#qa-score-bar", ProgressBar).update(
            progress=int(score * 100)
        )
        body = self.query_one("#qa-body", Static)

        if passed:
            verdict_line = (
                f"[bold green] PASS[/]  [green]score {score:.0%}[/]"
            )
        else:
            verdict_line = (
                f"[bold red] FAIL[/]  [red]score {score:.0%}[/]"
            )

        if reasons:
            issues = "\n".join(
                f"  [dim]-[/] [yellow]{r[:60]}[/]"
                for r in reasons[:5]
            )
            body.update(f"{verdict_line}\n\n[dim]Issues:[/]\n{issues}")
        else:
            body.update(f"{verdict_line}\n\n[dim green]No issues found.[/]")

    def reset(self) -> None:
        self.query_one("#qa-score-bar", ProgressBar).update(progress=0)
        self.query_one("#qa-body", Static).update(
            "[dim]Awaiting pipeline run...[/]"
        )
