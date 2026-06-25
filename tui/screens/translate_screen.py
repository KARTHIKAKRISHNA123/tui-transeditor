# tui/screens/translate_screen.py
# Minimal, robust translation screen. Priorities: always respond to the button,
# always show the output. No _running guard (it was getting stuck and blocking
# every click) — the worker's own exclusive=True handles concurrency.
from __future__ import annotations

import logging

from rich.markup import escape
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import (Button, Footer, Header, Input, Label, Static,
                             TextArea)

from services.translation_service import TranslationService

_log = logging.getLogger("tui.translate_screen")


class TranslateScreen(Screen):
    CSS = """
    Screen { layout: vertical; }
    #form { height: auto; padding: 1 2; }
    Label { color: $text-muted; margin-top: 1; }
    #src, #tgt { height: 3; }
    #source { height: 6; border: round $primary; }
    #run { margin-top: 1; }
    #status { height: 1; color: $warning; padding: 0 2; }
    #out-title { color: $accent; margin-top: 1; padding: 0 2; }
    #output {
        height: 1fr; border: round $accent; padding: 1; margin: 0 2 1 2;
        background: $surface;
    }
    """

    def __init__(self, service: TranslationService) -> None:
        super().__init__()
        self._service = service

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="form"):
            yield Label("SOURCE LANGUAGE")
            yield Input(value="English", id="src")
            yield Label("TARGET LANGUAGE")
            yield Input(value="Tamil", id="tgt")
            yield Label("SOURCE TEXT")
            yield TextArea(id="source")
            yield Button("TRANSLATE", id="run", variant="primary")
        yield Static("", id="status")
        yield Label("TRANSLATION OUTPUT", id="out-title")
        yield Static("[dim]Translation will appear here...[/]", id="output")
        yield Footer()

    def on_mount(self) -> None:
        _log.info("TranslateScreen mounted")
        self.query_one("#source", TextArea).focus()

    @on(Button.Pressed, "#run")
    def _go(self, event: Button.Pressed) -> None:
        event.stop()
        text = self.query_one("#source", TextArea).text.strip()
        if not text:
            self.query_one("#status", Static).update(
                "[red]Type some source text first[/]"
            )
            return
        src = self.query_one("#src", Input).value.strip() or "English"
        tgt = self.query_one("#tgt", Input).value.strip() or "Tamil"

        # Immediate feedback on the MAIN thread, before any worker — so the
        # click is always visibly acknowledged.
        self.query_one("#status", Static).update(f"[yellow]Translating {src} -> {tgt}...[/]")
        self.query_one("#output", Static).update("[dim]Working...[/]")
        _log.info("TRANSLATE clicked: %s -> %s", src, tgt)
        self._run(text, src, tgt)

    @work(exclusive=True, thread=True)
    def _run(self, text: str, src: str, tgt: str) -> None:
        # Runs in a background thread. The ONLY cross-thread UI calls happen at
        # the very end (one call), so there's nothing to deadlock mid-run.
        _log.info("worker running translate()")
        try:
            result = self._service.translate(text, src, tgt, lambda e: None)
            _log.info("worker got result; pushing to UI")
            self.app.call_from_thread(self._show, result)
        except Exception as exc:
            _log.exception("worker failed: %s", exc)
            self.app.call_from_thread(self._fail, str(exc))

    def _show(self, result) -> None:
        out = (result.final_text or "").strip() or "(no output produced)"
        self.query_one("#output", Static).update(escape(out))
        line = f"[green]Done in {result.elapsed:.1f}s[/]"
        v = result.verdict
        if v is not None:
            verd = "PASS" if v.passed else "FAIL"
            colour = "green" if v.passed else "red"
            line += f"  [{colour}]·  QA {verd} {v.score:.0%}[/]"
        self.query_one("#status", Static).update(line)
        self.query_one("#source", TextArea).focus()

    def _fail(self, msg: str) -> None:
        self.query_one("#output", Static).update(
            f"[red]Error:[/] {escape(msg[:400])}"
        )
        self.query_one("#status", Static).update("[red]Error - see translation.log[/]")
