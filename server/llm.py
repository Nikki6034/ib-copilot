"""Server-side LLM client for IB Copilot.

All model calls go through `chat()`. It uses the course model (gpt-6-luna) via the
Portkey gateway by default, captures the API's own token usage (including cached tokens
when the API reports them — never invented), applies a timeout and bounded retries, and
returns a structured result. Secrets stay on the server.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from openai import OpenAI

from . import config

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is not None:
        return _client
    if config.USE_DIRECT_OPENAI:
        if not config.OPENAI_API_KEY:
            raise RuntimeError("USE_DIRECT_OPENAI=1 but OPENAI_API_KEY is not set.")
        _client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=config.REQUEST_TIMEOUT_S)
    else:
        if not config.PORTKEY_API_KEY:
            raise RuntimeError(
                "PORTKEY_API_KEY is not set. Put it in .env (project root or one dir above)."
            )
        _client = OpenAI(
            api_key=config.PORTKEY_API_KEY,
            base_url=config.PORTKEY_BASE_URL,
            default_headers={
                "x-portkey-api-key": config.PORTKEY_API_KEY,
                "x-portkey-provider": config.PORTKEY_PROVIDER,
            },
            timeout=config.REQUEST_TIMEOUT_S,
        )
    return _client


@dataclass
class LLMResult:
    text: str
    model: str
    input_tokens: int | None = None
    cached_tokens: int | None = None          # None => the API did not report it
    output_tokens: int | None = None
    total_tokens: int | None = None
    latency_s: float = 0.0
    calls: int = 1
    cost_usd: float | None = None
    error: str | None = None
    meta: dict = field(default_factory=dict)


def estimate_cost(model: str, input_tokens, cached_tokens, output_tokens) -> float | None:
    """USD estimate from configured pricing applied to real token counts. Cached tokens
    (if reported) are billed at the cached rate and excluded from fresh input."""
    if input_tokens is None and output_tokens is None:
        return None
    p = config.price_for(model)
    cached = cached_tokens or 0
    fresh_in = max((input_tokens or 0) - cached, 0)
    return round(
        fresh_in / 1e6 * p["input_per_1m"]
        + cached / 1e6 * p["cached_input_per_1m"]
        + (output_tokens or 0) / 1e6 * p["output_per_1m"],
        6,
    )


def _extract_usage(resp) -> dict:
    u = getattr(resp, "usage", None)
    if u is None:
        return {"input_tokens": None, "cached_tokens": None, "output_tokens": None, "total_tokens": None}
    cached = None
    details = getattr(u, "prompt_tokens_details", None)
    if details is not None:
        cached = getattr(details, "cached_tokens", None)
    return {
        "input_tokens": getattr(u, "prompt_tokens", None),
        "cached_tokens": cached,                       # None if the API omits it
        "output_tokens": getattr(u, "completion_tokens", None),
        "total_tokens": getattr(u, "total_tokens", None),
    }


def chat(messages: list[dict], max_tokens: int | None = None, model: str | None = None) -> LLMResult:
    """One chat completion with usage capture, timeout and bounded retries.

    Returns an LLMResult; on failure after retries, returns a result with `error` set and
    empty text (callers degrade gracefully rather than crash)."""
    model = model or config.MODEL
    max_tokens = max_tokens or config.MAX_OUTPUT_TOKENS
    client = get_client()
    started = time.time()
    last_err = None
    for attempt in range(config.MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_completion_tokens=max_tokens,   # Azure-backed: max_tokens is rejected
            )
            text = (resp.choices[0].message.content or "").strip()
            usage = _extract_usage(resp)
            cost = estimate_cost(model, usage["input_tokens"], usage["cached_tokens"], usage["output_tokens"])
            return LLMResult(
                text=text, model=model, latency_s=round(time.time() - started, 3),
                cost_usd=cost, calls=attempt + 1, **usage,
            )
        except Exception as e:  # noqa: BLE001 - bounded retry on any transient failure
            last_err = e
            if attempt < config.MAX_RETRIES:
                time.sleep(0.6 * (attempt + 1))
                continue
    return LLMResult(
        text="", model=model, latency_s=round(time.time() - started, 3),
        calls=config.MAX_RETRIES + 1, error=f"{type(last_err).__name__}: {str(last_err)[:300]}",
    )
