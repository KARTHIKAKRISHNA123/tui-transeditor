# orchestration/tools.py
"""Translation capabilities, placed where each is reliable.

Two kinds of thing live here:
  1. AGENT TOOLS  (@tool)  — the LLM decides when to call them mid-reasoning.
  2. PIPELINE FUNCTIONS    — deterministic guards the SERVICE layer always runs.

Why the split? An LLM "usually" calling a placeholder-protection tool is NOT a
guarantee. For format-safety we want a GUARANTEE, so that logic is plain code
that always executes in the service layer — never left to the model's discretion.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from crewai.tools import tool
from langdetect import LangDetectException, detect

# ───────────────────────── AGENT TOOL 1: glossary ─────────────────────────

_GLOSSARY_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "glossary.json"
)


def _load_glossary() -> dict[str, str]:
    """Load the termbase once at import time. Missing file → empty glossary."""
    if not _GLOSSARY_PATH.exists():
        return {}
    return json.loads(_GLOSSARY_PATH.read_text(encoding="utf-8"))


_GLOSSARY: dict[str, str] = _load_glossary()


@tool("Glossary Lookup")
def glossary_tool(source_text: str) -> str:
    """Find approved terminology present in source_text.

    Returns every glossary term found and the REQUIRED target rendering.
    Call this before translating so terminology stays consistent.
    """
    hits = {
        term: tgt
        for term, tgt in _GLOSSARY.items()
        if term.lower() in source_text.lower()
    }
    if not hits:
        return "No glossary terms found in this text."
    lines = [
        f'- "{term}" MUST be translated as "{tgt}"' for term, tgt in hits.items()
    ]
    return "Required terminology:\n" + "\n".join(lines)


# ──────────────────────── AGENT TOOL 2: language ─────────────────────────


def _detect(text: str) -> str:
    """Best-effort ISO-639-1 language code, or 'unknown'.

    Shared by the @tool below AND by quality_service directly.
    Keeping it as a plain function means quality_service can import it
    without importing the @tool decorator machinery.
    """
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"


@tool("Detect Language")
def language_tool(text: str) -> str:
    """Detect the language of a text snippet.

    Use this after translating to confirm the output is actually in
    the target language and not accidentally still in the source language.
    """
    return f"Detected language code: {_detect(text)}"


# ─────────── PIPELINE GUARDS (deterministic — called by services, not agents) ──────────

# Regex: things that must NEVER be translated.
# Order matters — longer/more-specific patterns first.
_NON_TRANSLATABLE = re.compile(
    r"(`[^`]+`"              # `inline code`
    r"|\{[^}]+\}"            # {curly_placeholders}
    r"|%[sd]"                # %s %d printf-style
    r"|https?://\S+"         # URLs
    r"|[\w.+-]+@[\w-]+\.[\w.-]+"  # emails
    r"|</?[a-zA-Z][^>]*>)"  # <html/xml tags>
)

# A visually distinct sentinel the model will never accidentally "translate".
# ⟦0⟧, ⟦1⟧, … are exotic enough that no LLM confuses them for real content.
_SENTINEL = "⟦{}⟧"


def protect_placeholders(text: str) -> tuple[str, dict[str, str]]:
    """Replace every non-translatable span with a numbered sentinel.

    Returns (protected_text, mapping).

    The model receives protected_text. Sentinels pass through untouched.
    After the crew finishes, call restore_placeholders(output, mapping)
    to swap sentinels back to the originals.
    """
    mapping: dict[str, str] = {}
    counter = 0

    def _swap(match: re.Match) -> str:
        nonlocal counter
        token = _SENTINEL.format(counter)
        mapping[token] = match.group(0)
        counter += 1
        return token

    protected = _NON_TRANSLATABLE.sub(_swap, text)
    return protected, mapping


def restore_placeholders(text: str, mapping: dict[str, str]) -> str:
    """Swap every sentinel back to its original literal."""
    for token, original in mapping.items():
        text = text.replace(token, original)
    return text


def placeholder_integrity(mapping: dict[str, str], output_text: str) -> dict:
    """Check that every sentinel survived translation.

    A dropped ⟦3⟧ means a URL or format-string was corrupted.
    We detect this deterministically — no LLM judgement needed.

    Returns {"ok": bool, "missing": list[str], "expected": int}
    """
    missing = [tok for tok in mapping if tok not in output_text]
    return {"ok": not missing, "missing": missing, "expected": len(mapping)}
