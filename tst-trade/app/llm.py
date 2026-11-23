"""One way to ask any brain for strict JSON: Anthropic (official SDK), OpenAI, xAI (OpenAI-compatible) and Gemini.

ask() returns (data, input_tokens, output_tokens) or raises LLMError. Prices are only for the monthly cap: Anthropic's
from its price table; unknown models are priced high on purpose so a cap is never overrun by a guess."""
from __future__ import annotations

import json

import httpx

TIMEOUT = 60.0
PRICES = {   # USD per 1M tokens (input, output)
    "claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50),
}
UNKNOWN_PRICE = (5.0, 25.0)


class LLMError(Exception):
    pass


def cost(model: str, tin: int, tout: int) -> float:
    pin, pout = PRICES.get(model, UNKNOWN_PRICE)
    return (tin * pin + tout * pout) / 1e6


def _json(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{"):]
    try:
        data = json.loads(t)
    except ValueError as e:
        raise LLMError(f"cavab JSON deyil: {t[:120]}") from e
    if not isinstance(data, dict):
        raise LLMError("cavab obyekt deyil")
    return data


async def _anthropic(key, model, system, user, schema, max_tokens):
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=key, timeout=TIMEOUT, max_retries=1)
    try:
        r = await client.messages.create(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}})
    except anthropic.AuthenticationError as e:
        raise LLMError("Anthropic: açar qəbul olunmadı") from e
    except anthropic.NotFoundError as e:
        raise LLMError(f"Anthropic: model tapılmadı ({model})") from e
    except anthropic.RateLimitError as e:
        raise LLMError("Anthropic: sorğu limiti") from e
    except anthropic.APIConnectionError as e:
        raise LLMError("Anthropic: qoşulmaq alınmadı") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"Anthropic: HTTP {e.status_code}") from e
    finally:
        await client.close()
    if r.stop_reason == "refusal":
        raise LLMError("Anthropic: model cavab verməkdən imtina etdi")
    text = next((b.text for b in r.content if b.type == "text"), "")
    return _json(text), r.usage.input_tokens, r.usage.output_tokens


async def _openai_like(base, key, model, system, user, schema, max_tokens, token_field):
    body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "answer", "schema": schema, "strict": True}},
            token_field: max_tokens}
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(f"{base}/v1/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=body)
    if r.status_code in (401, 403):
        raise LLMError("açar qəbul olunmadı")
    if r.status_code != 200:
        raise LLMError(f"HTTP {r.status_code}: {r.text[:160]}")
    j = r.json()
    msg = (j.get("choices") or [{}])[0].get("message") or {}
    if msg.get("refusal"):
        raise LLMError("model cavab verməkdən imtina etdi")
    u = j.get("usage") or {}
    return _json(msg.get("content") or ""), int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)


async def _gemini(key, model, system, user, schema, max_tokens):
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": schema,
                                 "maxOutputTokens": max_tokens}}
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                         headers={"x-goog-api-key": key}, json=body)
    if r.status_code in (401, 403):
        raise LLMError("Gemini: açar qəbul olunmadı")
    if r.status_code != 200:
        raise LLMError(f"Gemini: HTTP {r.status_code}: {r.text[:160]}")
    j = r.json()
    try:
        text = j["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError("Gemini: boş cavab") from e
    u = j.get("usageMetadata") or {}
    return _json(text), int(u.get("promptTokenCount") or 0), int(u.get("candidatesTokenCount") or 0)


async def ask(provider: str, key: str, model: str, system: str, user: str, schema: dict,
              max_tokens: int = 2000) -> tuple[dict, int, int]:
    if provider == "anthropic":
        return await _anthropic(key, model, system, user, schema, max_tokens)
    if provider == "openai":
        return await _openai_like("https://api.openai.com", key, model, system, user, schema, max_tokens,
                                  "max_completion_tokens")
    if provider == "xai":
        return await _openai_like("https://api.x.ai", key, model, system, user, schema, max_tokens, "max_tokens")
    if provider == "gemini":
        return await _gemini(key, model, system, user, schema, max_tokens)
    raise LLMError(f"naməlum provayder: {provider}")
