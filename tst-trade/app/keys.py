"""Key places: save, read, mask, delete, and check that a key works. Keys are sealed with SESSION_SECRET in SQLite;
a key never goes back to the browser, only its last four characters."""
from __future__ import annotations

import json
import time

import httpx

from . import registry
from .db import DB
from .seal import mask, seal, unseal

CHECK_TIMEOUT = 15.0


class KeyStore:
    def __init__(self, db: DB, secret: str):
        self.db = db
        self.secret = secret

    def set(self, slot: str, values: dict[str, str]) -> None:
        if slot not in registry.KEY_IDS:
            raise ValueError("naməlum açar yeri")
        fields = registry.FIELDS[slot]
        clean = {f: str(values.get(f, "")).strip() for f in fields}
        need = [f for f in fields if f not in registry.OPTIONAL.get(slot, [])]
        if not all(clean[f] for f in need):
            raise ValueError("bu sahələr doldurulmalıdır: " + ", ".join(need))
        self.db.put(f"key:{slot}", seal(json.dumps(clean), self.secret))
        self.db.put(f"keyset:{slot}", str(time.time()))
        self.db.delete(f"check:{slot}")

    def get(self, slot: str) -> dict[str, str] | None:
        raw = self.db.get(f"key:{slot}")
        if raw is None:
            return None
        text = unseal(raw, self.secret)
        if text is None:
            return None
        try:
            return json.loads(text)
        except ValueError:
            return None

    def first(self, slot: str) -> str | None:
        v = self.get(slot)
        return next(iter(v.values()), None) if v else None

    def delete(self, slot: str) -> None:
        for k in (f"key:{slot}", f"keyset:{slot}", f"check:{slot}"):
            self.db.delete(k)

    def status(self, slot: str) -> dict:
        raw = self.db.get(f"key:{slot}")
        v = self.get(slot)
        check = self.db.get(f"check:{slot}")
        return {
            "saved": raw is not None,
            "unreadable": raw is not None and v is None,   # SESSION_SECRET changed: enter the key again
            "hint": mask(next(iter(v.values()), None)) if v else None,
            "saved_ts": float(self.db.get(f"keyset:{slot}") or 0) or None,
            "check": json.loads(check) if check else None,
        }

    def record_check(self, slot: str, ok: bool | None, message: str) -> dict:
        res = {"ok": ok, "message": message[:300], "ts": time.time()}
        self.db.put(f"check:{slot}", json.dumps(res))
        return res


