# file.py
from pathlib import Path
from dotenv import load_dotenv
from llm.router import ModelRouter

load_dotenv()
router = ModelRouter(Path("config/models.yaml"))

roles = ["translator", "reviewer", "corrector", "qa"]
for role in roles:
    print(f"\n── Testing: {role} ──")
    try:
        result = router.call_with_fallback(role, "Reply with exactly: ok")
        print(f"  ✓  {result.strip()[:60]}")
    except Exception as e:
        print(f"  ✗  {str(e)[:100]}")