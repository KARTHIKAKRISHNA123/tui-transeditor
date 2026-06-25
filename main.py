# main.py — wire everything and launch. Composition root for the whole app.
import logging
import os

# ── LiteLLM: skip GitHub cost-map fetch (hangs on slow connections) ──────────
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

# ── LiteLLM transport: force the synchronous httpx client. ───────────────────
# litellm >=1.89 defaults to an aiohttp transport, which HANGS FOREVER when
# CrewAI's sync kickoff() runs inside our Textual @work(thread=True) worker on
# Windows (no usable event loop in the background thread → the request never
# returns, so the TUI gets stuck on "Already running"). httpx is sync-safe.
# Must be set BEFORE litellm/crewai are imported below.
os.environ.setdefault("DISABLE_AIOHTTP_TRANSPORT", "True")

# ── File logging: every crewai/litellm/agent log goes to translation.log ─────
# StreamHandler would corrupt the Textual TUI, so we write to a file only.
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(name)-40s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler("translation.log", mode="w", encoding="utf-8"),
    ],
    force=True,
)
# Quiet the very noisy httpx/httpcore traffic-level logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

from pathlib import Path

from dotenv import load_dotenv

from services.translation_service import TranslationService
from tui.app import TranslationApp


def main() -> None:
    load_dotenv()                        # OPENROUTER_API_KEY into the environment
    base_dir = Path(__file__).resolve().parent
    service = TranslationService(base_dir)   # build the seam once
    TranslationApp(service).run()            # hand it to the UI


if __name__ == "__main__":
    main()
