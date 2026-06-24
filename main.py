# main.py — wire everything and launch. Composition root for the whole app.
from pathlib import Path

from dotenv import load_dotenv

from services.translation_service import TranslationService
from tui.app import TranslationApp


def main() -> None:
    load_dotenv()                       # OPENROUTER_API_KEY into the environment
    base_dir = Path(__file__).resolve().parent
    service = TranslationService(base_dir)   # build the seam once
    TranslationApp(service).run()            # hand it to the UI


if __name__ == "__main__":
    main()