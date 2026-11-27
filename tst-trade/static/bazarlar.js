// Bazarlar arası blok: the metal's chart with the cross-market rules' firings (1 h / 4 h / 1 day), each linked market
// next to the metal with how strongly they move together and whether it moves first, what the block says now and the
// book with the Judge's record.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const pct = (v) => (v == null ? "—" : Math.round(v * 100) + " %");
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const NAMES = { XAU: "Qızıl", XAG: "Gümüş", XPT: "Platin", XPD: "Palladium" };
  const TFS = [["1h", "1 saat"], ["4h", "4 saat"], ["1d", "1 gün"]];
  const ST = { "sübut": "✅ sübut", yox: "❌ yox", "zəif": "⚠️ zəif", az: "⏳ az", "xərc": "💸 xərc", "namizəd": "🏁 namizəd (son sınaq gözlənir)" };
  const FCOL = { dollar: "#3fb27f", faiz: "#4ea1ff", neft: "#ff9f43", risk: "#ef476f", "sənaye": "#c77dff", "metal cütü": "#e8b94a" };
  const load = (k, d) => { try { return JSON.parse(localStorage.getItem("tst_cm_" + k)) ?? d; } catch (e) { return d; } };
  const save = (k, v) => { try { localStorage.setItem("tst_cm_" + k, JSON.stringify(v)); } catch (e) { /* fine */ } };
  let sym = load("sym", "XAU"), tf = load("tf", "1h"), data = null;

  function seg(el, items, cur, on) {
    el.innerHTML = items.map(([k, n]) => `<button class="${String(k) === String(cur) ? "on" : ""}" data-k="${k}">${esc(n)}</button>`).join("");
    el.querySelectorAll("button").forEach((b) => b.onclick = () => on(b.dataset.k));
  }
  function pair(cv, gold, pts, col, invert, title) {
    const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
    cv.width = W * dpr; cv.height = H * dpr;
    const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
    g.font = "11px " + css("--mono"); const fg = css("--muted");
    g.fillStyle = fg; g.fillText(title + (invert ? "  (tərsinə: yuxarı = metal üçün yaxşı)" : ""), 6, 12);
    if (!pts.length) { g.fillText("bu bazarın şamı yoxdur (broker vermir)", 6, 32); return; }
    const t0 = gold[0][0], t1 = gold[gold.length - 1][0];
    const x = (t) => 6 + (t - t0) / Math.max(1, t1 - t0) * (W - 60);
    const scale = (arr, inv) => { const vs = arr.map((p) => p[1]); let lo = Math.min(...vs), hi = Math.max(...vs); if (hi === lo) { hi += 1; lo -= 1; }
      return (v) => { const f = (v - lo) / (hi - lo); return 20 + (inv ? f : 1 - f) * (H - 34); }; };
    const yg = scale(gold, false), yf = scale(pts, invert);
    const line = (arr, y, c, w) => { g.strokeStyle = c; g.lineWidth = w; g.beginPath(); arr.forEach((p, i) => i ? g.lineTo(x(p[0]), y(p[1])) : g.moveTo(x(p[0]), y(p[1]))); g.stroke(); g.lineWidth = 1; };
    line(gold, yg, "rgba(160,170,185,.55)", 1.2); line(pts, yf, col, 1.6);
  }
  function draw() {
    if (!data || !data.candles || !data.candles.length) return;
    const fam = Object.fromEntries((data.book || []).map((r) => [r.id, r]));
    const marks = (data.fired || []).map((f) => ({ i: f.i, dir: f.dir, c: FCOL[(fam[f.rule] || {}).family] || "#e8b94a",
      label: ((fam[f.rule] || {}).name || f.rule) + ": " + (f.note || "") }));
    drawChart($("cv"), $("tip"), data.candles, null, tf, { show: Math.min(250, data.candles.length), ema: true, sub: "none", ext: { marks } });
  }
  function markets() {
    const gold = data.candles.map((c) => [c.t, c.c]);
    $("facs").innerHTML = (data.markets || []).map((m, k) => `<div class="fac"><canvas id="mk${k}"></canvas>
      <p class="note">${m.corr == null ? "əlaqə ölçülməyib" : `birlikdə hərəkət (1 saat, 30 gün): ${m.corr >= 0 ? "+" : ""}${m.corr.toFixed(2)}`}${m.lead == null ? "" : ` · önə düşmə (15 dəq): ${m.lead >= 0 ? "+" : ""}${m.lead.toFixed(2)}`}<br>${esc(m.why)}</p></div>`).join("");
    (data.markets || []).forEach((m, k) => pair($("mk" + k), gold, m.pts, Object.values(FCOL)[k % 6], m.sign < 0, m.name));
  }
  function nowBox() {
    const n = data.now; if (!n) { $("now").innerHTML = "<p class='note'>məlumat yoxdur</p>"; return; }
    const p = n.vote.p, book = Object.fromEntries((data.book || []).map((r) => [r.id, r]));
    const r = n.judge.bazarlar || {};
    $("nowt").textContent = "son şam " + new Date(n.t * 1000).toLocaleString("en-GB", { timeZone: "America/New_York" }) + " NY";
    $("now").innerHTML = `<div class="tanow">
      <div><div class="big ${p > 0.5 ? "up" : p < 0.5 ? "down" : ""}">${Math.abs(p - 0.5) < 0.01 ? "fikir yoxdur" : p > 0.5 ? "▲ yuxarı" : "▼ aşağı"} · ${pct(p)}</div>
        <p class="note">«Bazarlar arası» səsi: ${esc(n.vote.basis)}</p>
        <p class="note">Hakim: ${r.nh ? `${r.nh} haldan ${pct(r.hit_rate)} düz (hədd ${pct(r.bar)}) · ${ST[r.status] || esc(r.status || "")}` : "hələ nəticə yoxdur"}</p></div>
      <div><p><b>Son şamda işləyən qaydalar:</b></p><ul class="tarules">${n.rules.map((x) => `<li><span style="color:${FCOL[(book[x.rule] || {}).family] || "#888"}">${x.dir > 0 ? "▲" : "▼"}</span> ${esc((book[x.rule] || {}).name || x.rule)} <span class="note">${esc(x.note || "")}</span></li>`).join("") || "<li class='note'>yoxdur</li>"}</ul></div></div>
      <p class="note">Bu, sübut olmayan fikirdir: AL / SAT yalnız Hakimin sübutu ilə göstərilir.</p>`;
  }
  function bookBox() {
    $("book").innerHTML = (data.book || []).map((r) => {
      const x = r.record, rr = x && x.rr;
      return `<div class="tarule"><b><i style="display:inline-block;width:10px;height:10px;border-radius:3px;background:${FCOL[r.family] || "#555"}"></i> ${esc(r.name)}</b> <span class="note mono">${esc(r.id)}</span>
        <span class="note">${x ? `${x.n} hal (${esc(tf)}), ${pct(x.hit_rate)} düz, ${ST[x.status] || esc(x.status)}${rr ? ` · stop+hədəf: hədəfə ${pct(rr.target_share)}, ${rr.net_r >= 0 ? "+" : ""}${rr.net_r.toFixed(2)} R` : ""}` : "hələ ölçülməyib"}${r.voice !== "bazarlar" ? " · səsi: " + esc(r.voice) + " blokunda" : ""}</span>
        <details><summary class="note">necə işləyir</summary><p class="note">${esc(r.how)}</p>
          <p class="note"><b>Siqnal:</b> ${esc(r.signal)} <b>Ləğv:</b> ${esc(r.void)}</p><p class="note"><b>Mənbə:</b> ${esc(r.source)}</p></details></div>`;
    }).join("");
  }
  const home = $("wrapc").parentNode, after = $("wrapc").nextSibling;
  function setBig(on) { if (on) document.body.appendChild($("wrapc")); else home.insertBefore($("wrapc"), after);
    $("wrapc").classList.toggle("full", on); document.body.classList.toggle("noscroll", on); setTimeout(draw, 30); }
  $("big").onclick = () => setBig(true); $("small").onclick = () => setBig(false);
  addEventListener("keydown", (e) => { if (e.key === "Escape") setBig(false); });
  let lastW = innerWidth;      // a real change of width only (a phone fires «resize» while scrolling)
  addEventListener("resize", () => { if (innerWidth === lastW) return; lastW = innerWidth; if (data) { draw(); markets(); } });
  async function go() {
    seg($("sym"), Object.entries(NAMES), sym, (k) => { sym = k; save("sym", k); go(); });
    seg($("tf"), TFS, tf, (k) => { tf = k; save("tf", k); go(); });
    try { const r = await fetch(`/api/bazarlar?symbol=${sym}&tf=${tf}`, { credentials: "same-origin" }); if (!r.ok) return; data = await r.json(); } catch (e) { return; }
    $("upd").textContent = "yeniləndi " + new Date().toLocaleTimeString("en-GB", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" }) + " NY";
    draw(); nowBox(); markets(); bookBox();
  }
  go(); setInterval(go, 300000);
})();
