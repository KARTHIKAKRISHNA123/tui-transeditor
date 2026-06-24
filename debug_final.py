# debug_final.py
# Runs the FULL pipeline headless (no TUI at all).
# Shows every event and the final result.
# This is the ground truth — if this works, the problem is 100% in the TUI.

import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from services.translation_service import TranslationService, PipelineEvent

svc = TranslationService(Path("."))

print("=== RUNNING PIPELINE ===")
print("Input: 'AI is ruling the world'  English → Tamil")
print()

events = []

def on_event(e: PipelineEvent):
    events.append(e)
    print(f"  [{e.type}] stage={e.stage} | {e.payload[:80]}")

try:
    result = svc.translate("AI is ruling the world", "English", "Tamil", on_event)
    print()
    print("=== RESULT ===")
    print(f"final_text : {result.final_text}")
    print(f"stages     : {list(result.stages.keys())}")
    print(f"verdict    : passed={result.verdict.passed} score={result.verdict.score:.2f}")
    print(f"elapsed    : {result.elapsed:.1f}s")
except Exception as e:
    print(f"\n=== EXCEPTION ===")
    print(f"{type(e).__name__}: {e}")
    import traceback; traceback.print_exc()
