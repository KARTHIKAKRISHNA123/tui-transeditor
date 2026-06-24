# debug_tui.py
# Minimal TUI with just a button and a log.
# NO CrewAI, NO service, NO external calls.
# If clicking "Click Me" shows "BUTTON WORKS" in the log → TUI wiring is fine.
# If nothing happens → the button event is broken at the Textual level.

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Footer, Header, Label, RichLog, TextArea


class DebugApp(App):
    CSS = """
    Screen { background: #120a1e; color: #ede9fe; }
    #log { height: 10; border: solid #6d28d9; }
    Button { width: 1fr; margin: 1; background: #6d28d9; color: #ede9fe; }
    TextArea { height: 5; border: solid #6d28d9; margin: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Type something, then click the button or press Ctrl+J")
        yield TextArea(id="ta")
        yield Button("Click Me", id="btn", variant="primary")
        yield RichLog(id="log", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#ta", TextArea).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        log = self.query_one("#log", RichLog)
        log.write(f"[green]BUTTON WORKS — id={event.button.id}[/]")

    def on_key(self, event) -> None:
        if event.key == "ctrl+j":
            event.stop()
            log = self.query_one("#log", RichLog)
            text = self.query_one("#ta", TextArea).text
            log.write(f"[cyan]CTRL+J WORKS — text='{text[:40]}'[/]")


if __name__ == "__main__":
    DebugApp().run()
