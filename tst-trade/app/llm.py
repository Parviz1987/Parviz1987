"""One way to ask any brain for strict JSON: Anthropic (official SDK), OpenAI, xAI (OpenAI-compatible) and Gemini.

ask() returns (data, input_tokens, output_tokens) or raises LLMError. Prices are only for the monthly cap: Anthropic's
from its price table; unknown models are priced high on purpose so a cap is never overrun by a guess."""
from __future__ import annotations

import json

import httpx

TIMEOUT = 60.0
PRICES = {   # USD per 1M tokens (input, output)
    "claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50),
    "gemini-2.5-flash": (0.30, 2.50), "gemini-2.5-flash-lite": (0.10, 0.40),
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
    if not t.startswith("{") and "{" in t and "}" in t:
        t = t[t.find("{"): t.rfind("}") + 1]      # a model with search tools may write a line before the JSON
    try:
        data = json.loads(t)
    except ValueError as e:
        # a search model may add a sentence AFTER the object (2026-11-25: the hunter lost an answer this way):
        # read the first complete JSON object and ignore what follows it
        try:
            data, _ = json.JSONDecoder().raw_decode(t[t.find("{"):]) if "{" in t else (None, 0)
        except ValueError:
            data = None
        if data is None:
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


SEARCH_CALL_USD = 0.01      # counted per server-side search call, on top of tokens (kept high on purpose for the cap)


async def _responses_search(base: str, key: str, model: str, system: str, user: str, tools: list,
                            max_tokens: int) -> tuple[dict, int, int, int]:
    """OpenAI-style Responses API with server-side search tools (xAI and OpenAI share the shape)."""
    body = {"model": model, "input": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "tools": tools, "max_output_tokens": max_tokens}
    async with httpx.AsyncClient(timeout=180.0) as c:
        r = await c.post(f"{base}/v1/responses", headers={"Authorization": f"Bearer {key}"}, json=body)
    if r.status_code in (401, 403):
        raise LLMError("açar qəbul olunmadı")
    if r.status_code != 200:
        raise LLMError(f"HTTP {r.status_code}: {r.text[:160]}")
    j = r.json()
    texts, calls = [], 0
    if isinstance(j.get("output_text"), str):
        texts.append(j["output_text"])
    for item in j.get("output") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("type", "")).endswith("_call"):
            calls += 1
        if item.get("type") == "message" and not texts:
            for part in item.get("content") or []:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    texts.append(part["text"])
    if not texts:
        raise LLMError("boş cavab")
    u = j.get("usage") or {}
    return _json("\n".join(texts)), int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0), calls


async def _anthropic_search(key: str, model: str, system: str, user: str, max_tokens: int) -> tuple[dict, int, int, int]:
    """Claude with the server-side web search tool (official SDK). A long search can pause the turn
    (stop_reason pause_turn): the paused turn is sent back so the server continues, at most 3 times."""
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=key, timeout=180.0, max_retries=1)
    messages = [{"role": "user", "content": user}]
    tin = tout = calls = 0
    try:
        for _ in range(4):
            r = await client.messages.create(
                model=model, max_tokens=max_tokens, system=system, messages=messages,
                tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}],
                output_config={"effort": "low"})
            tin += r.usage.input_tokens
            tout += r.usage.output_tokens
            calls += sum(1 for b in r.content if b.type == "web_search_tool_result")
            if r.stop_reason != "pause_turn":
                break
            messages.append({"role": "assistant", "content": r.content})
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
    text = "".join(b.text for b in r.content if b.type == "text")
    return _json(text), tin, tout, calls


async def search(provider: str, key: str, model: str, system: str, user: str,
                 max_tokens: int = 3000) -> tuple[dict, int, int, int]:
    """Live search by the provider's own server-side tools. Returns (json answer, input tokens, output tokens,
    number of search calls). xAI: X and the web; OpenAI and Anthropic: the web. Gemini: not wired."""
    if provider == "xai":
        # Grok only for X (its unique strength); the web is searched by the cheaper brains (Rəqəm ovçusu)
        return await _responses_search("https://api.x.ai", key, model, system, user, [{"type": "x_search"}],
                                       max_tokens)
    if provider == "openai":
        return await _responses_search("https://api.openai.com", key, model, system, user,
                                       [{"type": "web_search"}], max_tokens)
    if provider == "anthropic":
        return await _anthropic_search(key, model, system, user, max_tokens)
    if provider == "gemini":
        return await _gemini_search(key, model, system, user, max_tokens)
    raise LLMError(f"{provider}: canlı axtarış bu provayderdə qoşulmayıb")


_GEMINI_SWAP: dict[str, str] = {}      # a retired model -> the model Google told us (or listed) to use instead


async def _gemini_current(key: str, model: str, text: str) -> str | None:
    """Google retires Gemini models for new keys (2026-11-26: «gemini-2.5-flash is no longer available»). The model it
    names in its error, or else the newest «flash» model this key may use for generateContent."""
    import re
    m = re.search(r"use (?:models/)?(gemini-[A-Za-z0-9.\-]+)", text or "")
    if m and m.group(1) != model:
        return m.group(1).rstrip(".")
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.get("https://generativelanguage.googleapis.com/v1beta/models", headers={"x-goog-api-key": key},
                        params={"pageSize": 200})
    if r.status_code != 200:
        return None
    names = [x["name"].split("/")[-1] for x in r.json().get("models", [])
             if "generateContent" in (x.get("supportedGenerationMethods") or [])]
    flash = [n for n in names if "flash" in n and not re.search(r"lite|image|tts|live|audio|preview|exp|thinking", n)]
    def ver(n):
        v = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
        return float(v.group(1)) if v else 0.0
    flash.sort(key=lambda n: (ver(n), n), reverse=True)
    return flash[0] if flash else None


async def _gemini_search(key, model, system, user, max_tokens):
    model = _GEMINI_SWAP.get(model, model)
    try:
        return await _gemini_search_once(key, model, system, user, max_tokens)
    except LLMError as e:
        if "HTTP 404" not in str(e):
            raise
        new = await _gemini_current(key, model, str(e))
        if not new or new == model:
            raise
        _GEMINI_SWAP[model] = new
        return await _gemini_search_once(key, new, system, user, max_tokens)


async def _gemini_search_once(key, model, system, user, max_tokens):
    """Gemini with Google Search grounding (owner 2026-11-26: use the idle Gemini key for the data agents). A grounded
    answer cannot be forced to JSON, so the JSON is read from the text; the number of Google queries is counted."""
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {"maxOutputTokens": max_tokens}}
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                         headers={"x-goog-api-key": key}, json=body)
    if r.status_code in (401, 403):
        raise LLMError("Gemini: açar qəbul olunmadı")
    if r.status_code != 200:
        raise LLMError(f"Gemini: HTTP {r.status_code}: {r.text[:400]}")
    j = r.json()
    try:
        cand = j["candidates"][0]
        text = "".join(p.get("text", "") for p in cand["content"]["parts"])
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError("Gemini: boş cavab") from e
    calls = len((cand.get("groundingMetadata") or {}).get("webSearchQueries") or [])
    u = j.get("usageMetadata") or {}
    return _json(text), int(u.get("promptTokenCount") or 0), int(u.get("candidatesTokenCount") or 0), calls
