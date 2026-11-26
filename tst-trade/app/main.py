"""TST Trade: a forecast lab for XAU, XAG, XPT, XPD. No trading: forecasts are issued, scored and shown.

Run:  uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8100"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import auth, brains, brainviews, candles, forecast, judge, keys, registry
from . import diag
from . import feeds as feeds_mod
from .brainjobs import BrainJobs
from .feeds import Feeds
from .config import BASE_DIR, PROVIDERS, Settings, load_settings
from .db import DB
from .engine import Engine, market_open
from .keys import KeyStore

STATIC = BASE_DIR / "static"
log = logging.getLogger("tst.main")
PUBLIC = ("/login", "/healthz", "/version", "/api/diag", "/static/", "/sw.js", "/manifest.webmanifest")


def create_app(settings: Settings | None = None, start_engine: bool = True) -> FastAPI:
    s = settings or load_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # httpx logs every request URL at INFO: the watcher's ping addresses (and any key in a query) stay out of the log
    logging.getLogger("httpx").setLevel(logging.WARNING)
    db = DB(s.db_path)
    store = KeyStore(db, s.session_secret)
    feeds = Feeds(db, store)
    jobs = BrainJobs(db, store, feeds)
    engine = Engine(db, store, s.price_provider, s.poll_seconds, feeds, jobs)
    from .activity import Hub
    hub = Hub(db)                       # the one place every agent reports to; the agents panel reads only this
    engine.activity = feeds.activity = jobs.activity = hub
    from . import heartbeat
    heart = heartbeat.Heart(db, store)
    if start_engine:
        heartbeat.HEART = heart          # the outside watcher (plan step 1); tests build apps without it

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        hub.attach_loop(asyncio.get_running_loop())
        # every start of the process, with its commit and how long the start took (2026-11-26: the server restarted
        # once without a new version; this journal shows when and why — a slow start, a rollback or a crash)
        try:
            boots = json.loads(db.get("boot:log") or "[]")[-19:]
        except ValueError:
            boots = []
        boots.append({"ts": time.time(), "commit": _commit(), "startup_s": round(time.time() - diag.STARTED, 1)})
        db.put("boot:log", json.dumps(boots))
        if start_engine:
            engine.start()

            async def _cleanup():              # owner 2026-11-26: the retired methods' archive goes (record kept)
                await asyncio.sleep(120)
                from . import cleanup
                try:
                    res = await asyncio.to_thread(cleanup.run, db)
                    log.info("cleanup: %s", res)
                except Exception:
                    log.exception("cleanup failed")
                while not db.get(cleanup.VACUUM_MARK):      # the file shrinks once, after the night's backup
                    if cleanup.vacuum_due(db):
                        try:
                            log.info("vacuum: %s", await asyncio.to_thread(cleanup.vacuum, db))
                        except Exception:
                            log.exception("vacuum failed")
                            db.put(cleanup.VACUUM_MARK, json.dumps({"error": "bax: xəta jurnalı", "ts": time.time()}))
                        break
                    await asyncio.sleep(300)
            async def _conductor():            # owner 2026-11-26: does each voice do better in some market states?
                from . import conductor
                await asyncio.sleep(600)
                while True:
                    hour = time.gmtime().tm_hour
                    if conductor.audit_due(db) and hour not in (4, 5):   # never during the night's backup / vacuum
                        try:
                            log.info("conductor: %s", await asyncio.to_thread(conductor.run, db))
                        except Exception:
                            log.exception("conductor audit failed")
                    await asyncio.sleep(3600)
            async def _alive():                # every 5 minutes: the panel and the price, for the outside watcher
                import os
                heartbeat.deploy_signal(heart, os.path.join(os.path.dirname(os.path.abspath(s.db_path)), "update.log"))
                n = 0
                while True:
                    n += 1
                    try:
                        if n % 288 == 0:        # once a day: the deploy check hears «still fine» (period 30 days)
                            heartbeat.deploy_signal(heart, os.path.join(os.path.dirname(os.path.abspath(s.db_path)),
                                                                        "update.log"))
                        heartbeat.alive_signals(heart, engine)
                    except Exception:
                        log.exception("alive signal failed")
                    await asyncio.sleep(300)
            asyncio.get_running_loop().create_task(heart.run())
            asyncio.get_running_loop().create_task(_alive())
            asyncio.get_running_loop().create_task(_cleanup())
            asyncio.get_running_loop().create_task(_conductor())
            asyncio.get_running_loop().create_task(app.state.futures_keeper())
            asyncio.get_running_loop().create_task(app.state.futures_daily())
            asyncio.get_running_loop().create_task(app.state.rigor_daily())
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
    diag._SEALER[:] = [s.session_secret]

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
            if who == "guest" and (path.startswith(("/admin", "/api/admin", "/status", "/agents", "/api/agents",
                                                    "/ehtiyat", "/api/stock"))):
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
        host = request.headers.get("host", "")
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            f"connect-src 'self' wss://{host}; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
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
            from . import totp
            got = totp.check(db, s.session_secret, str(form.get("code", "")))
            if got is None:            # right password, wrong or missing 2FA code: a failed try like any other
                sec.failed(ip, "login")
                sec.log("login_code_fail", ip)
                await asyncio.sleep(1.0)
                return RedirectResponse("/login?e=code", status_code=303)
            if got == "recovery":
                sec.log("recovery_used", ip, "ehtiyat kod istifadə olundu")
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
        rep = await asyncio.to_thread(diag.report, db, store, engine, feeds, jobs, _commit())
        from . import geo
        ev = sec.recent(30)
        for e in ev:
            e["place"] = geo.label(geo.place(e.get("ip"), db.path))
        return {**rep, "security_events": ev}

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
        heartbeat.beat("duty-check", "ok", "diaqnostika oxundu")
        # off the event loop: the report includes the shadow-trading summary (seconds of work when not cached)
        return await asyncio.to_thread(diag.report, db, store, engine, feeds, jobs, _commit())

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
        verdict = judge.verdict(db, sym, h)          # the one verdict (also used by the decision strip and outlook)
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

    # ---------- agents panel ----------
    @app.get("/agents")
    async def agents_page():
        return FileResponse(STATIC / "agents.html")

    @app.get("/api/agents/events")
    async def agent_events(hours: float = 24):
        """The timeline: every agent event of the last hours (at most 7 days), oldest first, for replay."""
        hours = min(max(hours, 0.1), 168)
        snap = hub.snapshot()
        return {"nodes": snap["nodes"], "events": hub.events(time.time() - hours * 3600), "now": time.time()}

    @app.get("/api/agents/top")
    async def agents_top():
        """The bar on top: last sync times and the brains' monthly spend against their limits."""
        now = time.time()
        sync = {"Qiymət": engine.last_ok}
        for sid, name in (("rss", "Xəbər"), ("forexfactory", "Təqvim"), ("fred", "FRED"), ("cot", "COT"),
                          ("alpaca", "Benzinga")):
            sync[name] = feeds.health(sid).get("ok_ts")
        limits = [{"name": b["name"], "spent": b["spent"], "cap": float(b["config"]["month_usd"])}
                  for b in brains.view(db, store) if b["in_use"]]
        return {"now": now, "sync": sync, "limits": limits}

    @app.websocket("/ws/agents")
    async def agents_ws(ws: WebSocket):
        """Live stream for the panel: the current state at once, then every event as it happens. Owner only; the
        page must come from this site (a foreign page cannot open the owner's stream)."""
        origin = ws.headers.get("origin", "")
        if auth.role(ws.cookies.get(auth.COOKIE), s.session_secret) != "owner" or \
                (origin and origin.split("://", 1)[-1] != ws.headers.get("host")):
            await ws.close(code=4403)
            return
        await ws.accept()
        q: asyncio.Queue = asyncio.Queue()
        hub.subscribers.add(q)
        try:
            await ws.send_text(json.dumps(hub.snapshot()))
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=25)
                except asyncio.TimeoutError:
                    msg = json.dumps({"type": "ping", "now": time.time()})   # keeps proxies from closing the line
                await ws.send_text(msg)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            hub.subscribers.discard(q)

    def related_quote(code: str, now: float) -> tuple[float | None, str, float | None]:
        """A linked market's price for the panel: the live quote, or — when the stream has sent nothing for a while
        (a quiet market sends a price only when it changes, e.g. the 10-year note at night) — the last candle's close,
        marked QUIET with its time. OFFLINE only when nothing came for 2 hours."""
        q = engine.quotes.get(code)
        st = engine.status(code, now) if q else "OFFLINE"
        if st in ("LIVE", "DELAYED"):
            return q["price"], st, q["recv_ts"]
        last = db.execute("SELECT t, c FROM candles WHERE symbol=? AND tf='1m' ORDER BY t DESC LIMIT 1", (code,)).fetchone() \
            or db.execute("SELECT t, c FROM candles WHERE symbol=? AND tf='15m' ORDER BY t DESC LIMIT 1", (code,)).fetchone()
        if last and now - last["t"] < 2 * 3600:
            return last["c"], "QUIET", last["t"]
        return (last["c"] if last else None), "OFFLINE", (last["t"] if last else None)

    @app.get("/api/signals")
    async def signals_api(symbol: str = "XAU", hours: float = 48):
        """The alarms of one metal (and the market-wide ones) for the chart's marks: when, what kind, why."""
        from . import signals as sg
        sg.ensure(db)
        since = time.time() - min(max(hours, 1), 24 * 14) * 3600
        rows = db.execute("SELECT ts, kind, metal, strength, text FROM signals WHERE ts > ? AND "
                          "(metal IS NULL OR metal = ? OR metal LIKE ? OR metal LIKE ?) ORDER BY ts",
                          (since, symbol, symbol + ",%", "%," + symbol + "%")).fetchall()
        return {"symbol": symbol, "signals": [dict(r) for r in rows]}

    @app.get("/api/ticker")
    async def ticker():
        """The strip under the metal tiles: every market our analysis reads, with its price and today's change —
        the linked markets from the broker stream, the ETF proxies (US hours) and the nearest Fed decision odds."""
        from . import markets as mk
        from .feeds import ETF_SYMBOLS
        now = time.time()
        rows = []
        for code in mk.saved(db).get("epics", {}):
            price, st, _ = related_quote(code, now)
            day = candles.get(db, code, "1d", limit=1)
            rows.append({"code": code, "name": mk.RELATED.get(code, {}).get("name", code),
                         "price": price, "day_open": day[-1]["o"] if day else None, "status": st, "kind": "bazar"})
        day0 = int(now // 86400 * 86400)
        for sym in ETF_SYMBOLS:
            last = candles.get(db, sym, "15m", limit=1)
            first = db.execute("SELECT o FROM candles WHERE symbol=? AND tf='15m' AND t>=? ORDER BY t LIMIT 1",
                               (sym, day0)).fetchone()
            rows.append({"code": sym, "name": sym, "price": last[-1]["c"] if last else None,
                         "day_open": first["o"] if first else None,
                         "status": "LIVE" if last and now - last[-1]["t"] < 1800 else "DELAYED", "kind": "ETF"})
        fed = feeds.fed_odds(3)
        return {"markets": rows, "fed": fed, "ts": now}

    @app.get("/api/agents/state")
    async def agents_state():
        """The hub's current picture without a WebSocket (the panel's system-flow strip polls it)."""
        return hub.snapshot()

    @app.get("/api/hypotheses")
    async def hypotheses_api():
        """Block 8: the pre-registered hypotheses, judged only on live forecasts issued after their registration."""
        from . import hypotheses
        return {"registered": hypotheses.REGISTERED, "p_bar": hypotheses.P_BAR,
                "items": await asyncio.to_thread(diag._slow, "hypotheses", lambda: hypotheses._close(hypotheses.evaluate(db))),
                "focus_registered": hypotheses.FOCUS_REGISTERED, "focus_p_bar": hypotheses.FOCUS_P_BAR,
                "focus": await asyncio.to_thread(diag._slow, "focus", lambda: hypotheses._close(hypotheses.evaluate_focus(db))),
                "v_registered": hypotheses.V_REGISTERED, "v_p_bar": hypotheses.V_P_BAR,
                "v": await asyncio.to_thread(diag._slow, "vtests", lambda: hypotheses.evaluate_v(db))}

    @app.get("/api/trust")
    async def trust_api():
        """Etibar işığı: every analyst and the unified forecast as one light and one sentence."""
        from . import trust
        return await asyncio.to_thread(diag._slow, "trust", lambda: trust.build(db), 300)

    @app.get("/api/outlook")
    async def outlook_api():
        """Sabah üçün proqnoz: per metal the 1-day range, the three voices on direction with their records, the proof."""
        from . import outlook
        return await asyncio.to_thread(diag._slow, "outlook", lambda: outlook.all_metals(db), 120)

    @app.get("/ehtiyat")
    async def stock_page():
        return FileResponse(STATIC / "ehtiyat.html")

    @app.get("/api/stock")
    async def stock_api():
        """The owner's physical metal: each lot valued at the live price, totals, sensitivity, sales (owner only)."""
        from . import stock
        return await asyncio.to_thread(stock.view, db)

    @app.post("/api/stock/{action}")
    async def stock_write(action: str, request: Request):
        from . import stock
        b = await request.json()
        try:
            if action == "lot":
                return {"id": stock.add_lot(db, str(b.get("name", "")), str(b.get("metal", "")).upper(), float(b["grams"]),
                                            float(b["assay"]), float(b["cost"]), str(b.get("bought", "")),
                                            str(b.get("note", "")))}
            if action == "csv":
                return stock.import_csv(db, str(b.get("text", ""))[:200_000])
            if action == "sell":
                return stock.sell(db, int(b["lot_id"]), float(b["grams"]), float(b["assay"]), float(b["received"]),
                                  str(b.get("note", "")))
            if action == "delete":
                stock.delete_lot(db, int(b["lot_id"]))
                return {"ok": True}
            if action == "settings":
                return stock.set_settings(db, float(b["refiner_fee_pct"]), float(b["melt_loss_pct"]))
        except (KeyError, TypeError, ValueError) as e:
            raise HTTPException(400, str(e)[:200])
        raise HTTPException(404, "naməlum əməliyyat")

    @app.get("/bloklar")
    async def blocks_page():
        return FileResponse(STATIC / "bloklar.html")

    @app.get("/api/blocks")
    async def blocks_api(symbol: str = "XAU", horizon: str = "1h"):
        """The organs: each block's voice now, its methods' views and records, evidence and what is missing."""
        from . import blocks
        if symbol not in candles.METALS or horizon not in forecast.HORIZONS:
            raise HTTPException(400, "naməlum metal və ya üfüq")
        return await asyncio.to_thread(diag._slow, f"blocks:{symbol}:{horizon}",
                                       lambda: blocks.status(db, symbol, horizon), 60)

    @app.get("/xeber")
    async def news_page():
        return FileResponse(STATIC / "xeber.html")

    @app.get("/api/xeber")
    async def news_api(symbol: str = "XAU"):
        """The news block: 1-hour chart with the news rules' firings, the latest labelled headlines, the mood by
        topic, the voice now and the book with the Judge's record."""
        from . import newsblock
        if symbol not in candles.METALS:
            raise HTTPException(400, "naməlum metal")
        return await asyncio.to_thread(diag._slow, f"nw:{symbol}", lambda: newsblock.page(db, symbol), 60)

    @app.get("/bazarlar")
    async def cm_page():
        return FileResponse(STATIC / "bazarlar.html")

    @app.get("/api/bazarlar")
    async def cm_api(symbol: str = "XAU", tf: str = "1h"):
        """The cross-market block: the metal with the rules' firings, each linked market, the vote and the book."""
        from . import crossmarket
        if symbol not in candles.METALS or tf not in crossmarket.TFS:
            raise HTTPException(400, "naməlum metal və ya vaxt çərçivəsi")
        return await asyncio.to_thread(diag._slow, f"cm:{symbol}:{tf}", lambda: crossmarket.page(db, symbol, tf), 120)

    @app.get("/vaxt")
    async def tm_page():
        return FileResponse(STATIC / "vaxt.html")

    @app.get("/api/vaxt")
    async def tm_api(symbol: str = "XAU", tf: str = "1h"):
        """The time block: the metal with the calendar rules' firings, hour and weekday statistics, the calendar ahead,
        the slow methods, the vote and the book."""
        from . import timeblock
        if symbol not in candles.METALS or tf not in timeblock.TFS:
            raise HTTPException(400, "naməlum metal və ya vaxt çərçivəsi")
        return await asyncio.to_thread(diag._slow, f"tm:{symbol}:{tf}", lambda: timeblock.page(db, symbol, tf), 120)

    @app.get("/fundamental")
    async def fa_page():
        return FileResponse(STATIC / "fundamental.html")

    @app.get("/api/fundamental")
    async def fa_api(symbol: str = "XAU"):
        """The fundamental block: gold with the rules' firings, every driver, central banks, COT, surprises, the vote
        and the book with the Judge's record."""
        from . import fundamental
        if symbol not in candles.METALS:
            raise HTTPException(400, "naməlum metal")
        return await asyncio.to_thread(diag._slow, f"fa:{symbol}", lambda: fundamental.page(db, symbol), 120)

    @app.get("/ta")
    async def ta_page():
        return FileResponse(STATIC / "ta.html")

    @app.get("/api/ta")
    async def ta_api(symbol: str = "XAU", tf: str = "1h"):
        """The technical-analysis block: candles, every layer, every rule firing, the book with the Judge's record,
        and what the block says now for this timeframe (the same vote the forecasts use)."""
        from . import ta
        if symbol not in candles.METALS or tf not in ta.HORIZON:
            raise HTTPException(400, "naməlum metal və ya zaman çərçivəsi")
        return await asyncio.to_thread(diag._slow, f"ta:{symbol}:{tf}", lambda: ta.build(db, symbol, tf), 60)

    @app.get("/bilik")
    async def bilik_page():
        return FileResponse(STATIC / "bilik.html")

    @app.get("/api/bilik")
    async def bilik_api():
        """Block 25/28: the Bilik kitabı (our rules) with each rule's measured record and what fires right now."""
        from . import cards as cards_mod, playbook, rules

        def build():
            return {"version": playbook.VERSION, "rules": playbook.RULES, "areas": playbook.AREAS,
                    "records": rules.records(db), "active": {s: rules.active_now(db, s) for s in candles.METALS},
                    "brain_rules": cards_mod.rule_record(db),
                    "proposals": [dict(r) for r in db.execute(
                        "SELECT * FROM rule_proposals ORDER BY ts DESC LIMIT 30").fetchall()]
                    if db.execute("SELECT 1 FROM sqlite_master WHERE name='rule_proposals'").fetchone() else []}
        return await asyncio.to_thread(diag._slow, "bilik", build, 300)

    @app.get("/api/futstudy")
    async def futstudy_api():
        """Block 21: the futures tests (impulse with real volume, after US releases, both years, futures vs Capital cost)."""
        from . import futstudy
        return {"study": futstudy.summary(db), "download": json.loads(db.get("futures:last") or "null")}

    @app.get("/api/cards")
    async def cards_api(symbol: str | None = None, limit: int = 20):
        """Block 16: the frozen forecast cards (newest first) and the right/wrong summary of the scored ones."""
        from . import cards
        if symbol is not None and symbol not in candles.METALS:
            raise HTTPException(400, "naməlum metal")
        limit = max(1, min(limit, 100))
        return await asyncio.to_thread(lambda: {"cards": cards.recent(db, symbol, limit), "summary": cards.summary(db)})

    @app.get("/api/decision")
    async def decision_api():
        """Block 6: per metal the risk gate (with the liquidity view) and the decision per horizon (indication only)."""
        from . import nerve
        now = time.time()
        out = {}
        for sym, d in (engine.decisions or {}).items():
            why = engine.reflex.closed(sym, now)
            if why:      # the reflex acts at once, not at the next minute's recomputation
                d = {**d, "gate": {**d["gate"], "open": False, "reasons": [why] + d["gate"]["reasons"]},
                     "desks": [{**x, "call": "GÖZLƏ", "why": why} if x["call"] != "GÖZLƏ" else x for x in d["desks"]]}
            out[sym] = d
        return {"metals": out, "state": nerve.state(db), "ts": now}

    @app.get("/api/analysts")
    async def analysts(symbol: str = "XAU"):
        """Block 3, the scale: every analyst (method or brain) on each desk with its record and its weight, and the
        brains' own report card (alarm versus hourly)."""
        if symbol not in candles.METALS:
            raise HTTPException(400, "naməlum metal")

        def build():
            now = time.time()
            out = []
            for h in forecast.HORIZONS:
                live = {r["method"]: r for r in judge.stats(db, symbol, h, "live", ttl=600)}
                hist = {r["method"]: r for r in judge.stats(db, symbol, h, "history", ttl=600)}
                w = engine.weights(symbol, h, now)
                rows = []
                for m in forecast.methods_for(h):
                    if m in forecast.BASELINES:
                        continue
                    lv, hv = live.get(m, {}), hist.get(m, {})
                    rows.append({"method": m, "name": forecast.METHOD_NAMES.get(m, m),
                                 "family": forecast.FAMILY_NAMES.get(forecast.FAMILY.get(m, ""), ""),
                                 "live": {k: lv.get(k) for k in ("nh", "hit_rate", "bar", "status")},
                                 "history": {k: hv.get(k) for k in ("nh", "hit_rate", "bar", "status")},
                                 "weight": w.get(m, 0.0)})
                out.append({"horizon": h, "name": forecast.HORIZON_NAMES[h], "rows": rows})
            from . import checker
            return {"symbol": symbol, "desks": out, "brains": diag._slow("brain_score", lambda: brainviews.score(db, now)),
                    "checks": checker.report(db)}
        return await asyncio.to_thread(build)

    @app.get("/results")
    async def results_page():
        return FileResponse(STATIC / "results.html")

    @app.get("/api/results")
    async def results(symbol: str = "XAU", horizon: str = "1h"):
        """The results board: what the system expects now (every horizon, in plain terms), what it said before and
        what happened, the score, and the corridor-versus-price chart. Range = the «Dəyişməz» forecast's 50 % / 80 %
        ranges (the same for every method); direction = the selective consensus (the system's one combined view)."""
        if symbol not in candles.METALS or horizon not in forecast.HORIZONS:
            raise HTTPException(400, "naməlum metal və ya üfüq")
        now = time.time()
        expect = []
        for h in forecast.HORIZONS:
            c = _card(symbol, h)
            rw = next((m for m in c["methods"] if m["method"] == "rw"), None)
            v = c["verdict"]
            off = next((m for m in c["methods"] if m["method"] == v.get("method")), None)
            direction = None
            if v["status"] == "sübut" and off and off["p_up"] != 0.5:
                direction = {"up": off["p_up"] > 0.5, "p": max(off["p_up"], 1 - off["p_up"]),
                             "method": forecast.METHOD_NAMES.get(v["method"]), "condition": v.get("condition")}
            cons = next((m for m in c["methods"] if m["method"] == "consensus"), None)
            expect.append({"horizon": h, "name": forecast.HORIZON_NAMES[h], "issued_t": c["issued_t"],
                           "target_t": rw["target_t"] if rw else None, "price0": rw["price0"] if rw else None,
                           "lo50": rw["lo50"] if rw else None, "hi50": rw["hi50"] if rw else None,
                           "lo80": rw["lo80"] if rw else None, "hi80": rw["hi80"] if rw else None,
                           "direction": direction,
                           "consensus": ({"p": cons["p_up"], "basis": cons["basis"]} if cons else None),
                           "need": c["candles_need"] if not c["methods"] else None})
        # score: the last 7 days of live forecasts per horizon
        score = []
        for h in forecast.HORIZONS:
            r = db.execute("SELECT COUNT(*) n, AVG(in80) c80, AVG(in50) c50 FROM forecasts WHERE symbol=? AND horizon=? "
                           "AND mode='live' AND method='rw' AND price1 IS NOT NULL AND target_t > ?",
                           (symbol, h, now - 7 * 86400)).fetchone()
            d = db.execute("SELECT COUNT(hit) n, AVG(hit) hr FROM forecasts WHERE symbol=? AND horizon=? AND mode='live' "
                           "AND method='consensus' AND hit IS NOT NULL AND target_t > ?",
                           (symbol, h, now - 7 * 86400)).fetchone()
            bar = next((x["bar"] for x in judge.stats(db, symbol, h, "live", ttl=60) if x["method"] == "up"), 0.5)
            score.append({"horizon": h, "name": forecast.HORIZON_NAMES[h], "n": r["n"], "cover80": r["c80"],
                          "cover50": r["c50"], "dir_n": d["n"], "dir_hit": d["hr"], "bar": bar})
        # what it said and what happened (the chosen horizon)
        rows = db.execute(
            "SELECT r.issued_t, r.target_t, r.price0, r.price1, r.lo80, r.hi80, r.lo50, r.hi50, r.in80, r.in50, "
            "c.p_up AS cp, c.hit AS chit, c.basis AS cbasis FROM forecasts r LEFT JOIN forecasts c ON c.symbol=r.symbol "
            "AND c.horizon=r.horizon AND c.mode=r.mode AND c.issued_t=r.issued_t AND c.method='consensus' "
            "WHERE r.symbol=? AND r.horizon=? AND r.mode='live' AND r.method='rw' ORDER BY r.issued_t DESC LIMIT 60",
            (symbol, horizon)).fetchall()
        past = [dict(x) for x in rows]
        tf = forecast.HORIZONS[horizon]
        t0 = min((x["issued_t"] for x in past), default=now - 86400)
        price = [[c["t"], c["c"]] for c in candles.get(db, symbol, tf, limit=200) if c["t"] >= t0 - candles.TF[tf]]
        return {"symbol": symbol, "name": candles.NAMES[symbol], "horizon": horizon, "now": now,
                "price_now": (engine.quotes.get(symbol) or {}).get("price"), "expect": expect, "score": score,
                "past": past, "price": price, "tf_seconds": candles.TF[tf]}

    @app.get("/api/simulate")
    async def simulate_view(symbol: str = "XAU", mode: str = "history"):
        """Success map: every method's shadow trades (stop, target, time, spread) per horizon, in money.
        Heavy: computed off the event loop and kept 15 minutes."""
        from . import simulator
        if symbol not in candles.METALS or mode not in ("live", "history"):
            raise HTTPException(400, "naməlum metal və ya rejim")
        key = ("sim", symbol, mode)
        hit = _series_cache.get(key)
        if hit and time.time() - hit[0] < 900:
            return hit[1]

        def run():
            return {"symbol": symbol, "mode": mode, "method_names": forecast.METHOD_NAMES,
                    "horizons": [{"horizon": h, "name": forecast.HORIZON_NAMES[h],
                                  **simulator.cached(db, symbol, h, mode)} for h in forecast.HORIZONS]}
        out = await asyncio.to_thread(run)
        _series_cache[key] = (time.time(), out)
        return out

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
                price, st, seen = related_quote(code, now) if code not in candles.METALS else \
                    (q["price"] if q else None, engine.status(code, now) if q else "OFFLINE", None)
                row.update({"price": price, "status": st, "seen": seen,
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
        return judge.where_cached(db, symbol, horizon, mode)      # the Judge's shared cache

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
                "health": {k: feeds.health(k) for k in feeds_mod.SOURCE_IDS}}

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

    @app.get("/api/admin/router")
    async def router_state():
        from . import llmrouter
        return llmrouter.view(db)

    @app.post("/api/admin/router")
    async def router_decide(request: Request):
        """The owner's model decisions: try a switched-off model again, approve or reject a proposed replacement."""
        from . import llmrouter
        b = await request.json()
        try:
            out = llmrouter.decide(db, store, str(b.get("action")), str(b.get("provider")), str(b.get("model")))
        except ValueError as e:
            raise HTTPException(400, str(e))
        sec.log("model_" + str(b.get("action")), _ip(request), f"{b.get('provider')} {b.get('model')}")
        return out

    @app.get("/api/admin/ops")
    async def ops_state():
        """The «stop automatic repair» switch and the outside watcher's state (no addresses, no key)."""
        from . import ops
        return {**ops.state(db), "watcher": heart.view()}

    @app.post("/api/admin/ops")
    async def ops_set(request: Request):
        from . import ops
        body = await request.json()
        on = bool(body.get("paused"))
        sec.log("ops_pause" if on else "ops_resume", _ip(request))
        return ops.set_paused(db, on)

    @app.get("/api/admin/2fa")
    async def tfa_status():
        from . import totp
        return totp.status(db, s.session_secret)

    @app.post("/api/admin/2fa/{action}")
    async def tfa_action(action: str, request: Request):
        """2FA for the owner's login: start (a new secret to add to the app), confirm (first code -> on, recovery codes
        shown once), off (needs a current code or a recovery code)."""
        from . import totp
        body = await request.json() if action != "start" else {}
        try:
            if action == "start":
                return totp.start(db, s.session_secret)
            if action == "confirm":
                codes = totp.confirm(db, s.session_secret, str(body.get("code", "")))
                sec.log("2fa_on", _ip(request))
                return {"on": True, "recovery": codes}
            if action == "off":
                totp.turn_off(db, s.session_secret, str(body.get("code", "")))
                sec.log("2fa_off", _ip(request))
                return {"on": False}
        except ValueError as e:
            raise HTTPException(400, str(e))
        raise HTTPException(404, "naməlum əməliyyat")

    @app.get("/api/me")
    async def me(request: Request):
        return {"role": auth.role(request.cookies.get(auth.COOKIE), s.session_secret)}

    db.put("futures:running", "0")       # a download cut by a restart is not «running»

    fut_busy = {"on": False}             # one Databento download at a time: never two paying for the same month

    async def rigor_daily():
        """Once a day: our closes against an independent source (Twelve Data); the code version for the journal."""
        from . import rigor
        db.put("app:commit", _commit() or "?")
        await asyncio.sleep(600)
        while True:
            try:
                day = time.strftime("%Y-%m-%d", time.gmtime())
                if db.get("rigor:audit_day") != day:
                    await rigor.price_audit(db, store.first("twelvedata"))
                    db.put("rigor:audit_day", day)
            except Exception as e:
                log.warning("price audit: %s", e)
            await asyncio.sleep(3600)

    @app.get("/api/admin/registry")
    async def registry_api():
        """The strategy registry, finalists, the experiment journal, the price audit and the hypothesis agent (owner)."""
        from . import ideas, rigor
        def build():
            return {"registry": rigor.registry(db), "finals": rigor.finals(db), "experiments": rigor.experiments(db),
                    "trials": rigor.trials(db), "price_audit": json.loads(db.get("rigor:price_audit") or "null"),
                    "ideas": ideas.view(db), "ideas_next": float(db.get("ideas:last") or 0) + ideas.WEEK}
        return await asyncio.to_thread(build)

    @app.post("/api/admin/registry")
    async def registry_decide(request: Request):
        """The owner approves or rejects a finalist (passed its one-look final test and the independent re-check)."""
        from . import rigor
        b = await request.json()
        try:
            return rigor.decide(db, str(b["kind"]), str(b["name"]), str(b["symbol"]), str(b["horizon"]),
                                bool(b.get("approve")), str(b.get("note", "")))
        except (KeyError, ValueError) as e:
            raise HTTPException(400, str(e)[:200])

    @app.get("/api/admin/paper")
    async def paper_api():
        """Kağız ticarət: the virtual account, open positions, the journal (also rejected proposals) and statistics."""
        from . import paper
        return await asyncio.to_thread(paper.view, db)

    @app.post("/api/admin/paper")
    async def paper_set(request: Request):
        """Emergency stop on/off or the risk settings (owner)."""
        from . import paper
        b = await request.json()
        try:
            if "stop" in b:
                return paper.emergency(db, bool(b["stop"]))
            return paper.set_settings(db, b.get("settings") or {})
        except (TypeError, ValueError) as e:
            raise HTTPException(400, str(e)[:200])

    async def futures_daily():
        """Owner-approved daily top-up of the COMEX bars (after 06:00 UTC, once a day), then the volume rules run on
        the new candles. Never two downloads at once; the monthly ceiling is checked inside."""
        from . import futures, rules
        await asyncio.sleep(300)
        while True:
            try:
                day = time.strftime("%Y-%m-%d", time.gmtime())
                key = store.first("databento")
                if time.gmtime().tm_hour >= 6 and db.get("futures:daily_day") != day and key and not fut_busy["on"]:
                    fut_busy["on"] = True
                    try:
                        res = await futures.daily_refresh(db, key)
                    finally:
                        fut_busy["on"] = False
                    db.put("futures:daily_try", json.dumps({"ts": time.time(), **res}, ensure_ascii=False))
                    if res.get("ok"):
                        db.put("futures:daily_day", day)
                        await asyncio.to_thread(rules.run_futures_volume, db)
                    else:
                        log.warning("futures daily: %s", res.get("msg") or res.get("errors"))
            except Exception as e:
                log.warning("futures daily: %s", e)
            await asyncio.sleep(1800)

    async def futures_keeper():
        """An approved download that stopped (a restart, a timeout) is resumed every 30 minutes until it is complete."""
        while True:
            await futures_resume()
            last = json.loads(db.get("futures:last") or "null")
            if last and last.get("ok"):
                return
            await asyncio.sleep(1800)

    async def futures_resume():
        """A download the owner approved but a restart cut off goes on by itself (stored months are skipped, so
        nothing is paid twice; the approved limit still applies)."""
        from . import futures
        try:
            appr = json.loads(db.get("futures:approved") or "null")
            last = json.loads(db.get("futures:last") or "null")
            key = store.first("databento")
            if last and last.get("ok"):
                # data complete: recompute the tests if they were made by an older version (e.g. before VWAP)
                if '"vwap"' not in (db.get("futstudy:last") or ""):
                    from . import futstudy
                    await asyncio.sleep(90)
                    try:          # a failed recompute never touches the finished download's record
                        await asyncio.to_thread(futstudy.run_and_store, db)
                    except Exception as e:
                        log.warning("futures study: %s", e)
                return
            if not appr or not key:
                return
            await asyncio.sleep(60)
            if fut_busy["on"]:
                return
            fut_busy["on"] = True          # set before any await: nothing else can start in between
            db.put("futures:running", "1")
            try:
                res = await futures.download(db, key, float(appr["limit_usd"]), hub.report)
                if not res.get("ok"):
                    db.put("futures:last", json.dumps(res, ensure_ascii=False))
            finally:
                fut_busy["on"] = False
                db.put("futures:running", "0")
        except Exception as e:
            db.put("futures:last", json.dumps({"ok": False, "msg": f"{type(e).__name__}: {str(e)[:200]}"}))
    app.state.futures_resume = futures_resume
    app.state.futures_keeper = futures_keeper
    app.state.futures_daily = futures_daily
    app.state.rigor_daily = rigor_daily

    @app.get("/api/admin/futures/quote")
    async def futures_quote():
        """Stage 2: what the Databento futures history would cost (a free metadata call; nothing is bought)."""
        from . import futures
        key = store.first("databento")
        if not key:
            raise HTTPException(400, "Databento açarı saxlanmayıb")
        return await futures.quote_saved(db, key)

    @app.post("/api/admin/futures/buy")
    async def futures_buy(body: dict):
        """Stage 2: the owner confirmed the shown price. Runs in the background; refuses above the confirmed price and
        above the free credit (125 $) — a larger purchase needs a new decision."""
        from . import futures
        key = store.first("databento")
        if not key:
            raise HTTPException(400, "Databento açarı saxlanmayıb")
        try:
            limit = min(float(body.get("limit_usd")), 125.0)
        except (TypeError, ValueError):
            raise HTTPException(400, "yanlış məbləğ")
        import math
        if not math.isfinite(limit) or limit < 0:
            raise HTTPException(400, "yanlış məbləğ")
        if fut_busy["on"]:
            return {"msg": "yükləmə artıq gedir"}
        fut_busy["on"] = True              # set before any await: a second press cannot start a second download

        db.put("futures:approved", json.dumps({"limit_usd": limit, "ts": time.time()}))   # the owner's decision

        async def job():
            db.put("futures:running", "1")
            try:
                res = await futures.download(db, key, limit, hub.report)
                if not res.get("ok"):
                    db.put("futures:last", json.dumps(res, ensure_ascii=False))
            except Exception as e:
                db.put("futures:last", json.dumps({"ok": False, "msg": f"{type(e).__name__}: {str(e)[:200]}"}))
            finally:
                fut_busy["on"] = False
                db.put("futures:running", "0")
        asyncio.get_running_loop().create_task(job())
        return {"msg": f"Təsdiq qəbul olundu: ən çox {limit:.2f} $. Yükləmə başladı; Agentlər səhifəsində «Tarixçə» "
                       "agentində görünür, bitəndə nəticə buradadır və Claude-a hesabat gedir."}

    @app.post("/api/admin/history")
    async def history():
        return await engine.backfill(force=True)

    return app
