# debug_tui_minimal.py
# Strips away ALL service/crew code.
# Just a button and a log. Run this and click the button.
# Tell me exactly what you see.

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Label, RichLog, TextArea


class MinimalApp(App):
    CSS = """
    Screen    { background: #120a1e; color: #ede9fe; layout: vertical; }
    TextArea  { height: 6; border: solid #6d28d9; margin: 1; }
    Button    { width: 1fr; margin: 1; }
    RichLog   { height: 10; border: solid #6d28d9; margin: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Label("Type text below, then click Translate")
        yield TextArea(id="ta")
        yield Button("Translate", id="run-btn", variant="primary")
        yield RichLog(id="log", markup=True)

    def on_mount(self) -> None:
        self.query_one("#ta", TextArea).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        log = self.query_one("#log", RichLog)
        text = self.query_one("#ta", TextArea).text.strip()
        log.write(f"[green]BUTTON FIRED — id={event.button.id} text='{text[:30]}'[/]")

    def on_key(self, event) -> None:
        if event.key == "ctrl+j":
            event.stop()
            log = self.query_one("#log", RichLog)
            log.write("[cyan]CTRL+J FIRED[/]")


if __name__ == "__main__":
    MinimalApp().run()
