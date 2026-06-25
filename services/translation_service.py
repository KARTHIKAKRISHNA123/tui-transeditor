# services/translation_service.py
# 3-stage pipeline: Translator → Reviewer → Corrector
from __future__ import annotations

import json
import logging
import re
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
        # Reused for the standalone QA scoring call (a plain LLM call, NOT a
        # crew agent — keeps it tool-free and reliably JSON-formatted).
        self._router = self._crew._agent_factory._router
        self._qa_system = self._crew._agent_factory._full_backstory("qa")
        self._pass_threshold = wf["pass_threshold"]

    def translate(
        self,
        source_text: str,
        source_lang: str,
        target_lang: str,
        on_event: EventSink,
    ) -> TranslationResult:
        started = time.perf_counter()
        result = TranslationResult(source=source_text)

        # Write to the FILE log first — synchronously, with no cross-thread
        # UI call — so we always have proof the worker reached translate(),
        # even if a later UI event hiccups.
        log.info("Pipeline starting: %s -> %s", source_lang, target_lang)

        def _log(msg: str) -> None:
            """Emit to both the TUI log panel and the file logger."""
            log.info(msg)
            on_event(PipelineEvent("log", payload=msg))

        on_event(PipelineEvent("started"))
        _log(f"Pipeline starting: {source_lang} → {target_lang}")

        # Protect placeholders
        protected, mapping = protect_placeholders(source_text)
        _log(f"Source text protected ({len(mapping)} placeholder(s))")

        # Task callback — fires after each stage completes
        counter = {"i": 0}

        def _task_done(task_output) -> None:
            idx = counter["i"]
            stage = _STAGES[idx] if idx < len(_STAGES) else f"stage{idx}"
            text = restore_placeholders(task_output.raw or "", mapping)
            result.stages[stage] = text
            _log(f"Stage '{stage}' output: {len(text)} chars")
            on_event(PipelineEvent("stage_completed", stage=stage, payload=text))
            if idx + 1 < len(_STAGES):
                on_event(PipelineEvent("stage_started", stage=_STAGES[idx + 1]))
            counter["i"] += 1

        _log("Building crew (loading LLMs)...")
        on_event(PipelineEvent("stage_started", stage="translator"))

        # Run the 3-stage crew
        try:
            _log("Calling crew.build()...")
            crew = self._crew.build(task_callback=_task_done)
            _log("crew.build() done — calling crew.kickoff()...")
            crew.kickoff(inputs={
                "source_text": protected,
                "source_lang": source_lang,
                "target_lang": target_lang,
            })
            _log("crew.kickoff() returned")
        except Exception as exc:
            log.exception("Pipeline error: %s", exc)
            _log(f"ERROR: {exc}")
            if not result.stages.get("corrector"):
                on_event(PipelineEvent("error", payload=str(exc)))
                raise

        # Final text = corrector output, fallback to translator
        final_raw = (result.stages.get("corrector")
                     or result.stages.get("translator") or "")
        result.final_text = restore_placeholders(final_raw, mapping)

        # Deterministic placeholder check (no model call).
        integrity = placeholder_integrity(mapping, result.final_text)

        # ── QA stage: structured, per-dimension scoring (one LLM call) ───────
        result.verdict = self._run_qa(
            source=source_text,
            final_text=result.final_text,
            source_lang=source_lang,
            target_lang=target_lang,
            integrity=integrity,
            log_fn=_log,
        )

        result.elapsed = time.perf_counter() - started
        _log(f"Pipeline done in {result.elapsed:.1f}s")
        on_event(PipelineEvent("finished",
                               payload=f"Done in {result.elapsed:.1f}s"))
        return result

    # ── QA scoring ───────────────────────────────────────────────────────────
    @staticmethod
    def _parse_json(raw: str) -> dict:
        """Extract a JSON object from a model reply (tolerates code fences /
        surrounding prose)."""
        if not raw:
            return {}
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return {}
        return json.loads(m.group(0))

    def _run_qa(self, source: str, final_text: str, source_lang: str,
                target_lang: str, integrity: dict, log_fn) -> QualityVerdict:
        """Score the final translation with the QA model and build a verdict.

        Returns a structured verdict (adequacy/fluency + per-dimension scores +
        issues). Never raises — a QA failure degrades to a soft verdict so the
        translation still reaches the user.
        """
        log_fn("Running QA scoring...")
        reasons: list[str] = []
        adequacy = fluency = 0.0
        terminology_ok = True
        verdict_str = "fail"

        try:
            prompt = (
                f"SOURCE ({source_lang}):\n{source}\n\n"
                f"FINAL TRANSLATION ({target_lang}):\n{final_text}\n\n"
                f"Score the translation. Return ONLY the JSON object."
            )
            raw = self._router.for_role("qa").call([
                {"role": "system", "content": self._qa_system},
                {"role": "user", "content": prompt},
            ])
            data = self._parse_json(raw)

            adequacy = float(data.get("adequacy", 0) or 0)
            fluency = float(data.get("fluency", 0) or 0)
            terminology_ok = bool(data.get("terminology_ok", True))
            verdict_str = str(data.get("verdict", "fail")).lower()

            reasons.append(f"Adequacy {adequacy:.2f}  ·  Fluency {fluency:.2f}")
            dims = data.get("dimensions") or {}
            if isinstance(dims, dict) and dims:
                reasons.append("  ·  ".join(
                    f"{k} {float(v):.2f}" for k, v in dims.items()
                    if isinstance(v, (int, float))
                ))
            if not terminology_ok:
                reasons.append("Terminology issues flagged")
            for issue in (data.get("issues") or [])[:8]:
                reasons.append(f"• {issue}")
        except Exception as exc:  # QA must never sink the whole run
            log.exception("QA scoring failed: %s", exc)
            log_fn(f"QA scoring failed: {exc}")
            reasons.append("QA scoring unavailable — translation returned as-is")
            # Soft pass: we still produced a translation.
            adequacy = fluency = 0.0
            verdict_str = "n/a"

        if not integrity["ok"]:
            reasons.insert(0, f"Missing placeholders: {integrity['missing']}")

        score = round((adequacy + fluency) / 2.0, 2)
        passed = (
            bool(final_text)
            and integrity["ok"]
            and (verdict_str == "pass"
                 or (verdict_str == "n/a"))  # QA unavailable → don't hard-fail
        )
        log_fn(f"QA verdict: {'PASS' if passed else 'FAIL'} (score {score:.2f})")
        return QualityVerdict(passed=passed, score=score, reasons=reasons)
