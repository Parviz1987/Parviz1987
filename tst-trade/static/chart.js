/* Candlestick chart on a canvas, no library, with display-only technical analysis:
   EMA 20/50/200, Bollinger (20, 2), Fibonacci of the visible swing, classic daily pivots, round numbers,
   support / resistance from swing points, and a lower panel with RSI(14) or MACD(12, 26, 9).
   drawChart(canvas, tip, candles, overlay, tf, opts) — candles may hold extra history before the visible part
   (opts.show = how many to show) so the long averages start correctly. window.TA exposes the maths. */
(function () {
  function css(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }
  function fmt(x) { return x >= 100 ? x.toFixed(2) : x.toFixed(3); }
  // Times on the chart in New York time (the owner's city); daily and weekly candles keep their trading date.
  function tlabel(t, tf) {
    const d = new Date(t * 1000);
    const p = (n) => String(n).padStart(2, "0");
    if (tf === "1d" || tf === "1w") return p(d.getUTCDate()) + "." + p(d.getUTCMonth() + 1);
    return d.toLocaleTimeString("en-GB", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" });
  }

  // ---------- indicators ----------
  function ema(xs, n) {
    const k = 2 / (n + 1), out = new Array(xs.length).fill(null);
    if (xs.length < n) return out;
    let e = xs.slice(0, n).reduce((a, b) => a + b, 0) / n;
    out[n - 1] = e;
    for (let i = n; i < xs.length; i++) { e = xs[i] * k + e * (1 - k); out[i] = e; }
    return out;
  }
  function sma(xs, n) {
    const out = new Array(xs.length).fill(null);
    let s = 0;
    for (let i = 0; i < xs.length; i++) { s += xs[i]; if (i >= n) s -= xs[i - n]; if (i >= n - 1) out[i] = s / n; }
    return out;
  }
  function boll(xs, n = 20, k = 2) {
    const m = sma(xs, n), up = [], lo = [];
    for (let i = 0; i < xs.length; i++) {
      if (m[i] == null) { up.push(null); lo.push(null); continue; }
      let v = 0; for (let j = i - n + 1; j <= i; j++) v += (xs[j] - m[i]) ** 2;
      const sd = Math.sqrt(v / n); up.push(m[i] + k * sd); lo.push(m[i] - k * sd);
    }
    return { mid: m, up, lo };
  }
  function rsi(xs, n = 14) {
    const out = new Array(xs.length).fill(null);
    if (xs.length <= n) return out;
    let g = 0, l = 0;
    for (let i = 1; i <= n; i++) { const d = xs[i] - xs[i - 1]; g += Math.max(d, 0); l += Math.max(-d, 0); }
    g /= n; l /= n; out[n] = l === 0 ? 100 : 100 - 100 / (1 + g / l);
    for (let i = n + 1; i < xs.length; i++) {
      const d = xs[i] - xs[i - 1];
      g = (g * (n - 1) + Math.max(d, 0)) / n; l = (l * (n - 1) + Math.max(-d, 0)) / n;
      out[i] = l === 0 ? 100 : 100 - 100 / (1 + g / l);
    }
    return out;
  }
  function macd(xs) {
    const a = ema(xs, 12), b = ema(xs, 26);
    const line = xs.map((_, i) => a[i] != null && b[i] != null ? a[i] - b[i] : null);
    const first = line.findIndex((v) => v != null);
    const sig = new Array(xs.length).fill(null);
    if (first >= 0) { const s = ema(line.slice(first), 9); s.forEach((v, i) => sig[first + i] = v); }
    return { line, sig, hist: line.map((v, i) => v != null && sig[i] != null ? v - sig[i] : null) };
  }
  function atr(cs, n = 14) {
    if (cs.length <= n) return null;
    const tr = cs.slice(1).map((c, i) => Math.max(c.h - c.l, Math.abs(c.h - cs[i].c), Math.abs(c.l - cs[i].c)));
    let a = tr.slice(0, n).reduce((x, y) => x + y, 0) / n;
    for (let i = n; i < tr.length; i++) a = (a * (n - 1) + tr[i]) / n;
    return a;
  }
  // Swing points: a high (low) higher (lower) than the k candles on each side. Close levels are merged.
  function levels(cs, k = 3) {
    const pts = [];
    for (let i = k; i < cs.length - k; i++) {
      let hi = true, lo = true;
      for (let j = i - k; j <= i + k; j++) { if (cs[j].h > cs[i].h) hi = false; if (cs[j].l < cs[i].l) lo = false; }
      if (hi) pts.push(cs[i].h); if (lo) pts.push(cs[i].l);
    }
    const a = atr(cs) || 0, out = [];
    pts.sort((x, y) => x - y).forEach((p) => {
      const last = out[out.length - 1];
      if (last && p - last.v < a * 0.5) { last.v = (last.v * last.n + p) / (last.n + 1); last.n++; } else out.push({ v: p, n: 1 });
    });
    return out;
  }
  function fib(cs) {
    if (cs.length < 10) return null;
    let hi = 0, lo = 0;
    cs.forEach((c, i) => { if (c.h > cs[hi].h) hi = i; if (c.l < cs[lo].l) lo = i; });
    const H = cs[hi].h, L = cs[lo].l, up = lo < hi;
    return { up, H, L, lv: [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1].map((f) => ({ f, v: up ? H - f * (H - L) : L + f * (H - L) })) };
  }
  function pivots(day) {   // classic pivots from the previous day's high, low, close
    if (!day) return null;
    const P = (day.h + day.l + day.c) / 3;
    return { P, R1: 2 * P - day.l, S1: 2 * P - day.h, R2: P + (day.h - day.l), S2: P - (day.h - day.l) };
  }
  function roundStep(lo, hi) {
    const raw = (hi - lo) / 3, p = Math.pow(10, Math.floor(Math.log10(raw)));
    return [1, 2, 2.5, 5, 10].map((m) => m * p).find((s) => s >= raw) || 10 * p;
  }
  window.TA = { ema, sma, boll, rsi, macd, atr, levels, fib, pivots };

  const state = { cs: [], all: [], ov: null, tf: "1m", hover: -1, opts: {} };

  function line(g, xs, x, y, col, width = 1.2, dash) {
    g.strokeStyle = col; g.lineWidth = width; g.setLineDash(dash || []); g.beginPath();
    let on = false;
    xs.forEach((v, i) => { if (v == null) { on = false; return; } const X = x(i), Y = y(v); on ? g.lineTo(X, Y) : g.moveTo(X, Y); on = true; });
    g.stroke(); g.setLineDash([]); g.lineWidth = 1;
  }
  function hline(g, v, y, x0, x1, col, label, dash, labelX) {
    const yy = Math.round(y(v)) + .5;
    g.strokeStyle = col; g.setLineDash(dash || [2, 3]); g.beginPath(); g.moveTo(x0, yy); g.lineTo(x1, yy); g.stroke(); g.setLineDash([]);
    if (label) { g.fillStyle = col; g.fillText(label, labelX ?? x0 + 4, yy - 3); }
  }

  function draw(cv, tip) {
    const dpr = window.devicePixelRatio || 1;
    const W = cv.clientWidth, H = cv.clientHeight;
    cv.width = W * dpr; cv.height = H * dpr;
    const g = cv.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, W, H);
    const cs = state.cs, o = state.opts, all = state.all, off = all.length - cs.length;
    const fg = css("--muted"), lineC = css("--line"), up = css("--up"), down = css("--down"), gold = css("--gold");
    const C = { e20: "#4ea1ff", e50: "#c77dff", e200: "#ff9f43", bb: "#7f8c9a", fib: "#e0b84f", piv: "#2ec4b6", rnd: "#5b6472", sr: "#ef6f6c" };
    g.font = "11px " + css("--mono");
    if (!cs.length) { g.fillStyle = fg; g.fillText("Şam hələ yoxdur: qiymətlər yığılır.", 16, 30); tip.textContent = ""; return; }
    const sub = o.sub && o.sub !== "none" ? o.sub : null;
    const padR = 64, padB = 22, padT = 18, subH = sub ? Math.round((H - padB) * 0.26) : 0;
    const mainB = H - padB - subH - (sub ? 8 : 0);
    const extra = state.ov ? 3 : 0;
    const n = cs.length, slots = n + extra, cw = (W - padR) / slots;
    const closesAll = all.map((c) => c.c);
    const vis = (arr) => arr.slice(off);
    let lo = Math.min(...cs.map(c => c.l)), hi = Math.max(...cs.map(c => c.h));
    if (state.ov) { lo = Math.min(lo, state.ov.lo80); hi = Math.max(hi, state.ov.hi80); }
    if (hi === lo) { hi += 1; lo -= 1; }
    const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
    const y = (v) => padT + (hi - v) / (hi - lo) * (mainB - padT);
    const x = (i) => i * cw + cw / 2;
    const inView = (v) => v > lo && v < hi;
    g.strokeStyle = lineC; g.fillStyle = fg; g.lineWidth = 1;
    for (let i = 0; i <= 5; i++) {
      const v = lo + (hi - lo) * i / 5, yy = Math.round(y(v)) + .5;
      g.beginPath(); g.moveTo(0, yy); g.lineTo(W - padR, yy); g.stroke();
      g.fillText(fmt(v), W - padR + 6, yy + 4);
    }
    const step = Math.max(1, Math.ceil(n / 7));
    g.fillStyle = fg;
    for (let i = 0; i < n; i += step) g.fillText(tlabel(cs[i].t, state.tf), i * cw + 2, H - 6);
    const x1 = W - padR;

    // ---- level overlays (behind the candles) ----
    if (o.round) {
      const s = roundStep(lo, hi);
      for (let v = Math.ceil(lo / s) * s; v < hi; v += s) hline(g, v, y, 0, x1, C.rnd, fmt(v), [1, 4]);
    }
    if (o.sr) {
      const last = cs[n - 1].c, lv = levels(all.slice(-Math.max(n, 120)));
      const below = lv.filter((l) => l.v < last).slice(-2), above = lv.filter((l) => l.v > last).slice(0, 2);
      below.forEach((l) => inView(l.v) && hline(g, l.v, y, 0, x1, up, "dəstək " + fmt(l.v), [6, 3]));
      above.forEach((l) => inView(l.v) && hline(g, l.v, y, 0, x1, down, "müqavimət " + fmt(l.v), [6, 3]));
    }
    if (o.fib) {
      const f = fib(cs);
      if (f) f.lv.forEach((l) => hline(g, l.v, y, 0, x1, C.fib, (l.f * 100).toFixed(1) + " %", [3, 3], 4));
    }
    if (o.piv && state.day) {
      const p = pivots(state.day);
      Object.entries(p).forEach(([k, v]) => inView(v) && hline(g, v, y, 0, x1, C.piv, k, [8, 4], x1 - 34));
    }
    if (o.bb) {
      const b = boll(closesAll);
      line(g, vis(b.up), x, y, C.bb, 1, [4, 3]); line(g, vis(b.lo), x, y, C.bb, 1, [4, 3]); line(g, vis(b.mid), x, y, C.bb, 1);
    }

    // ---- candles ----
    const bw = Math.max(1, cw * 0.7);
    cs.forEach((c, i) => {
      const xx = x(i), col = c.c >= c.o ? up : down;
      g.strokeStyle = col; g.fillStyle = col;
      g.beginPath(); g.moveTo(Math.round(xx) + .5, y(c.h)); g.lineTo(Math.round(xx) + .5, y(c.l)); g.stroke();
      const top = y(Math.max(c.o, c.c)), bh = Math.max(1, y(Math.min(c.o, c.c)) - top);
      g.fillRect(xx - bw / 2, top, bw, bh);
    });
    if (o.ema) {
      line(g, vis(ema(closesAll, 20)), x, y, C.e20); line(g, vis(ema(closesAll, 50)), x, y, C.e50);
      line(g, vis(ema(closesAll, 200)), x, y, C.e200, 1.6);
    }
    if (state.ov) {
      const x0 = n * cw + cw * 0.2, w = cw * 2.6, ov = state.ov;
      g.globalAlpha = .22; g.fillStyle = gold; g.fillRect(x0, y(ov.hi80), w, y(ov.lo80) - y(ov.hi80));
      g.globalAlpha = .45; g.fillRect(x0, y(ov.hi50), w, y(ov.lo50) - y(ov.hi50));
      g.globalAlpha = 1; g.strokeStyle = gold; g.setLineDash([4, 3]);
      g.beginPath(); g.moveTo(0, y(ov.price0)); g.lineTo(x0 + w, y(ov.price0)); g.stroke(); g.setLineDash([]);
      // the unified forecast: an arrow from the current price towards the side it leans to, with its probability
      if (ov.vahid != null && Math.abs(ov.vahid - 0.5) >= 0.01) {
        const upw = ov.vahid > 0.5, cx0 = x0 + w / 2, y0 = y(ov.price0);
        const y1 = upw ? y(ov.hi50) : y(ov.lo50);
        g.strokeStyle = g.fillStyle = upw ? up : down; g.lineWidth = 2;
        g.beginPath(); g.moveTo(cx0, y0); g.lineTo(cx0, y1); g.stroke();
        g.beginPath(); g.moveTo(cx0, y1); g.lineTo(cx0 - 5, y1 + (upw ? 7 : -7)); g.lineTo(cx0 + 5, y1 + (upw ? 7 : -7)); g.fill();
        g.lineWidth = 1; g.font = "11px ui-monospace,monospace"; g.textAlign = "right";
        g.fillText(`Vahid ${Math.round(ov.vahid * 100)}%${ov.proven ? " ✓" : " · sübut yox"}`, Math.max(80, x0 - 4), y1 + (upw ? -4 : 12));
        g.textAlign = "left";
      }
    }
    // ---- alarm marks (opts.marks: [{ts, kind, text}]): a glowing triangle above the candle it happened in ----
    const marksAt = {};
    if (o.marks && o.marks.length && n > 1) {
      const span = cs[1].t - cs[0].t;
      o.marks.forEach((m) => {
        const i = Math.floor((m.ts - cs[0].t) / span);
        if (i < 0 || i >= n) return;
        (marksAt[i] = marksAt[i] || []).push(m);
      });
      const MC = { band: "#f0b54a", news: "#38c8ff", flow: "#38c8ff", release: "#a98bff", move: "#ff5d6c" };
      Object.entries(marksAt).forEach(([i, ms]) => {
        const c = cs[+i], X = x(+i), Y = Math.max(padT + 8, y(c.h) - 12), col = MC[ms[ms.length - 1].kind] || gold;
        g.save(); g.shadowColor = col; g.shadowBlur = 10; g.fillStyle = col;
        g.beginPath(); g.moveTo(X, Y + 6); g.lineTo(X - 5, Y - 3); g.lineTo(X + 5, Y - 3); g.closePath(); g.fill();
        if (ms.length > 1) { g.shadowBlur = 0; g.font = "9px " + css("--mono"); g.fillText(String(ms.length), X + 6, Y - 2); }
        g.restore();
      });
    }

    const last = cs[n - 1];
    g.fillStyle = gold; g.fillRect(W - padR, y(last.c) - 8, padR, 16);
    g.fillStyle = "#1b1505"; g.fillText(fmt(last.c), W - padR + 6, y(last.c) + 4);

    // ---- lower panel ----
    if (sub) {
      const top = mainB + 8, bot = H - padB;
      g.strokeStyle = lineC; g.beginPath(); g.moveTo(0, top - 4 + .5); g.lineTo(W, top - 4 + .5); g.stroke();
      if (sub === "rsi") {
        const r = vis(rsi(closesAll)), ry = (v) => top + (100 - v) / 100 * (bot - top);
        [30, 50, 70].forEach((v) => hline(g, v, ry, 0, x1, v === 50 ? lineC : fg, null, [2, 3]));
        g.fillStyle = fg; g.fillText("RSI 14", 4, top + 10); g.fillText("70", x1 + 6, ry(70) + 4); g.fillText("30", x1 + 6, ry(30) + 4);
        line(g, r, x, ry, gold, 1.4);
        const lr = r[r.length - 1]; if (lr != null) { g.fillStyle = gold; g.fillText(lr.toFixed(0), x1 + 30, ry(lr) + 4); }
      } else {
        const m = macd(closesAll), L = vis(m.line), S = vis(m.sig), Hh = vis(m.hist);
        const vals = [...L, ...S, ...Hh].filter((v) => v != null);
        const mx = Math.max(1e-9, ...vals.map(Math.abs)), my = (v) => (top + bot) / 2 - v / mx * (bot - top) / 2;
        hline(g, 0, my, 0, x1, lineC, null, [2, 3]);
        Hh.forEach((v, i) => { if (v == null) return; g.fillStyle = v >= 0 ? up : down; g.globalAlpha = .5;
          g.fillRect(x(i) - bw / 2, Math.min(my(0), my(v)), bw, Math.abs(my(v) - my(0))); g.globalAlpha = 1; });
        line(g, L, x, my, "#4ea1ff", 1.3); line(g, S, x, my, "#ff9f43", 1.3);
        g.fillStyle = fg; g.fillText("MACD 12/26/9", 4, top + 10);
      }
    }

    const hcan = state.hover >= 0 && state.hover < n ? cs[state.hover] : last;
    if (state.hover >= 0 && state.hover < n) {
      g.strokeStyle = fg; g.globalAlpha = .4;
      g.beginPath(); g.moveTo(x(state.hover), padT); g.lineTo(x(state.hover), H - padB); g.stroke(); g.globalAlpha = 1;
    }
    const hm = state.hover >= 0 ? marksAt[state.hover] : null;
    tip.textContent = tlabel(hcan.t, "1m") + " NY  Açılış " + fmt(hcan.o) + "  Max " + fmt(hcan.h) + "  Min " + fmt(hcan.l) +
      "  Bağlanış " + fmt(hcan.c) + (hm ? "   ⚡ " + hm.map((m) => m.text).join(" · ") : "");
    state.cw = cw;
  }

  window.drawChart = function (cv, tip, candles, overlay, tf, opts) {
    opts = opts || {};
    const show = opts.show || candles.length;
    state.all = candles; state.cs = candles.slice(-show); state.ov = overlay; state.tf = tf; state.opts = opts;
    state.day = opts.day || null;
    draw(cv, tip);
    if (!cv._wired) {
      cv._wired = true;
      const move = (e) => {
        const r = cv.getBoundingClientRect();
        state.hover = Math.floor((e.clientX - r.left) / (state.cw || 1)); draw(cv, tip);
      };
      cv.addEventListener("pointermove", move);
      cv.addEventListener("pointerdown", move);
      cv.addEventListener("pointerleave", () => { state.hover = -1; draw(cv, tip); });
      window.addEventListener("resize", () => draw(cv, tip));
    }
  };
})();

