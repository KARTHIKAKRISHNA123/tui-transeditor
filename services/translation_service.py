# services/translation_service.py
# 3-stage pipeline: Translator → Reviewer → Corrector
# QA stage removed — was causing 400/429 on every free model.
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from orchestration.crew import TranslationCrew
from orchestration.tools import (placeholder_integrity, protect_placeholders,
                                 restore_placeholders)
from services.quality_service import QualityService, QualityVerdict

log = logging.getLogger(__name__)

_STAGES = ["translator", "reviewer", "corrector"]


@dataclass
class PipelineEvent:
    type: str
    stage: str | None = None
    payload: str = ""


@dataclass
class TranslationResult:
    source: str
    final_text: str = ""
    stages: dict[str, str] = field(default_factory=dict)
    verdict: QualityVerdict | None = None
    elapsed: float = 0.0


EventSink = Callable[[PipelineEvent], None]


class TranslationService:
    def __init__(self, base_dir: Path) -> None:
        self._crew = TranslationCrew(base_dir)
        wf = self._crew._wf["quality"]
        self._quality = QualityService(
            base_dir,
            enable_back_translation=wf["enable_back_translation"],
            pass_threshold=wf["pass_threshold"],
        )

    def translate(
        self,
        source_text: str,
        source_lang: str,
        target_lang: str,
        on_event: EventSink,
    ) -> TranslationResult:
        started = time.perf_counter()
        result = TranslationResult(source=source_text)
        on_event(PipelineEvent("started"))

        # Protect placeholders
        protected, mapping = protect_placeholders(source_text)

        # Task callback — fires after each stage completes
        counter = {"i": 0}

        def _task_done(task_output) -> None:
            idx = counter["i"]
            stage = _STAGES[idx] if idx < len(_STAGES) else f"stage{idx}"
            text = restore_placeholders(task_output.raw or "", mapping)
            result.stages[stage] = text
            on_event(PipelineEvent("stage_completed", stage=stage, payload=text))
            if idx + 1 < len(_STAGES):
                on_event(PipelineEvent("stage_started",
                                       stage=_STAGES[idx + 1]))
            counter["i"] += 1

        on_event(PipelineEvent("stage_started", stage="translator"))

        # Run the 3-stage crew
        try:
            crew = self._crew.build(task_callback=_task_done)
            crew.kickoff(inputs={
                "source_text": protected,
                "source_lang": source_lang,
                "target_lang": target_lang,
            })
        except Exception as exc:
            # If we have a corrector result, use it — otherwise surface error
            if not result.stages.get("corrector"):
                on_event(PipelineEvent("error", payload=str(exc)))
                raise

        # Final text = corrector output, fallback to translator
        final_raw = (result.stages.get("corrector")
                     or result.stages.get("translator") or "")
        result.final_text = restore_placeholders(final_raw, mapping)

        # Deterministic quality check (no model call)
        integrity = placeholder_integrity(mapping, result.final_text)
        result.verdict = QualityVerdict(
            passed=bool(result.final_text) and integrity["ok"],
            score=1.0 if integrity["ok"] else 0.5,
            reasons=[] if integrity["ok"]
                    else [f"Missing: {integrity['missing']}"],
        )

        result.elapsed = time.perf_counter() - started
        on_event(PipelineEvent("finished",
                               payload=f"Done in {result.elapsed:.1f}s"))
        return result
