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
    """A brain call failed. status: the HTTP status (None when no answer came); retry_after: seconds the provider asked
    to wait; hint: «timeout» (the request was sent, the answer did not come), «connect» (nothing was sent), «refusal»,
    «output» (an answer that is not the JSON we asked for); suggested: a model the provider named instead (404)."""

    def __init__(self, msg: str, status: int | None = None, retry_after: float | None = None, body: str = "",
                 hint: str | None = None, suggested: str | None = None):
        super().__init__(msg)
        self.status, self.retry_after, self.body = status, retry_after, (body or "")[:3000]
        self.hint, self.suggested = hint, suggested


def _retry_after(headers, text: str = "") -> float | None:
    """Seconds to wait, from the Retry-After header or Google's «retryDelay»: "36s" in the body."""
    import re
    try:
        v = (headers or {}).get("retry-after")
        if v is not None:
            return float(v)
    except (TypeError, ValueError):
        pass
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', text or "")
    return float(m.group(1)) if m else None


def _http_err(prefix: str, r) -> LLMError:
    text = str(getattr(r, "text", "") or "")
    if r.status_code in (401, 403):
        return LLMError(f"{prefix}açar qəbul olunmadı", r.status_code, None, text)
    return LLMError(f"{prefix}HTTP {r.status_code}: {text[:160]}", r.status_code,
                    _retry_after(getattr(r, "headers", None), text), text)


def _anthropic_err(e, model: str) -> LLMError:
    import anthropic
    if isinstance(e, anthropic.APITimeoutError):
        return LLMError("Anthropic: cavab vaxtında gəlmədi", None, hint="timeout")
    if isinstance(e, anthropic.APIConnectionError):
        # «connect» (nothing sent) only when the connection itself failed; a dropped answer may already be billed
        sent = not isinstance(getattr(e, "__cause__", None), (httpx.ConnectError, httpx.ConnectTimeout))
        return LLMError("Anthropic: bağlantı kəsildi" if sent else "Anthropic: qoşulmaq alınmadı", None,
                        hint="timeout" if sent else "connect")
    st = getattr(e, "status_code", None)
    resp = getattr(e, "response", None)
    ra = _retry_after(getattr(resp, "headers", None)) if resp is not None else None
    msg = {401: "Anthropic: açar qəbul olunmadı", 403: "Anthropic: açar qəbul olunmadı",
           404: f"Anthropic: model tapılmadı ({model})", 429: "Anthropic: sorğu limiti"}.get(st, f"Anthropic: HTTP {st}")
    return LLMError(msg, st, ra, str(e))


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
            raise LLMError(f"cavab JSON deyil: {t[:120]}", 200, hint="output") from e
    if not isinstance(data, dict):
        raise LLMError("cavab obyekt deyil", 200, hint="output")
    return data


async def _anthropic(key, model, system, user, schema, max_tokens):
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=key, timeout=TIMEOUT, max_retries=0)   # one retry layer: the router
    try:
        r = await client.messages.create(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}})
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        raise _anthropic_err(e, model) from e
    finally:
        await client.close()
    if r.stop_reason == "refusal":
        raise LLMError("Anthropic: model cavab verməkdən imtina etdi", 200, hint="refusal")
    text = next((b.text for b in r.content if b.type == "text"), "")
    return _json(text), r.usage.input_tokens, r.usage.output_tokens


async def _openai_like(base, key, model, system, user, schema, max_tokens, token_field):
    body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "answer", "schema": schema, "strict": True}},
            token_field: max_tokens}
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(f"{base}/v1/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=body)
    if r.status_code != 200:
        raise _http_err("", r)
    j = r.json()
    msg = (j.get("choices") or [{}])[0].get("message") or {}
    if msg.get("refusal"):
        raise LLMError("model cavab verməkdən imtina etdi", 200, hint="refusal")
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
    if r.status_code != 200:
        raise _http_err("Gemini: ", r)
    j = r.json()
    try:
        text = j["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError("Gemini: boş cavab", 200, hint="output") from e
    u = j.get("usageMetadata") or {}     # thinking tokens are billed as output
    return (_json(text), int(u.get("promptTokenCount") or 0),
            int(u.get("candidatesTokenCount") or 0) + int(u.get("thoughtsTokenCount") or 0))


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
    raise LLMError(f"naməlum provayder: {provider}", hint="config")


SEARCH_CALL_USD = 0.01      # counted per server-side search call, on top of tokens (kept high on purpose for the cap)


async def _responses_search(base: str, key: str, model: str, system: str, user: str, tools: list,
                            max_tokens: int) -> tuple[dict, int, int, int]:
    """OpenAI-style Responses API with server-side search tools (xAI and OpenAI share the shape)."""
    body = {"model": model, "input": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "tools": tools, "max_output_tokens": max_tokens, "max_tool_calls": 5}
    async with httpx.AsyncClient(timeout=180.0) as c:
        r = await c.post(f"{base}/v1/responses", headers={"Authorization": f"Bearer {key}"}, json=body)
    if r.status_code != 200:
        raise _http_err("", r)
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
        raise LLMError("boş cavab", 200, hint="output")
    u = j.get("usage") or {}
    return _json("\n".join(texts)), int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0), calls


async def _anthropic_search(key: str, model: str, system: str, user: str, max_tokens: int) -> tuple[dict, int, int, int]:
    """Claude with the server-side web search tool (official SDK). A long search can pause the turn
    (stop_reason pause_turn): the paused turn is sent back so the server continues, at most 3 times."""
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=key, timeout=180.0, max_retries=0)   # one retry layer: the router
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
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        err = _anthropic_err(e, model)
        err.partial = (tin, tout, calls)             # earlier rounds were paid
        raise err from e
    finally:
        await client.close()
    if r.stop_reason == "refusal":
        raise LLMError("Anthropic: model cavab verməkdən imtina etdi", 200, hint="refusal")
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
    raise LLMError(f"{provider}: canlı axtarış bu provayderdə qoşulmayıb", hint="config")


# owner 2026-11-26 (plan step 7): a retired model is never swapped automatically any more. The model Google names (or
# lists) is attached to the 404 as a proposal; the router disables the old model, the spare brain works meanwhile, and
# the owner approves or rejects the proposal in Admin (or the pre-approval rule decides after a trial).


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
    try:
        return await _gemini_search_once(key, model, system, user, max_tokens)
    except LLMError as e:
        if e.status == 404:
            try:
                e.suggested = await _gemini_current(key, model, e.body)
            except Exception:           # finding a proposal never hides the original error
                pass
        raise


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
    if r.status_code != 200:
        raise _http_err("Gemini: ", r)
    j = r.json()
    try:
        cand = j["candidates"][0]
        text = "".join(p.get("text", "") for p in cand["content"]["parts"])
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError("Gemini: boş cavab", 200, hint="output") from e
    calls = len((cand.get("groundingMetadata") or {}).get("webSearchQueries") or [])
    u = j.get("usageMetadata") or {}     # thinking tokens are billed as output
    return (_json(text), int(u.get("promptTokenCount") or 0),
            int(u.get("candidatesTokenCount") or 0) + int(u.get("thoughtsTokenCount") or 0), calls)