/* Small line chart for the Judge: drawLines(canvas, series [{name, color, pts: [[t, v]]}], refs [{v, label}], lo, hi) */
window.drawLines = function (cv, series, refs, lo, hi) {
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
  cv.width = W * dpr; cv.height = H * dpr;
  const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
  g.font = "11px " + css("--mono");
  const fg = css("--muted"), lineC = css("--line"), padL = 38, padR = 8, padT = 8, padB = 20;
  const pts = series.flatMap((s) => s.pts);
  if (!pts.length) { g.fillStyle = fg; g.fillText("Hələ kifayət qədər yoxlanmış proqnoz yoxdur.", 12, 24); return; }
  const t0 = Math.min(...pts.map((p) => p[0])), t1 = Math.max(...pts.map((p) => p[0])) || t0 + 1;
  const x = (t) => padL + (t - t0) / Math.max(1, t1 - t0) * (W - padL - padR);
  const y = (v) => padT + (hi - Math.min(hi, Math.max(lo, v))) / (hi - lo) * (H - padT - padB);
  g.strokeStyle = lineC; g.fillStyle = fg;
  for (let i = 0; i <= 4; i++) {
    const v = lo + (hi - lo) * i / 4, yy = Math.round(y(v)) + .5;
    g.beginPath(); g.moveTo(padL, yy); g.lineTo(W - padR, yy); g.stroke(); g.fillText((v * 100).toFixed(0) + "%", 2, yy + 4);
  }
  const d0 = new Date(t0 * 1000), d1 = new Date(t1 * 1000), span = t1 - t0;
  const lab = (d) => span > 3 * 86400 ? d.toISOString().slice(0, 10) : d.toISOString().slice(5, 16).replace("T", " ");
  g.fillText(lab(d0), padL, H - 5); const l1 = lab(d1); g.fillText(l1, W - padR - g.measureText(l1).width, H - 5);
  refs.forEach((r) => { g.strokeStyle = r.color || fg; g.setLineDash([5, 4]); g.beginPath(); g.moveTo(padL, y(r.v)); g.lineTo(W - padR, y(r.v)); g.stroke();
    g.setLineDash([]); if (r.label) { g.fillStyle = r.color || fg; g.fillText(r.label, padL + 4, y(r.v) - 4); } });
  series.forEach((s) => { if (!s.pts.length) return; g.strokeStyle = s.color; g.lineWidth = 1.6; g.beginPath();
    s.pts.forEach((p, i) => i ? g.lineTo(x(p[0]), y(p[1])) : g.moveTo(x(p[0]), y(p[1]))); g.stroke(); g.lineWidth = 1; });
};
