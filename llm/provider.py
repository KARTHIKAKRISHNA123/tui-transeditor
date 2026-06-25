# llm/provider.py
"""LLM factory: turns a declarative ModelSpec into a live crewai.LLM.

This module is the ONLY place in the codebase that constructs an LLM
client. That centralization is deliberate — the LiteLLM credential wiring
is fiddly, and we want exactly one place to get it right.

It is provider-agnostic: any provider LiteLLM supports (Groq, OpenRouter,
Together, Fireworks, OpenAI, …) works by setting `provider` + `model` in
models.yaml. LiteLLM routes by the model-slug prefix (e.g. `groq/...`,
`openrouter/...`), and each provider just needs its own API-key env var.
"""
from __future__ import annotations  # lets us write `int | None` on older Pythons

import os
from dataclasses import dataclass

import litellm
from crewai import LLM


def _install_cache_breakpoint_stripper() -> None:
    """Remove CrewAI's `cache_breakpoint` message field before every request.

    CrewAI tags system/user messages with `{"cache_breakpoint": True}` to enable
    Anthropic/OpenRouter prompt caching. Groq — and most other providers — reject
    that unknown field with:
        BadRequestError: 'messages.0' : property 'cache_breakpoint' is unsupported
    OpenRouter happened to tolerate it; Groq does not. We strip it from every
    outgoing `litellm.completion` call so ANY provider accepts the payload.

    Idempotent: safe to call more than once.
    """
    if getattr(litellm, "_cache_breakpoint_stripped", False):
        return

    _orig_completion = litellm.completion

    def _strip(messages) -> None:
        if not messages:
            return
        for m in messages:
            if isinstance(m, dict):
                m.pop("cache_breakpoint", None)

    def _patched_completion(*args, **kwargs):
        # CrewAI calls litellm.completion(**params), so messages is a kwarg;
        # cover the positional case too just in case.
        _strip(kwargs.get("messages"))
        if len(args) >= 2:
            _strip(args[1])
        return _orig_completion(*args, **kwargs)

    litellm.completion = _patched_completion
    litellm._cache_breakpoint_stripped = True


# Install the shim as soon as this module (the LLM factory) is imported, so it
# is active for every entry point — the TUI app and the smoke test alike.
_install_cache_breakpoint_stripper()


# Which environment variable holds the API key for each provider.
# LiteLLM itself also reads most of these, but we pass the key explicitly so
# we can fail fast with a clear message instead of a cryptic 401 deep in an
# agent loop.
_PROVIDER_KEY_ENV = {
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "together": "TOGETHER_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
}


@dataclass(frozen=True)
class ModelSpec:
    """An immutable description of one model configuration.

    `frozen=True` makes instances read-only: once built, a spec can't be
    mutated. That prevents a whole class of bugs where some far-away code
    quietly changes a temperature mid-run. Config should be inert data.
    """
    model: str
    provider: str = "groq"
    temperature: float = 0.3
    timeout: int = 60
    max_tokens: int = 2000
    num_retries: int = 5          # retries on 429/5xx; LiteLLM backs off
    base_url: str | None = None   # only needed for providers like OpenRouter
    api_key_env: str | None = None  # override the default key env var


class LLMProvider:
    """Builds configured `crewai.LLM` instances from a `ModelSpec`."""

    def build(self, spec: ModelSpec) -> LLM:
        """Construct one LLM client for the spec's provider."""
        # Resolve which env var holds this provider's key.
        key_env = spec.api_key_env or _PROVIDER_KEY_ENV.get(spec.provider)
        if not key_env:
            raise RuntimeError(
                f"Unknown provider '{spec.provider}'. Add its API-key env var "
                f"to _PROVIDER_KEY_ENV in llm/provider.py, or set api_key_env "
                f"in models.yaml."
            )

        # Fail FAST and LOUD. If the key is missing, we want a clear error
        # here -- not a cryptic 401 surfacing three layers deep inside an
        # agent's reasoning loop, where it's miserable to debug.
        api_key = os.getenv(key_env)
        if not api_key:
            raise RuntimeError(
                f"{key_env} is not set. Add it to your .env file before "
                f"running (provider '{spec.provider}', model '{spec.model}')."
            )

        kwargs = dict(
            model=spec.model,
            api_key=api_key,
            temperature=spec.temperature,
            timeout=spec.timeout,
            max_tokens=spec.max_tokens,
            is_litellm=True,  # bypass native provider; use LiteLLM routing
            # Unknown kwargs are forwarded straight into litellm.completion().
            # Free tiers throttle (HTTP 429); LiteLLM retries on 429/5xx with
            # backoff so a transient limit doesn't kill the whole run.
            num_retries=spec.num_retries,
        )
        # Only providers behind a custom gateway (OpenRouter) need a base_url.
        # Groq/OpenAI/etc. are built into LiteLLM and must NOT get one.
        if spec.base_url:
            kwargs["base_url"] = spec.base_url
            kwargs["api_base"] = spec.base_url

        return LLM(**kwargs)
