"""Fiziki ehtiyat (owner 2026-11-25, from the Radar Gold design: «the physical metal the owner holds, apart from any
forecast or trade»).

For each lot: gross grams and fineness (assay, e.g. 0.585, 0.750, 0.916, 0.999) give the pure metal; at the live price
(the same feed as the panel, never a model) its value, what a refiner would pay after its fee and melt loss, the
result against the purchase cost, and how much the value moves per 1 $ and per 1 % of the price. Sales are journalled
separately (actual assay and payment), so the realised result is never mixed with the paper one. Owner only; the data
stays in the server's database.
Pure metal: net g = gross g x assay; net oz = net g / 31.1034768; value = net oz x price per troy ounce."""
from __future__ import annotations

import csv
import io
import time

from .db import DB

OZ = 31.1034768
SCHEMA = """
CREATE TABLE IF NOT EXISTS stock_lots (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, metal TEXT NOT NULL,
  grams REAL NOT NULL, assay REAL NOT NULL, cost_usd REAL NOT NULL, bought TEXT, note TEXT, created REAL NOT NULL,
  closed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS stock_sales (id INTEGER PRIMARY KEY AUTOINCREMENT, lot_id INTEGER NOT NULL, ts REAL NOT NULL,
  grams REAL NOT NULL, assay REAL NOT NULL, received_usd REAL NOT NULL, note TEXT);
"""
METALS = ("XAU", "XAG", "XPT", "XPD")
NAMES = {"XAU": "Qızıl", "XAG": "Gümüş", "XPT": "Platin", "XPD": "Palladium"}


def ensure(db: DB) -> None:
    db.script(SCHEMA)


def settings(db: DB) -> dict:
    return {"refiner_fee_pct": float(db.get("stock:refiner_fee_pct") or 1.0),
            "melt_loss_pct": float(db.get("stock:melt_loss_pct") or 0.5)}


def set_settings(db: DB, fee: float, loss: float) -> dict:
    if not (0 <= fee < 20 and 0 <= loss < 20):
        raise ValueError("faiz 0 ilə 20 arasında olmalıdır")
    db.put("stock:refiner_fee_pct", str(fee))
    db.put("stock:melt_loss_pct", str(loss))
    return settings(db)


def _check(metal: str, grams: float, assay: float, cost: float) -> None:
    if metal not in METALS:
        raise ValueError("metal XAU, XAG, XPT və ya XPD olmalıdır")
    if not (0 < grams < 10_000_000):
        raise ValueError("qram müsbət olmalıdır")
    if not (0 < assay <= 1):
        raise ValueError("əyar 0 ilə 1 arasında olmalıdır (məsələn 0.585, 0.916, 0.999)")
    if cost < 0:
        raise ValueError("alış dəyəri mənfi ola bilməz")


def add_lot(db: DB, name: str, metal: str, grams: float, assay: float, cost: float, bought: str = "", note: str = "") -> int:
    ensure(db)
    if assay > 1:                    # 585, 916, 999 written as karat-thousandths
        assay = assay / 1000
    _check(metal, grams, assay, cost)
    db.execute("INSERT INTO stock_lots(name, metal, grams, assay, cost_usd, bought, note, created) VALUES(?,?,?,?,?,?,?,?)",
               ((name or "lot")[:80], metal, grams, assay, cost, (bought or "")[:20], (note or "")[:200], time.time()))
    return db.execute("SELECT MAX(id) i FROM stock_lots").fetchone()["i"]


def import_csv(db: DB, text: str) -> dict:
    """name,metal,grams,assay,cost_usd,bought,note — a header line is allowed; bad lines are reported, not guessed."""
    ok, bad = 0, []
    for i, row in enumerate(csv.reader(io.StringIO(text)), 1):
        if not row or (i == 1 and row[0].strip().lower() in ("name", "ad")):
            continue
        try:
            add_lot(db, row[0].strip(), row[1].strip().upper(), float(row[2]), float(row[3]), float(row[4]),
                    row[5].strip() if len(row) > 5 else "", row[6].strip() if len(row) > 6 else "")
            ok += 1
        except (ValueError, IndexError) as e:
            bad.append(f"sətir {i}: {e}")
    return {"added": ok, "errors": bad[:20]}


def sell(db: DB, lot_id: int, grams: float, assay: float, received: float, note: str = "") -> dict:
    """A closed deal: grams sold from a lot at the assay the buyer measured and the money actually received."""
    ensure(db)
    lot = db.execute("SELECT * FROM stock_lots WHERE id=? AND closed=0", (lot_id,)).fetchone()
    if not lot:
        raise ValueError("açıq lot tapılmadı")
    if assay > 1:
        assay = assay / 1000
    sold = db.execute("SELECT COALESCE(SUM(grams), 0) g FROM stock_sales WHERE lot_id=?", (lot_id,)).fetchone()["g"]
    left = lot["grams"] - sold
    if not (0 < grams <= left + 1e-9) or not (0 < assay <= 1) or received < 0:
        raise ValueError(f"satış düzgün deyil (lotda {left:.2f} q qalıb)")
    db.execute("INSERT INTO stock_sales(lot_id, ts, grams, assay, received_usd, note) VALUES(?,?,?,?,?,?)",
               (lot_id, time.time(), grams, assay, received, (note or "")[:200]))
    if grams >= left - 1e-9:
        db.execute("UPDATE stock_lots SET closed=1 WHERE id=?", (lot_id,))
    return {"ok": True}


