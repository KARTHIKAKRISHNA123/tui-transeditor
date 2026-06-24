# llm/router.py
"""Role → LLM resolver with automatic fallback.

Public interface: router.call_with_fallback(role, prompt) → str
                  router.for_role(role) → LLM   (for crew.kickoff)

On 404 (slug removed from free tier) or exhausted 429 retries,
automatically switches to the 'fallback' role in models.yaml so the
pipeline never crashes just because a free slug rotated out.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import yaml
from crewai import LLM

from llm.provider import LLMProvider, ModelSpec

logger = logging.getLogger(__name__)


class ModelRouter:
    # Seconds to wait between 429 retries (just above OpenRouter's stated 29s)
    _RETRY_WAIT = 35
    # How many times to retry before falling back to the fallback role
    _MAX_RETRIES = 2

    def __init__(
        self,
        config_path: Path,
        provider: LLMProvider | None = None,
    ) -> None:
        # DEPENDENCY INJECTION — in tests, pass a FakeLLMProvider that never
        # hits the network. The router's routing logic stays testable.
        self._provider = provider or LLMProvider()
        self._roles = self._load(config_path)
        self._cache: dict[str, LLM] = {}

    @staticmethod
    def _load(path: Path) -> dict:
        # safe_load can't execute code embedded in YAML — always use it.
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return raw["roles"]

    def _build(self, role: str) -> LLM:
        """Build one LLM from config. KeyError if role is missing."""
        if role not in self._roles:
            raise KeyError(
                f"No model configured for role '{role}'. "
                f"Known roles: {list(self._roles)}"
            )
        cfg = self._roles[role]
        spec = ModelSpec(
            model=cfg["model"],
            base_url=cfg["base_url"],
            temperature=cfg["temperature"],
            timeout=cfg["timeout"],
            max_tokens=cfg["max_tokens"],
        )
        return self._provider.build(spec)

    def for_role(self, role: str) -> LLM:
        """Return the cached LLM for role, building it on first call.

        Used by AgentFactory so each agent gets its assigned model.
        Does NOT do fallback — the crew's own retry loop handles transient
        errors during kickoff(). Fallback is only for direct .call() usage.
        """
        if role not in self._cache:
            self._cache[role] = self._build(role)
        return self._cache[role]

    def call_with_fallback(self, role: str, prompt: str) -> str:
        """Call the LLM for role with automatic retry + model fallback.

        Flow:
          1. Try primary model up to _MAX_RETRIES times on 429.
          2. On 404 (slug gone) or exhausted retries → try 'fallback' role.
          3. Both fail → raise with clear instructions.

        Use this for smoke tests (file.py) and service-layer direct calls.
        Do NOT wrap crew.kickoff() with this — CrewAI has its own retry loop.
        """
        llm = self.for_role(role)
        last_exc: Exception | None = None

        # ── Primary: retry loop on 429 ────────────────────────────────────
        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                return llm.call(prompt)

            except Exception as exc:
                err = str(exc)

                if "404" in err:
                    # Slug removed from free tier — retrying is pointless.
                    logger.warning(
                        "Role '%s' got 404 (model slug removed from free tier). "
                        "Switching to fallback immediately.", role
                    )
                    last_exc = exc
                    break  # jump to fallback

                if "429" in err:
                    logger.warning(
                        "Role '%s' rate-limited (attempt %d/%d). Waiting %ds…",
                        role, attempt, self._MAX_RETRIES, self._RETRY_WAIT,
                    )
                    last_exc = exc
                    if attempt < self._MAX_RETRIES:
                        time.sleep(self._RETRY_WAIT)
                    continue  # retry same model

                raise  # any other error → fail fast, don't mask it

        # ── Fallback model ────────────────────────────────────────────────
        if "fallback" not in self._roles:
            raise RuntimeError(
                f"Primary model for role '{role}' failed and no 'fallback' "
                f"role is defined in models.yaml.\nLast error: {last_exc}"
            ) from last_exc

        logger.warning(
            "Falling back to 'fallback' role. Primary error: %s",
            str(last_exc)[:120],
        )
        # Remap this role's cache entry to the fallback model so that
        # subsequent for_role(role) calls inside crew.kickoff() also use it.
        self._cache[role] = self._build("fallback")

        try:
            return self._cache[role].call(prompt)
        except Exception as exc:
            raise RuntimeError(
                f"Both primary (role='{role}') and fallback models failed.\n"
                f"Primary: {last_exc}\nFallback: {exc}\n\n"
                "Wait a few minutes and retry, or check openrouter.ai/status."
            ) from exc
