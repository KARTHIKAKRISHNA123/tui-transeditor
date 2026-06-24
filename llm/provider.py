# llm/provider.py
"""LLM factory: turns a declarative ModelSpec into a live crewai.LLM.

This module is the ONLY place in the codebase that constructs an LLM
client. That centralization is deliberate — the OpenRouter/LiteLLM
credential wiring is fiddly, and we want exactly one place to get it right.
"""
from __future__ import annotations  # lets us write `int | None` on older Pythons

import os
from dataclasses import dataclass

from crewai import LLM


@dataclass(frozen=True)
class ModelSpec:
    """An immutable description of one model configuration.

    `frozen=True` makes instances read-only: once built, a spec can't be
    mutated. That prevents a whole class of bugs where some far-away code
    quietly changes a temperature mid-run. Config should be inert data.
    """
    model: str
    base_url: str
    temperature: float
    timeout: int
    max_tokens: int


class LLMProvider:
    """Builds configured `crewai.LLM` instances from a `ModelSpec`."""

    def build(self, spec: ModelSpec) -> LLM:
        """Construct one LLM client, with the OpenRouter wiring done right."""
        # Fail FAST and LOUD. If the key is missing, we want a clear error
        # here — not a cryptic 401 surfacing three layers deep inside an
        # agent's reasoning loop, where it's miserable to debug.
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Copy .env.example to .env "
                "and add your OpenRouter key before running."
            )

        return LLM(
            model=spec.model,
            base_url=spec.base_url,
            api_base=spec.base_url,   # ← THE FOOTGUN FIX. LiteLLM reads
                                      #   `api_base`, but CrewAI's LLM stores
                                      #   `base_url`. Passing BOTH guarantees
                                      #   the endpoint actually reaches LiteLLM.
            api_key=api_key,          # belt-and-suspenders with the env var
            temperature=spec.temperature,
            timeout=spec.timeout,
            max_tokens=spec.max_tokens,
        )