def _scrub(text: str, secrets: list[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text


async def _http_check(url: str, headers: dict | None = None, params: dict | None = None) -> tuple[bool, str]:
    async with httpx.AsyncClient(timeout=CHECK_TIMEOUT) as c:
        r = await c.get(url, headers=headers, params=params)
    if r.status_code == 200:
        return True, "işləyir"
    if r.status_code in (401, 403):
        return False, f"açar qəbul olunmadı (HTTP {r.status_code})"
    if r.status_code == 404:
        return False, "model və ya ünvan tapılmadı (HTTP 404): model adını yoxlayın"
    return False, f"HTTP {r.status_code}"


async def _anthropic_check(key: str, model: str) -> tuple[bool, str]:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=key, timeout=CHECK_TIMEOUT, max_retries=0)
    try:
        await client.models.retrieve(model)
        return True, "işləyir"
    except anthropic.AuthenticationError:
        return False, "açar qəbul olunmadı"
    except anthropic.PermissionDeniedError:
        return False, "açarın bu modelə icazəsi yoxdur"
    except anthropic.NotFoundError:
        return False, f"model tapılmadı: {model}"
    except anthropic.APIConnectionError:
        return False, "Anthropic-ə qoşulmaq alınmadı"
    except anthropic.APIStatusError as e:
        return False, f"HTTP {e.status_code}"
    finally:
        await client.close()


async def check(store: KeyStore, slot: str, model: str | None = None) -> dict:
    """Ask the provider one cheap question (a model or account lookup: no tokens are spent)."""
    v = store.get(slot)
    if v is None:
        return store.record_check(slot, False, "açar saxlanmayıb")
    key = next(iter(v.values()))
    try:
        if slot == "twelvedata":
            ok, msg = await _http_check("https://api.twelvedata.com/api_usage",
                                        headers={"Authorization": f"apikey {key}"})
        elif slot == "anthropic":
            ok, msg = await _anthropic_check(key, model or "claude-haiku-5-5")
        elif slot == "openai":
            ok, msg = await _http_check(f"https://api.openai.com/v1/models/{model or 'gpt-5.4-nano'}",
                                        headers={"Authorization": f"Bearer {key}"})
        elif slot == "xai":
            ok, msg = await _http_check(f"https://api.x.ai/v1/models/{model or 'grok-4.7'}",
                                        headers={"Authorization": f"Bearer {key}"})
        elif slot == "gemini":
            ok, msg = await _http_check(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model or 'gemini-2.5-flash-lite'}",
                headers={"x-goog-api-key": key})
        elif slot == "capital":
            from .providers.capital import CapitalStream
            cs = CapitalStream(v)
            try:
                await cs._session()
                ok, msg = True, f"işləyir ({'demo' if cs.env == 'demo' else 'real'} hesab)"
            except Exception as e:
                ok, msg = False, str(e)
        elif slot == "alpaca":
            ok, msg = await _http_check("https://data.alpaca.markets/v1beta1/news", params={"limit": 1},
                                        headers={"APCA-API-KEY-ID": v.get("key_id", ""),
                                                 "APCA-API-SECRET-KEY": v.get("secret", "")})
        elif slot == "fmp":
            ok, msg = await _http_check("https://financialmodelingprep.com/stable/search-symbol",
                                        params={"query": "AAPL", "apikey": key})
        elif slot == "healthchecks":
            ok, msg = await _http_check("https://healthchecks.io/api/v3/checks/", headers={"X-Api-Key": key})
        elif slot == "fred":
            ok, msg = await _http_check("https://api.stlouisfed.org/fred/series",
                                        params={"series_id": "DFII10", "api_key": key, "file_type": "json"})
        elif slot == "bls":
            async with httpx.AsyncClient(timeout=CHECK_TIMEOUT) as c:
                r = await c.post("https://api.bls.gov/publicAPI/v2/timeseries/data/",
                                 json={"seriesid": ["CUUR0000SA0"], "registrationkey": key, "latest": True})
            body = r.json() if r.status_code == 200 else {}
            ok = body.get("status") == "REQUEST_SUCCEEDED"
            msg = "işləyir" if ok else f"açar qəbul olunmadı: {'; '.join(body.get('message', []))[:120] or r.status_code}"
        elif slot == "databento":
            # metadata only: costs nothing (no data is downloaded); the key is the user name, the password is empty
            async with httpx.AsyncClient(timeout=CHECK_TIMEOUT) as c:
                r = await c.get("https://hist.databento.com/v0/metadata.list_datasets", auth=(key, ""))
            ok = r.status_code == 200 and "GLBX.MDP3" in r.text
            msg = ("tarixçə: işləyir (CME/COMEX, GLBX.MDP3)" if ok else
                   f"açar qəbul olunmadı: HTTP {r.status_code}" if r.status_code in (401, 403) else
                   f"cavab gözlənilən deyil: HTTP {r.status_code}")
            if ok:                                  # the live right is separate from history (owner 27.11 23:00)
                from . import orderflow
                lok, ltext = await orderflow.live_check(key)
                msg += "; " + ltext
                ok = False if lok is False else ok
        elif slot == "r2":
            from . import backup
            ok, msg, bucket = await backup.check_fix(v)
            fixed = {**backup.normalize(v), **({"bucket": bucket} if bucket else {})}
            if fixed != v:                  # values put in their own boxes / the bucket found: kept for the night copy
                store.set("r2", fixed)
                v = store.get("r2") or v
        elif slot == "financialjuice":
            from . import fjnews
            ok, msg = fjnews.check(store.db, v)
        else:
            # No check exists yet for this provider: the key is saved, nothing is known about it (not an error).
            ok, msg = None, "açar saxlanıb; bu açarın yoxlaması növbəti mərhələdə qoşulacaq"
    except httpx.HTTPError as e:
        ok, msg = False, f"qoşulmaq alınmadı: {type(e).__name__}"
    return store.record_check(slot, ok, _scrub(msg, [x for f, x in v.items() if f != "bucket"]))   # a bucket name is no secret
