# smoke_test.py — run the translation pipeline WITHOUT the TUI.
# Purpose: isolate whether the problem is the model/pipeline or the TUI worker.
# Usage:   uv run python smoke_test.py
#
# It prints every step to the console and a full traceback on any error, so we
# can see exactly where (and whether) the Groq call works.
import os
import sys
import traceback

# Same transport fix the app uses (must be set before litellm import).
os.environ.setdefault("DISABLE_AIOHTTP_TRANSPORT", "True")

from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

print("=" * 60)
print("STEP 0: environment")
key = os.getenv("GROQ_API_KEY", "")
print(f"  GROQ_API_KEY present: {bool(key)}  (starts with {key[:6]!r})")
print(f"  DISABLE_AIOHTTP_TRANSPORT = {os.getenv('DISABLE_AIOHTTP_TRANSPORT')}")

try:
    print("STEP 1: import TranslationService")
    from services.translation_service import TranslationService, PipelineEvent

    print("STEP 2: build TranslationService (loads config + router)")
    svc = TranslationService(Path(__file__).resolve().parent)

    print("STEP 3: direct one-shot LiteLLM call (translator role only)")
    # Bypass CrewAI entirely — does the raw Groq call even work?
    llm = svc._crew._agent_factory._router.for_role("translator")
    out = llm.call("Translate 'hi how are you' into Tamil. Reply with only the Tamil.")
    print("  RAW LLM REPLY:", repr(out)[:300])

    print("STEP 4: full pipeline via translate()")

    def on_event(ev: PipelineEvent) -> None:
        print(f"    [event] {ev.type:16s} stage={ev.stage} payload={ev.payload[:80]!r}")

    result = svc.translate("hi how are you", "English", "Tamil", on_event=on_event)
    print("=" * 60)
    print("FINAL TEXT:", repr(result.final_text))
    if result.verdict:
        print(f"QA PASSED: {result.verdict.passed}   SCORE: {result.verdict.score}")
        for r in result.verdict.reasons:
            print("   -", r)
    print("ELAPSED:", round(result.elapsed, 1), "s")
    print("SUCCESS ✅")

except Exception as exc:
    print("=" * 60)
    print("FAILED ❌:", type(exc).__name__, exc)
    traceback.print_exc()
    sys.exit(1)
