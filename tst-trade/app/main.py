"""TST Trade: a forecast lab for XAU, XAG, XPT, XPD. No trading: forecasts are issued, scored and shown.

Run:  uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8100"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import auth, brains, candles, forecast, judge, keys, registry
from . import diag
from .brainjobs import BrainJobs
from .feeds import Feeds
from .config import BASE_DIR, PROVIDERS, Settings, load_settings
from .db import DB
from .engine import Engine, market_open
from .keys import KeyStore

STATIC = BASE_DIR / "static"
PUBLIC = ("/login", "/healthz", "/version", "/api/diag", "/static/", "/sw.js", "/manifest.webmanifest")


def create_app(settings: Settings | None = None, start_engine: bool = True) -> FastAPI:
    s = settings or load_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    db = DB(s.db_path)
    store = KeyStore(db, s.session_secret)
    feeds = Feeds(db, store)
    jobs = BrainJobs(db, store, feeds)
    engine = Engine(db, store, s.price_provider, s.poll_seconds, feeds, jobs)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_engine:
            engine.start()
        yield
        if start_engine:
            await engine.stop()

    def _secrets() -> list[str]:
        out = [s.app_password, s.session_secret]
        for slot in registry.KEY_SLOTS:
            v = store.get(slot["id"])
            if v:
                out += [x for x in v.values() if x]
        return out

    from .security import Guard
    sec = Guard(db)

    def _ip(request: Request) -> str:
        # uvicorn trusts Caddy's X-Forwarded-For from 127.0.0.1: this is the visitor's real address
        return request.client.host if request.client else "?"

    journal = diag.ErrorJournal(db, _secrets)
    logging.getLogger().addHandler(journal)

    app = FastAPI(title="TST Trade", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db, app.state.keys, app.state.engine, app.state.settings = db, store, engine, s
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        who = auth.role(request.cookies.get(auth.COOKIE), s.session_secret)
        if not any(path == p or path.startswith(p) for p in PUBLIC):
            if who is None:
                if path.startswith("/api/"):
                    return JSONResponse({"error": "giriş lazımdır"}, status_code=401)
                return RedirectResponse("/login", status_code=303)
            if who == "guest" and (path.startswith(("/admin", "/api/admin", "/status"))):
                # A guest sees the panel only: no keys, no settings, no password page.
                if path.startswith("/api/"):
                    return JSONResponse({"error": "qonaq üçün bağlıdır"}, status_code=403)
                return RedirectResponse("/", status_code=303)
        if request.method in ("POST", "DELETE") and path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin and origin.split("://", 1)[-1] != request.headers.get("host"):
                return JSONResponse({"error": "başqa saytdan sorğu"}, status_code=403)
        response = await call_next(request)
        if request.method in ("POST", "DELETE") and response.status_code == 200 and path.startswith("/api/admin/"):
            parts = path.split("/")
            kind = {"keys": "key_deleted" if request.method == "DELETE" else "key_saved", "password": "password_changed",
                    "guest": "guest_changed", "provider": "provider_changed",
                    "diag-token": "diag_token_changed"}.get(parts[3] if len(parts) > 3 else "")
            if kind and not path.endswith("/check"):
                sec.log(kind, _ip(request), parts[4] if kind.startswith("key_") and len(parts) > 4 else "")
        tok = request.cookies.get(auth.COOKIE)
        if auth.needs_renewal(tok, s.session_secret):
            # Every visit pushes the 30 days forward: the owner logs in once and stays in.
            response.set_cookie(auth.COOKIE, auth.make_token(s.session_secret, role=who or "owner"),
                                max_age=auth.DAYS * 86400, httponly=True, secure=s.cookie_secure, samesite="lax")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        # HTTPS only from now on (1 year), and only this site's own scripts may run on its pages
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        return response

    # ---------- pages ----------
    @app.get("/login")
    async def login_page():
        return FileResponse(STATIC / "login.html")

    @app.post("/login")
    async def login(request: Request):
        ip = _ip(request)
        if sec.is_blocked(ip):
            return RedirectResponse("/login?e=blocked", status_code=303)
        form = await request.form()
        given = str(form.get("password", ""))
        if auth.password_ok(given, db_hash=db.get("auth:password_hash"), env_hash=s.app_password_hash,
                            env_plain=s.app_password):
            who = "owner"
        elif auth.guest_ok(given, db.get("auth:guest_hash")):
            who = "guest"
        else:
            sec.failed(ip, "login")
            await asyncio.sleep(1.0)      # every wrong try costs a second: guessing at speed is impossible
            return RedirectResponse("/login?e=1", status_code=303)
        sec.succeeded(ip, who)
        r = RedirectResponse("/", status_code=303)
        r.set_cookie(auth.COOKIE, auth.make_token(s.session_secret, role=who), max_age=auth.DAYS * 86400,
                     httponly=True, secure=s.cookie_secure, samesite="lax")
        return r

    @app.post("/logout")
    async def logout():
        r = RedirectResponse("/login", status_code=303)
        r.delete_cookie(auth.COOKIE)
        return r

    @app.get("/")
    async def panel():
        return FileResponse(STATIC / "index.html")

    # The installable app: the worker must be served from the root to control every page.
    @app.get("/sw.js")
    async def service_worker():
        return FileResponse(STATIC / "sw.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})

    @app.get("/manifest.webmanifest")
    async def manifest():
        return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")

    @app.get("/admin")
    async def admin():
        return FileResponse(STATIC / "admin.html")

    def _commit() -> str | None:
        import subprocess
        try:
            return subprocess.run(["git", "-C", str(BASE_DIR), "rev-parse", "--short", "HEAD"], capture_output=True,
                                  text=True, timeout=5).stdout.strip() or None
        except Exception:
            return None

    @app.get("/version")
    async def version():
        """The commit the server runs (public: shows that the auto-update reached the server)."""
        return {"commit": _commit()}

    @app.get("/status")
    async def status_page():
        return FileResponse(STATIC / "status.html")

    @app.get("/api/admin/status")
    async def status_data():
        return {**diag.report(db, store, engine, feeds, jobs, _commit()), "security_events": sec.recent(30)}

    @app.get("/api/diag")
    async def diagnostics(request: Request):
        """Read-only report for the outside reviewer. Needs the diagnostics token (Authorization: Bearer ...)."""
        ip = _ip(request)
        if sec.is_blocked(ip):
            return JSONResponse({"error": "çox səhv cəhd: 15 dəqiqə gözləyin"}, status_code=429)
        stored = db.get("auth:diag_hash")
        given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not stored or not given or not auth.verify_hash(given, stored):
            if given:
                sec.failed(ip, "diag")
            return JSONResponse({"error": "diaqnostika açarı lazımdır"}, status_code=401)
        return diag.report(db, store, engine, feeds, jobs, _commit())

    @app.post("/api/admin/diag-token")
    async def new_diag_token():
        """A new diagnostics token, shown once. Only its hash is stored; it can read /api/diag and nothing else."""
        import secrets as _secrets_mod
        tok = "tstdiag_" + _secrets_mod.token_urlsafe(32)
        db.put("auth:diag_hash", auth.hash_password(tok))
        return {"token": tok}

    @app.delete("/api/admin/diag-token")
    async def drop_diag_token():
        db.delete("auth:diag_hash")
        return {"ok": True}

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    # ---------- panel data ----------
    @app.get("/api/state")
    async def state():
        now = time.time()
        metals = []
        for sym in candles.METALS:
            q = engine.quotes.get(sym)
            day = candles.get(db, sym, "1d", limit=1)
            metals.append({"symbol": sym, "name": candles.NAMES[sym],
                           "price": q["price"] if q else None, "source_ts": q["source_ts"] if q else None,
                           "recv_ts": q["recv_ts"] if q else None, "ts_missing": q["ts_missing"] if q else None,
                           "source": engine.provider_name,
                           "status": engine.status(sym, now), "day_open": day[-1]["o"] if day else None,
                           "error": engine.errors.get(sym) or engine.errors.get("*")})
        return {"now": now, "provider": engine.provider_name, "market_open": market_open(now),
                "event_mode": feeds.event_mode(now),
                "last_ok": engine.last_ok, "poll": engine.poll, "metals": metals}

    @app.get("/api/candles")
    async def get_candles(symbol: str, tf: str = "1m", limit: int = 200):
        if symbol not in candles.METALS or tf not in candles.TF:
            raise HTTPException(400, "naməlum metal və ya zaman çərçivəsi")
        return {"symbol": symbol, "tf": tf, "candles": candles.get(db, symbol, tf, min(max(limit, 10), 1000))}

    def _card(sym: str, h: str) -> dict:
        tf = forecast.HORIZONS[h]
        row = db.execute("SELECT MAX(issued_t) t FROM forecasts WHERE symbol=? AND horizon=? AND mode='live'",
                         (sym, h)).fetchone()
        live = judge.stats(db, sym, h, "live", ttl=60)
        hist = judge.stats(db, sym, h, "history", ttl=300)
        live_n = max((r["n"] for r in live if r["method"] == "momentum"), default=0)   # momentum always has a view
        basis_stats, basis_mode = (live, "live") if live_n >= judge.MIN_N[h] else (hist, "history")
        verdict = judge.official(basis_stats)
        verdict["by"] = basis_mode
        methods = []
        if row and row["t"] is not None:
            for r in db.execute("SELECT method, p_up, lo50, hi50, lo80, hi80, basis, price0, target_t FROM forecasts "
                                "WHERE symbol=? AND horizon=? AND mode='live' AND issued_t=?", (sym, h, row["t"])):
                methods.append(dict(r))
        if verdict["status"] != "sübut" and methods:
            # Conditional proof: a method proven only in this session or this market mood speaks only then.
            rw = next((m for m in methods if m["method"] == "rw"), None)
            width = (rw["hi80"] - rw["lo80"]) / rw["price0"] if rw and rw["price0"] else None
            cond = judge.conditional(_where(sym, h, basis_mode), judge.session_of(time.time()), width)
            live_view = cond and next((m for m in methods if m["method"] == cond["method"] and m["p_up"] != 0.5), None)
            if live_view:
                verdict = {"method": cond["method"], "status": "sübut", "by": basis_mode, "condition": cond["group"],
                           "cond_hit_rate": cond["hit_rate"], "cond_n": cond["n"]}
        have = len(candles.closed(db, sym, tf, time.time(), limit=forecast.MIN_CANDLES))
        return {"horizon": h, "name": forecast.HORIZON_NAMES[h], "tf": tf, "issued_t": row["t"] if row else None,
                "methods": methods, "verdict": verdict, "stats_live": live, "stats_history": hist,
                "candles_have": have, "candles_need": forecast.MIN_CANDLES}

    @app.get("/api/forecasts")
    async def forecasts(symbol: str):
        if symbol not in candles.METALS:
            raise HTTPException(400, "naməlum metal")
        return {"symbol": symbol, "method_names": forecast.METHOD_NAMES,
                "cards": [_card(symbol, h) for h in forecast.HORIZONS]}

    _series_cache: dict = {}

    # FRED's daily value stands in for a related market the broker does not have (shown as daily, never as live)
    FRED_FOR = {"DXY": "DTWEXBGS", "VIX": "VIXCLS", "US500": "SP500", "US10Y": "DGS10", "OIL": "DCOILWTICO"}

    @app.get("/api/markets")
    async def markets_view(metal: str = "XAU"):
        """Every market that moves the metals on one screen: live price, day change, a 2-day sparkline, why it is
        linked, how strongly it moves with the metal and whether it moves first (measured, cached 10 minutes)."""
        from . import markets as mk
        if metal not in candles.METALS:
            raise HTTPException(400, "naməlum metal")
        now = time.time()
        epics = mk.saved(db).get("epics", {})
        fred = {m["series"]: m for m in feeds.macro_view()}
        out = []
        for code in list(candles.METALS) + list(mk.RELATED):
            info = mk.RELATED.get(code, {"name": candles.NAMES.get(code, code), "why": "", "sign": None})
            row = {"code": code, "name": info["name"], "why": info["why"], "sign": info["sign"],
                   "live": code in candles.METALS or code in epics}
            if row["live"]:
                q = engine.quotes.get(code)
                day = candles.get(db, code, "1d", limit=1)
                row.update({"price": q["price"] if q else None, "status": engine.status(code, now) if q else "OFFLINE",
                            "day_open": day[-1]["o"] if day else None,
                            "spark": [c["c"] for c in candles.get(db, code, "1h", limit=48)]})
                if code != metal:
                    key = ("links", code, metal)
                    hit = _series_cache.get(key)
                    if not hit or now - hit[0] > 600:
                        hit = (now, mk.links(db, code, metal, now))
                        _series_cache[key] = hit
                    row["links"] = hit[1]
            elif code in FRED_FOR and fred.get(FRED_FOR[code], {}).get("value") is not None:
                f = fred[FRED_FOR[code]]
                row.update({"daily": f["value"], "daily_date": f["date"], "daily_change": f.get("change_week")})
            out.append(row)
        return {"metal": metal, "markets": out, "resolved": bool(epics), "resolve_error": mk.saved(db).get("error")}

    @app.get("/api/passports")
    async def passports(symbol: str = "XAU"):
        """Each method's passport and the Judge's current verdict for it on every horizon (history and live)."""
        if symbol not in candles.METALS:
            raise HTTPException(400, "naməlum metal")
        rows = []
        for m in forecast.METHODS:
            res = {}
            for h in forecast.HORIZONS:
                if m not in forecast.methods_for(h):
                    continue
                for mode in ("live", "history"):
                    r = next((x for x in judge.stats(db, symbol, h, mode, ttl=300) if x["method"] == m), None)
                    if r:
                        res.setdefault(h, {})[mode] = {k: r[k] for k in ("status", "nh", "n", "hit_rate")}
            fam = forecast.FAMILY.get(m)
            rows.append({"method": m, "name": forecast.METHOD_NAMES[m], **forecast.PASSPORT.get(m, {}), "results": res,
                         "family": forecast.FAMILY_NAMES.get(fam) if fam else None})
        return {"symbol": symbol, "horizons": forecast.HORIZON_NAMES, "methods": rows}

    def _where(symbol: str, horizon: str, mode: str) -> dict:
        key = ("where", symbol, horizon, mode)
        hit = _series_cache.get(key)
        if hit and time.time() - hit[0] < 600:   # a heavy grouping; the picture changes slowly
            return hit[1]
        out = judge.where(db, symbol, horizon, mode)
        _series_cache[key] = (time.time(), out)
        return out

    @app.get("/api/judge/where")
    async def judge_where(symbol: str, horizon: str, mode: str = "history"):
        if symbol not in candles.METALS or horizon not in forecast.HORIZONS or mode not in ("live", "history"):
            raise HTTPException(400, "naməlum metal, üfüq və ya rejim")
        return _where(symbol, horizon, mode)

    @app.get("/api/judge/series")
    async def judge_series(symbol: str, horizon: str, mode: str = "live"):
        if symbol not in candles.METALS or horizon not in forecast.HORIZONS or mode not in ("live", "history"):
            raise HTTPException(400, "naməlum metal, üfüq və ya rejim")
        key = (symbol, horizon, mode)
        hit = _series_cache.get(key)
        if hit and time.time() - hit[0] < 120:     # the panel asks every 20 s; the picture changes slowly
            return hit[1]
        out = judge.series(db, symbol, horizon, mode)
        _series_cache[key] = (time.time(), out)
        return out

    @app.get("/api/feeds")
    async def feeds_view(metal: str | None = None):
        now = time.time()
        news = feeds.latest_news(30, metal if metal in candles.METALS else None)
        labels = {r["uid"]: dict(r) for r in db.execute(
            "SELECT n.uid, a.direction, a.strength, a.metals AS ai_metals, a.event FROM news n JOIN news_ai a "
            "ON a.uid=n.uid WHERE n.ts > ?", (now - 7 * 86400,)).fetchall()} if news else {}
        for n in news:
            n["ai"] = labels.get(n.get("uid"))
        from . import surprise
        return {"news": news, "releases": surprise.recent(db, now), "hunter": jobs.hunter.recent(4),
                "events": feeds.upcoming(now), "macro": feeds.macro_view(), "event_mode": feeds.event_mode(now),
                "cot": feeds.cot_view(),
                "health": {k: feeds.health(k) for k in ("rss", "forexfactory", "fred", "cot", "alpaca", "fmp")}}

    _rs_cache: list = [0.0, None]

    @app.get("/api/brains")
    async def brains_view():
        from .brainjobs import reader_score
        now = time.time()
        if now - _rs_cache[0] > 300:           # many small lookups: recomputed at most every 5 minutes
            _rs_cache[:] = [now, reader_score(db, now)]
        return {"strategist": jobs.last_explanation(), "reader": jobs.state("reader"),
                "strategist_state": jobs.state("strategist"), "reader_score": _rs_cache[1],
                "scout": jobs.last_scout(), "scout_state": jobs.state("scout")}

    @app.get("/api/journal")
    async def journal(symbol: str, limit: int = 40):
        rows = db.execute("SELECT horizon, method, issued_t, target_t, price0, price1, p_up, lo80, hi80, outcome, "
                          "hit, in80, basis FROM forecasts WHERE symbol=? AND mode='live' AND scored_ts IS NOT NULL "
                          "AND method NOT IN ('rw', 'up') AND hit IS NOT NULL ORDER BY target_t DESC LIMIT ?",
                          (symbol, min(max(limit, 1), 200))).fetchall()
        return {"rows": [dict(r) for r in rows]}

    # ---------- admin ----------
    @app.get("/api/admin/overview")
    async def overview():
        slots = [{**slot, "state": store.status(slot["id"]), "health": feeds.health(slot["id"])}
                 for slot in registry.KEY_SLOTS]
        free = [{**f, "health": feeds.health(f["id"])} for f in registry.FREE_SOURCES]
        return {"categories": registry.CATEGORIES, "keys": slots, "free": free,
                "brains": brains.view(db, store), "providers": list(PROVIDERS),
                "brain_providers": list(registry.BRAIN_PROVIDERS),
                "price_provider": engine.chosen_provider(), "active_provider": engine.provider_name,
                "history": engine.history_state, "secret_fixed": s.secret_is_fixed,
                "guest": db.get("auth:guest_hash") is not None, "diag": db.get("auth:diag_hash") is not None}

    @app.post("/api/admin/keys/{slot}")
    async def save_key(slot: str, request: Request):
        try:
            store.set(slot, await request.json())
        except ValueError as e:
            raise HTTPException(400, str(e))
        engine.reset_provider()
        return store.status(slot)

    @app.delete("/api/admin/keys/{slot}")
    async def delete_key(slot: str):
        if slot not in registry.KEY_IDS:
            raise HTTPException(404, "naməlum açar yeri")
        store.delete(slot)
        engine.reset_provider()
        return store.status(slot)

    @app.post("/api/admin/keys/{slot}/check")
    async def check_key(slot: str):
        if slot not in registry.KEY_IDS:
            raise HTTPException(404, "naməlum açar yeri")
        res = await keys.check(store, slot)
        if slot == "capital" and res["ok"]:
            # A working Capital.com key switches the live price to its stream at once (gold-api.com stays the fallback).
            db.put("setting:price_provider", "capital")
            engine.reset_provider()
        return res

    @app.post("/api/admin/brains/{slot}")
    async def save_brain(slot: str, request: Request):
        try:
            return brains.save(db, slot, await request.json())
        except (ValueError, TypeError) as e:
            raise HTTPException(400, str(e))

    @app.post("/api/admin/brains/{slot}/check")
    async def check_brain(slot: str):
        if slot not in registry.BRAIN_IDS:
            raise HTTPException(404, "naməlum yuva")
        cfg = brains.config(db, slot)
        return await keys.check(store, cfg["provider"], cfg["model"])

    @app.post("/api/admin/provider")
    async def set_provider(request: Request):
        name = (await request.json()).get("provider")
        if name not in PROVIDERS:
            raise HTTPException(400, "naməlum mənbə")
        db.put("setting:price_provider", name)
        engine.reset_provider()
        return {"price_provider": name}

    @app.post("/api/admin/password")
    async def change_password(request: Request):
        body = await request.json()
        old, new, again = (str(body.get(k, "")) for k in ("old", "new", "again"))
        if not auth.password_ok(old, db_hash=db.get("auth:password_hash"), env_hash=s.app_password_hash,
                                env_plain=s.app_password):
            raise HTTPException(400, "köhnə parol səhvdir")
        if len(new) < auth.MIN_LEN:
            raise HTTPException(400, f"yeni parol ən azı {auth.MIN_LEN} simvol olmalıdır")
        if new != again:
            raise HTTPException(400, "yeni parol iki dəfə eyni yazılmayıb")
        db.put("auth:password_hash", auth.hash_password(new))
        return {"ok": True}

    @app.post("/api/admin/feeds/{name}")
    async def refresh_feed(name: str):
        if name not in ("news", "calendar", "macro", "cot"):
            raise HTTPException(404, "naməlum mənbə")
        await feeds.tick(force=name)
        return {k: feeds.health(k) for k in ("rss", "forexfactory", "fred", "cot")}

    @app.post("/api/admin/guest")
    async def set_guest(request: Request):
        body = await request.json()
        pw = str(body.get("password", ""))
        if not pw:
            db.delete("auth:guest_hash")
            return {"guest": False}
        if len(pw) < auth.MIN_LEN:
            raise HTTPException(400, f"qonaq parolu ən azı {auth.MIN_LEN} simvol olmalıdır")
        db.put("auth:guest_hash", auth.hash_password(pw))
        return {"guest": True}

    @app.get("/api/me")
    async def me(request: Request):
        return {"role": auth.role(request.cookies.get(auth.COOKIE), s.session_secret)}

    @app.post("/api/admin/history")
    async def history():
        return await engine.backfill(force=True)

    return app
