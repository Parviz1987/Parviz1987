"""TST Trade: a forecast lab for XAU, XAG, XPT, XPD. No trading: forecasts are issued, scored and shown.

Run:  uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8100"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import auth, brains, candles, forecast, judge, keys, registry
from .feeds import Feeds
from .config import BASE_DIR, PROVIDERS, Settings, load_settings
from .db import DB
from .engine import Engine, market_open
from .keys import KeyStore

STATIC = BASE_DIR / "static"
PUBLIC = ("/login", "/healthz", "/version", "/static/")


def create_app(settings: Settings | None = None, start_engine: bool = True) -> FastAPI:
    s = settings or load_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    db = DB(s.db_path)
    store = KeyStore(db, s.session_secret)
    feeds = Feeds(db, store)
    engine = Engine(db, store, s.price_provider, s.poll_seconds, feeds)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_engine:
            engine.start()
        yield
        if start_engine:
            await engine.stop()

    app = FastAPI(title="TST Trade", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db, app.state.keys, app.state.engine, app.state.settings = db, store, engine, s
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        if not any(path == p or path.startswith(p) for p in PUBLIC):
            if not auth.valid(request.cookies.get(auth.COOKIE), s.session_secret):
                if path.startswith("/api/"):
                    return JSONResponse({"error": "giriş lazımdır"}, status_code=401)
                return RedirectResponse("/login", status_code=303)
        if request.method in ("POST", "DELETE") and path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin and origin.split("://", 1)[-1] != request.headers.get("host"):
                return JSONResponse({"error": "başqa saytdan sorğu"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    # ---------- pages ----------
    @app.get("/login")
    async def login_page():
        return FileResponse(STATIC / "login.html")

    @app.post("/login")
    async def login(request: Request):
        form = await request.form()
        if not auth.password_ok(str(form.get("password", "")), db_hash=db.get("auth:password_hash"),
                                env_hash=s.app_password_hash, env_plain=s.app_password):
            return RedirectResponse("/login?e=1", status_code=303)
        r = RedirectResponse("/", status_code=303)
        r.set_cookie(auth.COOKIE, auth.make_token(s.session_secret), max_age=auth.DAYS * 86400, httponly=True,
                     secure=s.cookie_secure, samesite="lax")
        return r

    @app.post("/logout")
    async def logout():
        r = RedirectResponse("/login", status_code=303)
        r.delete_cookie(auth.COOKIE)
        return r

    @app.get("/")
    async def panel():
        return FileResponse(STATIC / "index.html")

    @app.get("/admin")
    async def admin():
        return FileResponse(STATIC / "admin.html")

    @app.get("/version")
    async def version():
        """The commit the server runs (public: shows that the auto-update reached the server)."""
        import subprocess
        try:
            sha = subprocess.run(["git", "-C", str(BASE_DIR), "rev-parse", "--short", "HEAD"], capture_output=True,
                                 text=True, timeout=5).stdout.strip()
        except Exception:
            sha = ""
        return {"commit": sha or None}

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
        live = judge.stats(db, sym, h, "live")
        hist = judge.stats(db, sym, h, "history")
        live_n = max((r["n"] for r in live if r["method"] == "momentum"), default=0)
        basis_stats, basis_mode = (live, "live") if live_n >= judge.MIN_N[h] else (hist, "history")
        verdict = judge.official(basis_stats)
        verdict["by"] = basis_mode
        methods = []
        if row and row["t"] is not None:
            for r in db.execute("SELECT method, p_up, lo50, hi50, lo80, hi80, basis, price0, target_t FROM forecasts "
                                "WHERE symbol=? AND horizon=? AND mode='live' AND issued_t=?", (sym, h, row["t"])):
                methods.append(dict(r))
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

    @app.get("/api/feeds")
    async def feeds_view(metal: str | None = None):
        now = time.time()
        return {"news": feeds.latest_news(30, metal if metal in candles.METALS else None),
                "events": feeds.upcoming(now), "macro": feeds.macro_view(), "event_mode": feeds.event_mode(now),
                "health": {k: feeds.health(k) for k in ("rss", "forexfactory", "fred")}}

    @app.get("/api/journal")
    async def journal(symbol: str, limit: int = 40):
        rows = db.execute("SELECT horizon, method, issued_t, target_t, price0, price1, p_up, lo80, hi80, outcome, "
                          "hit, in80 FROM forecasts WHERE symbol=? AND mode='live' AND scored_ts IS NOT NULL "
                          "AND method IN ('momentum', 'reversal') ORDER BY target_t DESC LIMIT ?",
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
                "history": engine.history_state, "secret_fixed": s.secret_is_fixed}

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
        if name not in ("news", "calendar", "macro"):
            raise HTTPException(404, "naməlum mənbə")
        await feeds.tick(force=name)
        return {k: feeds.health(k) for k in ("rss", "forexfactory", "fred")}

    @app.post("/api/admin/history")
    async def history():
        return await engine.backfill(force=True)

    return app
