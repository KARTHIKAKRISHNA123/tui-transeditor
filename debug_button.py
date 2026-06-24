# debug_button.py
# Run this BEFORE the TUI to confirm the service itself works.
# If this crashes, the button was never the problem — it's the service.
# If this works, the problem is purely in the TUI event wiring.

import traceback
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

print("Step 1: importing TranslationService...")
try:
    from services.translation_service import TranslationService, PipelineEvent
    print("  OK")
except Exception as e:
    print(f"  FAILED: {e}")
    traceback.print_exc()
    exit(1)

print("Step 2: building service...")
try:
    svc = TranslationService(Path("."))
    print("  OK")
except Exception as e:
    print(f"  FAILED: {e}")
    traceback.print_exc()
    exit(1)

print("Step 3: calling translate()...")
try:
    def on_event(e: PipelineEvent):
        print(f"  EVENT: {e.type} | stage={e.stage} | {e.payload[:60]}")

    result = svc.translate(
        "Hello world",
        "English",
        "Tamil",
        on_event=on_event,
    )
    print(f"\nFINAL TEXT: {result.final_text}")
    print(f"VERDICT: passed={result.verdict.passed} score={result.verdict.score}")
except Exception as e:
    print(f"  FAILED: {e}")
    traceback.print_exc()
    exit(1)

print("\nAll steps passed. Service works. Button problem is TUI-only.")
