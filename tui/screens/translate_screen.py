# tui/screens/translate_screen.py
from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Label, Static, TextArea
from textual.widgets import Button   # add to imports at top


from services.translation_service import PipelineEvent, TranslationService
from tui.widgets.agent_status import AgentStatusPanel
from tui.widgets.log_panel import LogPanel
from tui.widgets.qa_panel import QAPanel
from tui.widgets.translation_panel import TranslationPanel

_AGENTS = ["translator", "reviewer", "corrector"]


class TranslateScreen(Screen):

    def __init__(self, service: TranslationService) -> None:
        super().__init__()
        self._service = service
        self._running = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="left-col"):
                yield AgentStatusPanel()
                yield QAPanel()
            with Vertical(id="right-col"):
                with Vertical(id="input-area"):
                    yield Label(" SOURCE LANGUAGE", id="lbl-src")
                    yield Input(
                        placeholder="Source language (e.g. English)",
                        id="src-lang",
                        value="English",
                    )
                    yield Label(" TARGET LANGUAGE", id="lbl-tgt")
                    yield Input(
                        placeholder="Target language (e.g. Tamil)",
                        id="tgt-lang",
                        value="Tamil",
                    )
                    yield Label(" SOURCE TEXT", id="lbl-text")
                    yield TextArea(id="source-input", language=None)
                    yield Button("TRANSLATE", id="run-btn", variant="primary")

                    yield Static("", id="status-bar")
                yield TranslationPanel()
                with Vertical(id="log-area"):
                    yield Label(" LIVE LOGS", id="log-title")
                    yield LogPanel()
        yield Footer()

    def on_mount(self) -> None:
        # Set TextArea height
        ta = self.query_one("#source-input", TextArea)
        ta.styles.height     = 8
        ta.styles.min_height = 8
        # Focus the source text first so user can type
        ta.focus()

    # ── THE TRIGGER: Input.Submitted on the trigger-input ────────────────
    # Input.Submitted fires when user presses Enter inside any Input widget.
    # VS Code never intercepts plain Enter in a focused single-line Input.
    # This is the most reliable trigger across ALL terminals and IDEs.

    def on_button_pressed(self, event) -> None:
        if event.button.id == "run-btn":
            event.stop()
            self._trigger_translation()

    # Also handle Enter in the language inputs for convenience
    @on(Input.Submitted, "#src-lang")
    @on(Input.Submitted, "#tgt-lang")
    def on_lang_submitted(self, event: Input.Submitted) -> None:
        # Tab to next field rather than triggering translation
        self.focus_next()

    def _set_status(self, msg: str) -> None:
        try:
            self.query_one("#status-bar", Static).update(msg)
        except Exception:
            pass

    def _trigger_translation(self) -> None:
        if self._running:
            self._set_status("[yellow]Already running — please wait...[/]")
            return

        text = self.query_one("#source-input", TextArea).text.strip()
        if not text:
            self._set_status(
                "[red]Source text is empty — type text above first[/]"
            )
            self.query_one("#source-input", TextArea).focus()
            return

        src = self.query_one("#src-lang", Input).value.strip() or "English"
        tgt = self.query_one("#tgt-lang", Input).value.strip() or "Tamil"
        self._start_pipeline(text, src, tgt)

    def _start_pipeline(self, text: str, src: str, tgt: str) -> None:
        self._running = True
        self._set_status(
            f"[bold #9d4edd]Translating ({src} → {tgt})...[/]"
        )
        for name in _AGENTS:
            self.query_one(AgentStatusPanel).set_status(name, "pending")
        self.query_one(TranslationPanel).set_output("")
        self.query_one(QAPanel).reset()
        self.query_one(LogPanel).line(
            f"[bold #9d4edd]Starting: {text[:60]}[/]"
        )
        self.run_pipeline(text, src, tgt)

    def _end_pipeline(self) -> None:
        self._running = False
        # Return focus to trigger input so user can hit Enter again
        try:
            self.query_one("#trigger-input", Input).focus()
        except Exception:
            pass

    @work(thread=True, exclusive=True, exit_on_error=False)
    def run_pipeline(self, text: str, src: str, tgt: str) -> None:
        try:
            result = self._service.translate(
                text, src, tgt, on_event=self._emit
            )
            self.app.call_from_thread(self._on_success, result)
        except Exception as exc:
            self.app.call_from_thread(self._on_error, str(exc))

    def _emit(self, event: PipelineEvent) -> None:
        self.app.call_from_thread(self._apply, event)

    def _apply(self, event: PipelineEvent) -> None:
        logs   = self.query_one(LogPanel)
        agents = self.query_one(AgentStatusPanel)
        output = self.query_one(TranslationPanel)

        if event.type == "stage_started":
            agents.set_status(event.stage, "running")
            self._set_status(f"[yellow]Running {event.stage}...[/]")
            logs.line(f"[yellow]> {event.stage}[/] running...")
        elif event.type == "stage_completed":
            agents.set_status(event.stage, "done")
            logs.line(f"[green]+ {event.stage}[/] done")
            if event.stage == "corrector" and event.payload:
                output.set_output(event.payload)
                self._set_status("[green]Translation ready[/]")
        elif event.type == "log":
            logs.line(f"[dim]{event.payload}[/]")
        elif event.type == "finished":
            logs.line(f"[#9d4edd]{event.payload}[/]")
        elif event.type == "error":
            logs.line(f"[red]{event.payload[:150]}[/]")
            self._set_status(f"[red]{event.payload[:80]}[/]")

    def _on_success(self, result) -> None:
        v = result.verdict
        self.query_one(QAPanel).set_verdict(v.passed, v.score, v.reasons)
        self.query_one(TranslationPanel).set_output(result.final_text)
        self._set_status(
            f"[green]Done in {result.elapsed:.1f}s — "
            f"press Enter in the box below for another[/]"
        )
        self.query_one(LogPanel).line(
            f"[green]DONE[/] [dim]{result.elapsed:.1f}s[/]"
        )
        self._end_pipeline()

    def _on_error(self, msg: str) -> None:
        self.query_one(LogPanel).line(f"[bold red]Error:[/] {msg[:200]}")
        self._set_status(f"[red]Error — see logs[/]")
        for name in _AGENTS:
            self.query_one(AgentStatusPanel).set_status(name, "fail")
        self._end_pipeline()
