"""Texniki analizin qalan növləri (owner 2026-11-25: «all 12 kinds, complete, inside our nervous system»).

Each detector reads candle i using candles 0..i only (no look-ahead) and returns rules as (id, direction, note), like
rules.detect. Every rule is in the Bilik kitabı (playbook.py) with how / signal / void / source, the Judge measures
each one on its own (rules.records: next candle and stop + target), and the Chartist gets the firings and records.

Subjective schools are reduced to one objective, testable reading each (written down before any result was seen):
- Elliott: two checkable moments only — the start of wave 3 and the end of a 5-wave impulse (with the three hard
  rules: wave 2 never beyond the start, wave 3 never the shortest, wave 4 never into wave 1).
- Wyckoff: spring / upthrust at the edge of a sideways range.
- «Smart money»: liquidity sweep (a stop hunt beyond a swing that closes back), order block (the last opposite candle
  before a displacement, on the first return), break of structure / change of character.
Volume: the broker gives no exchange volume, so «tick volume» (how many times the price changed inside the candle, the
volume every CFD platform shows) is counted from 2026-11-25 on; volume rules stay silent until enough of it exists."""
from __future__ import annotations


def zigzag(cs: list[dict], highs: list[int], lows: list[int]) -> list[tuple[int, str, float]]:
    """Confirmed swings in time order, alternating high/low (of two in a row, the more extreme is kept)."""
    pts = sorted([(j, "H", cs[j]["h"]) for j in highs] + [(j, "L", cs[j]["l"]) for j in lows])
    out: list[tuple[int, str, float]] = []
    for p in pts:
        if out and out[-1][1] == p[1]:
            if (p[1] == "H" and p[2] >= out[-1][2]) or (p[1] == "L" and p[2] <= out[-1][2]):
                out[-1] = p
            continue
        out.append(p)
    return out


def _line(a: tuple[int, float], b: tuple[int, float], x: int) -> float:
    return a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0])


def stochastic(cs: list[dict], n: int = 14, d: int = 3) -> tuple[list, list]:
    k: list = [None] * len(cs)
    for i in range(n - 1, len(cs)):
        hh = max(x["h"] for x in cs[i - n + 1:i + 1])
        ll = min(x["l"] for x in cs[i - n + 1:i + 1])
        k[i] = 50.0 if hh == ll else (cs[i]["c"] - ll) / (hh - ll) * 100
    dd: list = [None] * len(cs)
    for i in range(len(cs)):
        w = k[max(0, i - d + 1):i + 1]
        if len(w) == d and None not in w:
            dd[i] = sum(w) / d
    return k, dd


def obv(cs: list[dict]) -> list:
    out: list = [None] * len(cs)
    acc = 0.0
    for i in range(1, len(cs)):
        v = cs[i].get("v")
        if v is None or cs[i - 1].get("v") is None:
            acc = 0.0
            continue
        acc += v if cs[i]["c"] > cs[i - 1]["c"] else -v if cs[i]["c"] < cs[i - 1]["c"] else 0
        out[i] = acc
    return out


def _period_key(t: int, tf: str) -> int:
    """Pivots come from the previous trading day (1 h, 4 h) or the previous week (1 d)."""
    if tf == "1d":
        return (t + 7200 - 345600) // 604800
    return (t + 7200) // 86400


