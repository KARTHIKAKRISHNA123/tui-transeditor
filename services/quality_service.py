# services/quality_service.py
"""Authoritative quality gate: model judgment + deterministic checks."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from llm.router import ModelRouter
from orchestration.tasks import QAReport
from orchestration.tools import _detect


@dataclass
class QualityVerdict:
    passed: bool
    score: float
    reasons: list[str] = field(default_factory=list)
    back_translation: str | None = None


# Minimal name→ISO map for the hard language check. Lenient: unknown = skip.
_LANG_CODES = {"english": "en", "tamil": "ta", "hindi": "hi", "french": "fr",
               "spanish": "es", "german": "de"}


class QualityService:
    def __init__(self, base_dir: Path, enable_back_translation: bool,
                 pass_threshold: float) -> None:
        self._router = ModelRouter(base_dir / "config" / "models.yaml")
        self._back = enable_back_translation
        self._threshold = pass_threshold

    def evaluate(self, source: str, final_text: str, source_lang: str,
                 target_lang: str, qa: QAReport | None, integrity: dict,
                 on_event) -> QualityVerdict:
        reasons: list[str] = []

        # Hard check 1: placeholders intact (a dropped URL = automatic fail).
        if not integrity["ok"]:
            reasons.append(f"Missing placeholders: {integrity['missing']}")

        # Hard check 2: output really is in the target language.
        want = _LANG_CODES.get(target_lang.lower())
        if want and _detect(final_text) != want:
            reasons.append(f"Output language is not {target_lang}")

        # Model judgment from the QA agent.
        score = (qa.adequacy + qa.fluency) / 2 if qa else 0.0
        if qa and not qa.terminology_ok:
            reasons.append("Terminology violations reported by QA")
        if qa:
            reasons.extend(qa.issues)

        # Optional back-translation round-trip (1 extra model call).
        back = None
        if self._back:
            on_event and on_event(__import__("services.translation_service",
                fromlist=["PipelineEvent"]).PipelineEvent(
                "log", payload="Running back-translation check"))
            back = self._router.for_role("qa").call(
                f"Translate this {target_lang} text back into {source_lang}, "
                f"output only the translation:\n\n{final_text}")

        passed = score >= self._threshold and integrity["ok"] and not (
            qa and not qa.terminology_ok)
        return QualityVerdict(passed=passed, score=score, reasons=reasons,
                              back_translation=back)