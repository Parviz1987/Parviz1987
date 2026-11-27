// Fundamental blok: gold's daily chart with the fundamental rules' firings, each driver next to gold, the central
// banks' monthly buying, COT, the US surprise index, what the block says now and the book with the Judge's record.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const pct = (v) => (v == null ? "—" : Math.round(v * 100) + " %");
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const NAMES = { XAU: "Qızıl", XAG: "Gümüş", XPT: "Platin", XPD: "Palladium" };
  const ST = { "sübut": "✅ sübut", yox: "❌ yox", "zəif": "⚠️ zəif", az: "⏳ az", "xərc": "💸 xərc", "namizəd": "🏁 namizəd (son sınaq gözlənir)" };
  const FCOL = { faiz: "#4ea1ff", dollar: "#3fb27f", "mövqe": "#c77dff", "sürpriz": "#ff9f43", "mərkəzi bank": "#e8b94a" };
  const load = (k, d) => { try { return JSON.parse(localStorage.getItem("tst_fa_" + k)) ?? d; } catch (e) { return d; } };
  const save = (k, v) => { try { localStorage.setItem("tst_fa_" + k, JSON.stringify(v)); } catch (e) { /* fine */ } };
  let sym = load("sym", "XAU"), cnt = load("cnt", 250), data = null;

  function seg(el, items, cur, on) {
    el.innerHTML = items.map(([k, n]) => `<button class="${String(k) === String(cur) ? "on" : ""}" data-k="${k}">${esc(n)}</button>`).join("");
    el.querySelectorAll("button").forEach((b) => b.onclick = () => on(b.dataset.k));
  }
  // gold (grey, left scale) and one driver (colour, right scale) over time; invert: draw the driver upside down so
  // «good for gold» goes up on both lines
  function pair(cv, gold, pts, col, invert, title) {
    const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
    cv.width = W * dpr; cv.height = H * dpr;
    const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
    g.font = "11px " + css("--mono"); const fg = css("--muted");
    g.fillStyle = fg; g.fillText(title + (invert ? "  (tərsinə çəkilib: yuxarı = qızıl üçün yaxşı)" : ""), 6, 12);
    if (!pts.length) { g.fillText("məlumat hələ yoxdur", 6, 32); return; }
    const t0 = Math.min(gold[0][0], pts[0][0]), t1 = Math.max(gold[gold.length - 1][0], pts[pts.length - 1][0]);
    const x = (t) => 6 + (t - t0) / Math.max(1, t1 - t0) * (W - 60);
    const scale = (arr, inv) => { const vs = arr.map((p) => p[1]); let lo = Math.min(...vs), hi = Math.max(...vs); if (hi === lo) { hi += 1; lo -= 1; }
      return (v) => { const f = (v - lo) / (hi - lo); return 20 + (inv ? f : 1 - f) * (H - 34); }; };
    const yg = scale(gold, false), yf = scale(pts, invert);
    const draw = (arr, y, c, w) => { g.strokeStyle = c; g.lineWidth = w; g.beginPath(); arr.forEach((p, i) => i ? g.lineTo(x(p[0]), y(p[1])) : g.moveTo(x(p[0]), y(p[1]))); g.stroke(); g.lineWidth = 1; };
    draw(gold, yg, "rgba(160,170,185,.55)", 1.2); draw(pts, yf, col, 1.6);
    const last = pts[pts.length - 1][1];
    g.fillStyle = col; g.fillText(Math.abs(last) >= 1000 ? Math.round(last).toLocaleString("en-US") : last.toFixed(2), W - 52, yf(last) + 4);
    const d0 = new Date(t0 * 1000).toISOString().slice(0, 7), d1 = new Date(t1 * 1000).toISOString().slice(0, 7);
    g.fillStyle = fg; g.fillText(d0, 6, H - 3); g.fillText(d1, W - 60, H - 3);
  }
  function bars(cv, pts, title, unit) {
    const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
    cv.width = W * dpr; cv.height = H * dpr;
    const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
    g.font = "11px " + css("--mono"); const fg = css("--muted");
    g.fillStyle = fg; g.fillText(title, 6, 12);
    if (!pts.length) { g.fillText("məlumat hələ yoxdur (gündə bir dəfə yüklənir)", 6, 32); return; }
    const mx = Math.max(1, ...pts.map((p) => Math.abs(p[1]))), mid = 20 + (H - 34) / 2, bw = (W - 60) / pts.length;
    g.strokeStyle = css("--line"); g.beginPath(); g.moveTo(6, mid); g.lineTo(W - 54, mid); g.stroke();
    pts.forEach((p, i) => { const h = p[1] / mx * (H - 34) / 2; g.fillStyle = p[1] >= 0 ? css("--up") : css("--down");
      g.fillRect(6 + i * bw, h >= 0 ? mid - h : mid, Math.max(1, bw - 1), Math.abs(h)); });
    const last = pts[pts.length - 1][1];
    g.fillStyle = fg; g.fillText(`son: ${last > 0 ? "+" : ""}${last} ${unit}`, W - 130, 12);
  }

  function draw() {
    if (!data || !data.candles || !data.candles.length) return;
    const fam = Object.fromEntries((data.book || []).map((r) => [r.id, r]));
    const seen = new Set((data.fired || []).map((f) => f.rule + "|" + f.dir + "|" + f.i));
    const marks = (data.fired || []).filter((f) => !seen.has(f.rule + "|" + f.dir + "|" + (f.i - 1))).map((f) => ({
      i: f.i, dir: f.dir, c: FCOL[(fam[f.rule] || {}).family] || "#e8b94a", label: ((fam[f.rule] || {}).name || f.rule) + ": " + (f.note || "") }));
    drawChart($("cv"), $("tip"), data.candles, null, "1d", { show: Math.min(cnt, data.candles.length), ema: true, sub: "none", ext: { marks } });
  }
  function factors() {
    const t0 = data.candles.length ? data.candles[Math.max(0, data.candles.length - 520)].t : 0;
    const gold = data.candles.filter((c) => c.t >= t0).map((c) => [c.t, c.c]);
    const items = [];
    (data.factors || []).forEach((f, k) => items.push({ id: "fc" + k, f }));
    $("facs").innerHTML = items.map((it) => `<div class="fac"><canvas id="${it.id}"></canvas></div>`).join("") +
      '<div class="fac"><canvas id="fcb"></canvas></div><div class="fac"><canvas id="fsu"></canvas></div>';
    items.forEach((it) => pair($(it.id), gold, it.f.pts, ["#4ea1ff", "#ef476f", "#ff9f43", "#3fb27f", "#c77dff"][items.indexOf(it) % 5], it.f.good < 0, it.f.name));
    bars($("fcb"), (data.cb || []).slice(-36), "Mərkəzi bankların aylıq xalis alışı (IMF, 25 bank), ton", "ton");
    pair($("fsu"), gold, (data.surprise || []).map((p) => [p[0], p[1]]), "#ff9f43", false, "ABŞ sürpriz indeksi (14 gün, qızıl üçün işarə)");
  }
  function nowBox() {
    const n = data.now; if (!n) { $("now").innerHTML = "<p class='note'>məlumat yoxdur</p>"; return; }
    const p = n.vote.p, book = Object.fromEntries((data.book || []).map((r) => [r.id, r]));
    const jl = (m) => { const r = n.judge[m] || {}; return r.nh ? `${r.nh} haldan ${pct(r.hit_rate)} düz (hədd ${pct(r.bar)}) · ${ST[r.status] || esc(r.status || "")}` : "hələ nəticə yoxdur"; };
    $("nowt").textContent = "son gün " + new Date(n.t * 1000).toISOString().slice(0, 10);
    $("now").innerHTML = `<div class="tanow">
      <div><div class="big ${p > 0.5 ? "up" : p < 0.5 ? "down" : ""}">${Math.abs(p - 0.5) < 0.01 ? "fikir yoxdur" : p > 0.5 ? "▲ yuxarı" : "▼ aşağı"} · ${pct(p)}</div>
        <p class="note">«Fundamental» səsi (gün və həftə proqnozuna gedir): ${esc(n.vote.basis)}</p><p class="note">Hakim: ${jl("fundamental")}</p></div>
      <div><p><b>Bu gün işləyən qaydalar:</b></p><ul class="tarules">${n.rules.map((r) => `<li><span style="color:${FCOL[(book[r.rule] || {}).family] || "#888"}">${r.dir > 0 ? "▲" : "▼"}</span> ${esc((book[r.rule] || {}).name || r.rule)} <span class="note">${esc(r.note || "")}</span></li>`).join("") || "<li class='note'>yoxdur</li>"}</ul>
        <p class="note">ABŞ rəqəminin ilk saatı («Hadisə sürprizi»): ${jl("surprise")}</p></div>
      <div><p><b>Strateq (AI, fundamental şərh):</b> ${n.strateq ? pct(n.strateq.p) + " yuxarı" : "kartı yoxdur"}</p>
        ${n.strateq ? `<p class="note">${esc(n.strateq.scenario || "")}</p><p class="note"><b>Əks ssenari:</b> ${esc(n.strateq.counter || "—")}</p>` : ""}
        <p class="note">Hakim: ${jl("strateq")}</p></div></div>
      <p class="note">Bu, sübut olmayan fikirdir: AL / SAT yalnız Hakimin sübutu ilə göstərilir.</p>`;
  }
  function bookBox() {
    $("book").innerHTML = (data.book || []).map((r) => {
      const x = r.record, rr = x && x.rr;
      return `<div class="tarule"><b><i style="display:inline-block;width:10px;height:10px;border-radius:3px;background:${FCOL[r.family] || "#555"}"></i> ${esc(r.name)}</b>
        <span class="note">${r.family ? "" : "analitik faktlardan tətbiq edir · "}${x ? `${x.n} gün, ${pct(x.hit_rate)} düz, ${ST[x.status] || esc(x.status)}${rr ? ` · stop+hədəf: hədəfə ${pct(rr.target_share)}, ${rr.net_r >= 0 ? "+" : ""}${rr.net_r.toFixed(2)} R` : ""}` : (r.family ? "hələ ölçülməyib" : "")}</span>
        <details><summary class="note">necə işləyir</summary><p class="note">${esc(r.how)}</p>
          <p class="note"><b>Siqnal:</b> ${esc(r.signal)} <b>Ləğv:</b> ${esc(r.void)}</p><p class="note"><b>Mənbə:</b> ${esc(r.source)}</p></details></div>`;
    }).join("");
  }
  const home = $("wrapc").parentNode, after = $("wrapc").nextSibling;
  function setBig(on) { if (on) document.body.appendChild($("wrapc")); else home.insertBefore($("wrapc"), after);
    $("wrapc").classList.toggle("full", on); document.body.classList.toggle("noscroll", on); setTimeout(draw, 30); }
  $("big").onclick = () => setBig(true); $("small").onclick = () => setBig(false);
  addEventListener("keydown", (e) => { if (e.key === "Escape") setBig(false); });
  // only a real change of width redraws: on a phone the address bar hides and shows while scrolling and fires
  // «resize» each time; rebuilding 16 charts on every scroll could make the phone browser close the page
  let lastW = innerWidth;
  addEventListener("resize", () => { if (innerWidth === lastW) return; lastW = innerWidth; if (data) factors(); });
  addEventListener("tst:unfold", () => { if (data) factors(); });               // a folded section opened (fold.js)
  async function go() {
    seg($("sym"), Object.entries(NAMES), sym, (k) => { sym = k; save("sym", k); go(); });
    seg($("cnt"), [[120, "6 ay"], [250, "1 il"], [500, "2 il"]], cnt, (k) => { cnt = +k; save("cnt", cnt); seg($("cnt"), [[120, "6 ay"], [250, "1 il"], [500, "2 il"]], cnt, () => {}); draw(); go(); });
    try { const r = await fetch(`/api/fundamental?symbol=${sym}`, { credentials: "same-origin" }); if (!r.ok) return; data = await r.json(); } catch (e) { return; }
    $("upd").textContent = "yeniləndi " + new Date().toLocaleTimeString("en-GB", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" }) + " NY";
    draw(); nowBox(); factors(); bookBox();
  }
  go(); setInterval(go, 300000);
})();
