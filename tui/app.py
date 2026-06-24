# tui/app.py — no emojis in TITLE or SUB_TITLE
from pathlib import Path

from textual.app import App

from services.translation_service import TranslationService
from tui.screens.translate_screen import TranslateScreen


class TranslationApp(App):
    CSS_PATH = Path(__file__).parent / "styles" / "app.tcss"

    TITLE     = "AI Translation Pipeline"
    SUB_TITLE = "Translator > Reviewer > Corrector > QA"

    BINDINGS = [
        ("q",      "quit",      "Quit"),
        ("ctrl+c", "quit",      "Quit"),
        ("ctrl+l", "clear_log", "Clear logs"),
    ]

    def __init__(self, service: TranslationService) -> None:
        super().__init__()
        self._service = service

    def on_mount(self) -> None:
        self.push_screen(TranslateScreen(self._service))

    def action_clear_log(self) -> None:
        from tui.widgets.log_panel import LogPanel
        try:
            self.query_one(LogPanel).clear()
        except Exception:
            pass