def more(ind, i: int, highs: list[int], lows: list[int], tf: str) -> list[tuple[str, int, str]]:
    cs, out = ind.cs, []
    c, atr, tr = cs[i], ind.atr[i], ind.trend(i)
    bull, bear = c["c"] > c["o"], c["c"] < c["o"]
    prev = cs[i - 1]
    zz = zigzag(cs, [j for j in highs if j >= i - 100], [j for j in lows if j >= i - 100])
    H = [(j, p) for j, k, p in zz if k == "H"]
    L = [(j, p) for j, k, p in zz if k == "L"]

    # --- 1. Klassik: trend xətti (through the last two confirmed lows / highs) ---
    if len(L) >= 2 and L[-1][1] > L[-2][1] and i - L[-1][0] >= 3:
        ln, lp = _line(L[-2], L[-1], i), _line(L[-2], L[-1], i - 1)
        if c["l"] <= ln + 0.2 * atr and c["c"] > ln and bull and tr >= 0:
            out.append(("TA-TL-1", 1, "yüksələn trend xəttindən sıçrayış"))
        elif c["c"] < ln - 0.2 * atr and prev["c"] >= lp:
            out.append(("TA-TL-1", -1, "yüksələn trend xətti aşağı qırıldı"))
    if len(H) >= 2 and H[-1][1] < H[-2][1] and i - H[-1][0] >= 3:
        ln, lp = _line(H[-2], H[-1], i), _line(H[-2], H[-1], i - 1)
        if c["h"] >= ln - 0.2 * atr and c["c"] < ln and bear and tr <= 0:
            out.append(("TA-TL-1", -1, "enən trend xəttindən geri itələndi"))
        elif c["c"] > ln + 0.2 * atr and prev["c"] <= lp:
            out.append(("TA-TL-1", 1, "enən trend xətti yuxarı qırıldı"))

    # --- 2. Fiqurlar ---
    def crossed_down(level: float) -> bool:
        return c["c"] < level <= prev["c"]

    def crossed_up(level: float) -> bool:
        return c["c"] > level >= prev["c"]
    # double top / bottom (two equal swings, the neckline between them breaks)
    if len(H) >= 2 and H[-1][0] >= i - 40:
        (a, pa), (b, pb) = H[-2], H[-1]
        if b - a >= 5 and abs(pa - pb) <= 0.5 * atr:
            neck = min(x["l"] for x in cs[a:b + 1])
            if max(pa, pb) - neck >= 2 * atr and crossed_down(neck):
                out.append(("TA-PAT-1", -1, "ikiqat zirvə: boyun xətti qırıldı"))
    if len(L) >= 2 and L[-1][0] >= i - 40:
        (a, pa), (b, pb) = L[-2], L[-1]
        if b - a >= 5 and abs(pa - pb) <= 0.5 * atr:
            neck = max(x["h"] for x in cs[a:b + 1])
            if neck - min(pa, pb) >= 2 * atr and crossed_up(neck):
                out.append(("TA-PAT-1", 1, "ikiqat dib: boyun xətti qırıldı"))
    # head and shoulders / inverse
    if len(H) >= 3 and H[-1][0] >= i - 40:
        (a, pa), (b, pb), (d, pd) = H[-3:]
        if pb - max(pa, pd) >= 0.5 * atr and abs(pa - pd) <= 1.0 * atr:
            neck = min(min(x["l"] for x in cs[a:b + 1]), min(x["l"] for x in cs[b:d + 1]))
            if crossed_down(neck):
                out.append(("TA-PAT-HS", -1, "baş-çiyinlər: boyun xətti qırıldı"))
    if len(L) >= 3 and L[-1][0] >= i - 40:
        (a, pa), (b, pb), (d, pd) = L[-3:]
        if min(pa, pd) - pb >= 0.5 * atr and abs(pa - pd) <= 1.0 * atr:
            neck = max(max(x["h"] for x in cs[a:b + 1]), max(x["h"] for x in cs[b:d + 1]))
            if crossed_up(neck):
                out.append(("TA-PAT-HS", 1, "tərs baş-çiyinlər: boyun xətti qırıldı"))
    # triangle and wedge (two highs and two lows inside the last 60 candles)
    if len(H) >= 2 and len(L) >= 2 and min(H[-2][0], L[-2][0]) >= i - 60:
        hi_now, lo_now = _line(H[-2], H[-1], i), _line(L[-2], L[-1], i)
        hi_prev, lo_prev = _line(H[-2], H[-1], i - 1), _line(L[-2], L[-1], i - 1)
        sh = (H[-1][1] - H[-2][1]) / (H[-1][0] - H[-2][0])
        sl = (L[-1][1] - L[-2][1]) / (L[-1][0] - L[-2][0])
        if hi_now > lo_now:
            if sh < 0 < sl:                                     # converging: triangle
                if crossed_up(hi_now) or (c["c"] > hi_now and prev["c"] <= hi_prev):
                    out.append(("TA-PAT-TRI", 1, "üçbucaq yuxarı qırıldı"))
                elif crossed_down(lo_now) or (c["c"] < lo_now and prev["c"] >= lo_prev):
                    out.append(("TA-PAT-TRI", -1, "üçbucaq aşağı qırıldı"))
            elif sh > 0 and sl > 0 and sl > sh and c["c"] < lo_now and prev["c"] >= lo_prev:
                out.append(("TA-PAT-WEDGE", -1, "yüksələn paz aşağı qırıldı"))
            elif sh < 0 and sl < 0 and sh < sl and c["c"] > hi_now and prev["c"] <= hi_prev:
                out.append(("TA-PAT-WEDGE", 1, "enən paz yuxarı qırıldı"))
    # flag: a strong impulse, a tight pause, a break in the impulse's direction
    for k in range(i - 16, i - 4):
        if k < 6:
            continue
        move = cs[k]["c"] - cs[k - 6]["c"]
        if abs(move) < 3 * atr:
            continue
        pause = cs[k + 1:i]
        if not 4 <= len(pause) <= 15:
            continue
        ph, pl = max(x["h"] for x in pause), min(x["l"] for x in pause)
        if ph - pl > 0.5 * abs(move):
            continue
        if move > 0 and cs[k]["c"] - pl < 0.5 * move and c["c"] > ph >= prev["c"]:
            out.append(("TA-PAT-FLAG", 1, "bayraq: güclü qalxışdan sonra fasilə yuxarı qırıldı"))
            break
        if move < 0 and ph - cs[k]["c"] < 0.5 * -move and c["c"] < pl <= prev["c"]:
            out.append(("TA-PAT-FLAG", -1, "bayraq: güclü düşüşdən sonra fasilə aşağı qırıldı"))
            break

    # --- 5. Osilyator: Stoxastik ---
    k1, d1, k0, d0 = ind.sk[i], ind.sd[i], ind.sk[i - 1], ind.sd[i - 1]
    if None not in (k1, d1, k0, d0):
        if k0 <= d0 and k1 > d1 and max(k1, d1) < 25:
            out.append(("TA-STOCH-1", 1, "Stoxastik 20-dən aşağıda yuxarı kəsdi"))
        elif k0 >= d0 and k1 < d1 and min(k1, d1) > 75:
            out.append(("TA-STOCH-1", -1, "Stoxastik 80-dən yuxarıda aşağı kəsdi"))

    # --- 1b. Pivot nöqtələri (previous day / week) ---
    key = _period_key(c["t"], tf)
    j = i
    while j > 0 and _period_key(cs[j]["t"], tf) == key:
        j -= 1
    pk = _period_key(cs[j]["t"], tf)
    span = []
    while j >= 0 and _period_key(cs[j]["t"], tf) == pk and len(span) < 60:
        span.append(cs[j])
        j -= 1
    if span:
        ph, pl, pc = max(x["h"] for x in span), min(x["l"] for x in span), span[0]["c"]
        p = (ph + pl + pc) / 3
        r1, s1 = 2 * p - pl, 2 * p - ph
        if c["l"] <= s1 + 0.2 * atr and c["c"] > s1 and bull:
            out.append(("TA-PIVOT-1", 1, "S1 pivot dəstəyindən dönüş"))
        elif c["h"] >= r1 - 0.2 * atr and c["c"] < r1 and bear:
            out.append(("TA-PIVOT-1", -1, "R1 pivot müqavimətindən dönüş"))

    # --- 8. Fibonacci uzanması: the move reaches 127,2-161,8 % of the previous wave and turns ---
    if len(zz) >= 3:
        (j0, k0_, p0), (j1, _, p1), (j2, _, p2) = zz[-3:]
        w = abs(p1 - p0)
        if k0_ == "L" and p2 > p0 and w >= 3 * atr:            # up wave, pullback; now the next leg up
            lo_t, hi_t = p2 + 1.272 * w, p2 + 1.618 * w
            if c["h"] >= lo_t and c["c"] <= hi_t and bear:
                out.append(("TA-FIB-EXT", -1, "161,8 % uzanma zonasında satıcı şamı"))
        elif k0_ == "H" and p2 < p0 and w >= 3 * atr:
            hi_t, lo_t = p2 - 1.272 * w, p2 - 1.618 * w
            if c["l"] <= hi_t and c["c"] >= lo_t and bull:
                out.append(("TA-FIB-EXT", 1, "161,8 % uzanma zonasında alıcı şamı"))

    # --- 9. Nəzəriyyələr ---
    # Dow: the swing structure (higher highs and higher lows / lower and lower)
    if len(H) >= 2 and len(L) >= 2:
        if H[-1][1] > H[-2][1] and L[-1][1] > L[-2][1]:
            out.append(("TH-DOW-1", 1, "yüksələn quruluş: yüksək zirvə və yüksək dib"))
        elif H[-1][1] < H[-2][1] and L[-1][1] < L[-2][1]:
            out.append(("TH-DOW-1", -1, "enən quruluş: alçaq zirvə və alçaq dib"))
    # Elliott
    if len(zz) >= 3:
        (a, ka, pa), (b, _, pb), (d, _, pd) = zz[-3:]
        if ka == "L" and pb > pa and pa < pd < pb:
            ret = (pb - pd) / (pb - pa)
            if 0.382 <= ret <= 0.786 and crossed_up(pb):
                out.append(("TH-ELL-1", 1, f"Elliott: 2-ci dalğa {ret * 100:.0f} %, 3-cü dalğa başladı"))
        elif ka == "H" and pb < pa and pb < pd < pa:
            ret = (pd - pb) / (pa - pb)
            if 0.382 <= ret <= 0.786 and crossed_down(pb):
                out.append(("TH-ELL-1", -1, f"Elliott: 2-ci dalğa {ret * 100:.0f} %, aşağı 3-cü dalğa başladı"))
    if len(zz) >= 5:
        (_, k0_, p0), (_, _, p1), (_, _, p2), (_, _, p3), (_, _, p4) = zz[-5:]
        if k0_ == "L" and p0 < p2 < p1 < p4 < p3:                   # rules: 2 above start, 4 above 1
            w1, w3 = p1 - p0, p3 - p2
            if w3 >= w1 * 0.618 and c["h"] > p3 and bear and c["c"] < p3:
                out.append(("TH-ELL-2", -1, "Elliott: 5 dalğa tamamlandı, düzəliş gözlənir"))
        elif k0_ == "H" and p0 > p2 > p1 > p4 > p3:
            w1, w3 = p0 - p1, p2 - p3
            if w3 >= w1 * 0.618 and c["l"] < p3 and bull and c["c"] > p3:
                out.append(("TH-ELL-2", 1, "Elliott: aşağı 5 dalğa tamamlandı, düzəliş gözlənir"))
    # Wyckoff: spring / upthrust at the edge of a sideways range
    rng = cs[i - 40:i]
    rh, rl = max(x["h"] for x in rng), min(x["l"] for x in rng)
    if tr == 0 and rh - rl <= 8 * atr:
        if c["l"] < rl and c["c"] > rl and bull:
            out.append(("TH-WYC-1", 1, "Wyckoff «spring»: dibin altı yoxlandı, qiymət aralığa qayıtdı"))
        elif c["h"] > rh and c["c"] < rh and bear:
            out.append(("TH-WYC-1", -1, "Wyckoff «upthrust»: zirvənin üstü yoxlandı, qiymət aralığa qayıtdı"))

    # --- 10. Price action / «smart money» ---
    rngc = (c["h"] - c["l"]) or 1e-12
    if H and H[-1][0] >= i - 50 and c["h"] > H[-1][1] and c["c"] < H[-1][1] \
            and (c["h"] - max(c["o"], c["c"])) / rngc >= 0.5:
        out.append(("PA-LIQ-1", -1, "likvidlik toplandı: zirvənin üstündəki stoplar götürüldü, qiymət geri qayıtdı"))
    elif L and L[-1][0] >= i - 50 and c["l"] < L[-1][1] and c["c"] > L[-1][1] \
            and (min(c["o"], c["c"]) - c["l"]) / rngc >= 0.5:
        out.append(("PA-LIQ-1", 1, "likvidlik toplandı: dibin altındakı stoplar götürüldü, qiymət geri qayıtdı"))
    if H and crossed_up(H[-1][1]):
        out.append(("PA-BOS-1", 1, "quruluş qırıldı yuxarı" + (" (xarakter dəyişdi)" if len(H) >= 2 and H[-1][1] < H[-2][1]
                                                               else "")))
    elif L and crossed_down(L[-1][1]):
        out.append(("PA-BOS-1", -1, "quruluş qırıldı aşağı" + (" (xarakter dəyişdi)" if len(L) >= 2 and L[-1][1] > L[-2][1]
                                                                else "")))
    # order block: the last opposite candle before a displacement (>= 2 ATR in 3 candles breaking the last 10 extremes)
    for k in range(i - 4, i - 30, -1):
        if k < 15:
            break
        up = cs[k + 2]["c"] - cs[k - 1]["c"]
        if abs(up) < 2 * atr:
            continue
        before = cs[k - 11:k - 1]
        if up > 0 and cs[k + 2]["c"] > max(x["h"] for x in before):
            ob = next((cs[j] for j in range(k - 1, k - 6, -1) if cs[j]["c"] < cs[j]["o"]), None)
            if ob and all(x["l"] > ob["h"] for x in cs[k + 3:i]) and c["l"] <= ob["h"] and c["c"] >= ob["l"] and bull:
                out.append(("PA-OB-1", 1, "alıcı «order block» zonasına ilk qayıdış"))
            break
        if up < 0 and cs[k + 2]["c"] < min(x["l"] for x in before):
            ob = next((cs[j] for j in range(k - 1, k - 6, -1) if cs[j]["c"] > cs[j]["o"]), None)
            if ob and all(x["h"] < ob["l"] for x in cs[k + 3:i]) and c["h"] >= ob["l"] and c["c"] <= ob["h"] and bear:
                out.append(("PA-OB-1", -1, "satıcı «order block» zonasına ilk qayıdış"))
            break

    # --- 7. Həcm (tick volume; silent until 100 candles have it) ---
    win = cs[i - 100:i + 1]
    if all(x.get("v") for x in win):
        vs = [x["v"] for x in win]
        avg = sum(vs[:-1]) / (len(vs) - 1)
        if c["v"] >= 2 * avg and c["h"] - c["l"] > atr:
            prev20 = cs[i - 20:i]
            if c["c"] > max(x["h"] for x in prev20):
                out.append(("VOL-SPIKE-1", 1, "böyük həcmlə zirvə qırıldı (böyük oyunçu)"))
            elif c["c"] < min(x["l"] for x in prev20):
                out.append(("VOL-SPIKE-1", -1, "böyük həcmlə dib qırıldı (böyük oyunçu)"))
        ob_ = ind.obv
        if ob_[i] is not None and ob_[i - 20] is not None:
            w20 = cs[i - 20:i]
            o20 = [x for x in ob_[i - 20:i] if x is not None]
            if o20 and c["c"] > max(x["h"] for x in w20) and ob_[i] < max(o20):
                out.append(("VOL-OBV-1", -1, "qiymət yeni zirvədə, həcm (OBV) təsdiqləmir"))
            elif o20 and c["c"] < min(x["l"] for x in w20) and ob_[i] > min(o20):
                out.append(("VOL-OBV-1", 1, "qiymət yeni dibdə, həcm (OBV) təsdiqləmir"))
        nv = 24 if tf == "1h" else 6 if tf == "4h" else 5
        sv = cs[i - nv + 1:i + 1]
        tv = sum(x["v"] for x in sv)
        if tv:
            vwap = sum((x["h"] + x["l"] + x["c"]) / 3 * x["v"] for x in sv) / tv
            if crossed_up(vwap) and c["v"] > avg:
                out.append(("VOL-VWAP-1", 1, "qiymət həcmlə VWAP-ı yuxarı keçdi"))
            elif crossed_down(vwap) and c["v"] > avg:
                out.append(("VOL-VWAP-1", -1, "qiymət həcmlə VWAP-ı aşağı keçdi"))
        # volume profile: the price with the most volume (POC) of the last 100 candles acts as a magnet / level
        step = max(atr / 4, 1e-9)
        bins: dict[int, float] = {}
        for x in win[:-1]:
            b = int(((x["h"] + x["l"] + x["c"]) / 3) // step)
            bins[b] = bins.get(b, 0.0) + x["v"]
        poc = (max(bins, key=bins.get) + 0.5) * step
        if c["l"] <= poc <= c["h"]:
            if prev["c"] > poc and c["c"] > poc and bull:
                out.append(("VOL-POC-1", 1, "həcm profilinin mərkəzi (POC) dəstək oldu"))
            elif prev["c"] < poc and c["c"] < poc and bear:
                out.append(("VOL-POC-1", -1, "həcm profilinin mərkəzi (POC) müqavimət oldu"))
    return out