def delete_lot(db: DB, lot_id: int) -> None:
    """Only a lot with no sales may be deleted (a mistaken entry); sold lots stay in the journal."""
    ensure(db)
    if db.execute("SELECT 1 FROM stock_sales WHERE lot_id=?", (lot_id,)).fetchone():
        raise ValueError("satışı olan lot silinmir")
    db.execute("DELETE FROM stock_lots WHERE id=?", (lot_id,))


def _price(db: DB, metal: str) -> tuple[float | None, float | None]:
    r = db.execute("SELECT t, c FROM candles WHERE symbol=? AND tf='1m' ORDER BY t DESC LIMIT 1", (metal,)).fetchone()
    return (r["c"], r["t"]) if r else (None, None)


def view(db: DB) -> dict:
    """Every open lot valued now, totals per metal, the price sensitivity and the sales journal."""
    ensure(db)
    cfg = settings(db)
    keep = 1 - (cfg["refiner_fee_pct"] + cfg["melt_loss_pct"]) / 100
    prices = {m: _price(db, m) for m in METALS}
    lots, totals = [], {}
    for r in db.execute("SELECT * FROM stock_lots WHERE closed=0 ORDER BY id").fetchall():
        sold = db.execute("SELECT COALESCE(SUM(grams), 0) g FROM stock_sales WHERE lot_id=?", (r["id"],)).fetchone()["g"]
        grams = r["grams"] - sold
        cost = r["cost_usd"] * (grams / r["grams"]) if r["grams"] else 0.0
        net_g = grams * r["assay"]
        net_oz = net_g / OZ
        px = prices[r["metal"]][0]
        spot = net_oz * px if px else None
        refiner = spot * keep if spot is not None else None
        x = {"id": r["id"], "name": r["name"], "metal": r["metal"], "grams": round(grams, 3), "assay": r["assay"],
             "net_g": round(net_g, 3), "net_oz": round(net_oz, 4), "cost": round(cost, 2), "bought": r["bought"],
             "note": r["note"], "spot_value": None if spot is None else round(spot, 2),
             "refiner_value": None if refiner is None else round(refiner, 2),
             "result": None if refiner is None else round(refiner - cost, 2),
             "per_usd": round(net_oz * keep, 4), "per_pct": None if refiner is None else round(refiner / 100, 2)}
        lots.append(x)
        t = totals.setdefault(r["metal"], {"metal": r["metal"], "name": NAMES[r["metal"]], "net_g": 0.0, "net_oz": 0.0,
                                           "cost": 0.0, "spot_value": 0.0, "refiner_value": 0.0, "per_usd": 0.0,
                                           "price": px, "price_t": prices[r["metal"]][1]})
        for k in ("net_g", "net_oz", "cost", "per_usd"):
            t[k] += x[k]
        if spot is not None:
            t["spot_value"] += x["spot_value"]
            t["refiner_value"] += x["refiner_value"]
    for t in totals.values():
        t["result"] = round(t["refiner_value"] - t["cost"], 2) if t["price"] else None
        t["scenarios"] = {f"{s:+d}%": round(t["refiner_value"] * s / 100, 2) for s in (-5, -1, 1, 5)} if t["price"] else {}
        for k in ("net_g", "net_oz", "cost", "spot_value", "refiner_value", "per_usd"):
            t[k] = round(t[k], 4 if k in ("net_oz", "per_usd") else 2)
    sales = []
    for s in db.execute("SELECT s.*, l.name, l.metal, l.grams lot_grams, l.cost_usd FROM stock_sales s "
                        "JOIN stock_lots l ON l.id=s.lot_id ORDER BY s.ts DESC LIMIT 100").fetchall():
        cost = s["cost_usd"] * s["grams"] / s["lot_grams"] if s["lot_grams"] else 0.0
        sales.append({"ts": s["ts"], "lot": s["name"], "metal": s["metal"], "grams": s["grams"], "assay": s["assay"],
                      "net_oz": round(s["grams"] * s["assay"] / OZ, 4), "received": s["received_usd"],
                      "cost": round(cost, 2), "result": round(s["received_usd"] - cost, 2), "note": s["note"]})
    return {"settings": cfg, "lots": lots, "totals": list(totals.values()), "sales": sales,
            "realised": round(sum(x["result"] for x in sales), 2)}
