// Vaxt və təqvim bloku: the metal's chart with the calendar rules' firings (1 h / 1 day), the average move by New York
// hour and by weekday from our own candles (a description, not a forecast), the calendar ahead, the slow methods
// (season, festivals), what the block says now and the book with the Judge's record.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const pct = (v) => (v == null ? "—" : Math.round(v * 100) + " %");
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const NAMES = { XAU: "Qızıl", XAG: "Gümüş", XPT: "Platin", XPD: "Palladium" };
  const TFS = [["1h", "1 saat"], ["1d", "1 gün"]];
  const DAYS = ["B.e.", "Ç.a.", "Ç.", "C.a.", "C."];
  const ST = { "sübut": "✅ sübut", yox: "❌ yox", "zəif": "⚠️ zəif", az: "⏳ az", "xərc": "💸 xərc", "namizəd": "🏁 namizəd (son sınaq gözlənir)" };
  const FCOL = { seans: "#4ea1ff", fiksinq: "#e8b94a", "gün": "#c77dff", "ay dönüşü": "#3fb27f", bayram: "#ff9f43", "rəqəm saatı": "#ef476f" };
  const load = (k, d) => { try { return JSON.parse(localStorage.getItem("tst_tm_" + k)) ?? d; } catch (e) { return d; } };
  const save = (k, v) => { try { localStorage.setItem("tst_tm_" + k, JSON.stringify(v)); } catch (e) { /* fine */ } };
  let sym = load("sym", "XAU"), tf = load("tf", "1h"), data = null;

  function seg(el, items, cur, on) {
    el.innerHTML = items.map(([k, n]) => `<button class="${String(k) === String(cur) ? "on" : ""}" data-k="${k}">${esc(n)}</button>`).join("");
    el.querySelectorAll("button").forEach((b) => b.onclick = () => on(b.dataset.k));
  }
  // bars of the average move (%) with the share of up candles written on top
  function bars(cv, rows, labels, title) {
    const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
    cv.width = W * dpr; cv.height = H * dpr;
    const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
    g.font = "10px " + css("--mono"); const fg = css("--muted");
    g.fillStyle = fg; g.fillText(title, 6, 12);
    const vals = rows.map((r) => r.avg || 0), mx = Math.max(1e-6, ...vals.map(Math.abs));
    const mid = 22 + (H - 46) / 2, bw = (W - 12) / rows.length;
    g.strokeStyle = css("--line"); g.beginPath(); g.moveTo(6, mid); g.lineTo(W - 6, mid); g.stroke();
    rows.forEach((r, i) => {
      const h = (r.avg || 0) / mx * (H - 46) / 2;
      g.fillStyle = (r.avg || 0) >= 0 ? css("--up") : css("--down");
      g.fillRect(6 + i * bw + 1, h >= 0 ? mid - h : mid, Math.max(1, bw - 2), Math.abs(h));
      g.fillStyle = fg; g.fillText(labels[i], 6 + i * bw + 1, H - 4);
    });
  }
  function draw() {
    if (!data || !data.candles || !data.candles.length) return;
    const fam = Object.fromEntries((data.book || []).map((r) => [r.id, r]));
    const marks = (data.fired || []).filter((f) => f.rule !== "TM-SES-1" && f.rule !== "TM-SES-2" || tf !== "1h").map((f) => ({ i: f.i, dir: f.dir,
      c: FCOL[(fam[f.rule] || {}).family] || "#e8b94a", label: ((fam[f.rule] || {}).name || f.rule) + ": " + (f.note || "") }));
    drawChart($("cv"), $("tip"), data.candles, null, tf, { show: Math.min(tf === "1h" ? 120 : 250, data.candles.length), ema: true, sub: "none", ext: { marks } });
  }
  function stats() {
    const h = data.by_hour || [], d = data.by_day || [];
    bars($("hr"), h, h.map((r) => (r.h % 3 === 0 ? String(r.h) : "")), "Saat (New York) üzrə orta hərəkət, % — yaşıl: qalxır, qırmızı: enir");
    bars($("dw"), d, d.map((r) => DAYS[r.d]), "Həftənin günü üzrə orta hərəkət, %");
  }
  function nowBox() {
    const n = data.now; if (!n) { $("now").innerHTML = "<p class='note'>məlumat yoxdur</p>"; return; }
    const p = n.vote.p, r = n.judge.vaxt || {}, sl = data.slow || {};
    $("nowt").textContent = "son şam " + new Date(n.t * 1000).toLocaleString("en-GB", { timeZone: "America/New_York" }) + " NY";
    $("now").innerHTML = `<div class="tanow">
      <div><div class="big ${p > 0.5 ? "up" : p < 0.5 ? "down" : ""}">${Math.abs(p - 0.5) < 0.01 ? "fikir yoxdur" : p > 0.5 ? "▲ yuxarı" : "▼ aşağı"} · ${pct(p)}</div>
        <p class="note">«Vaxt» səsi (saat və gün proqnozuna gedir): ${esc(n.vote.basis)}</p>
        <p class="note">Hakim: ${r.nh ? `${r.nh} haldan ${pct(r.hit_rate)} düz (hədd ${pct(r.bar)}) · ${ST[r.status] || esc(r.status || "")}` : "hələ nəticə yoxdur"}</p></div>
      <div><p><b>Həftə və ay üfüqü (yavaş üsullar):</b></p>
        <p class="note">Mövsümilik: ${sl.season ? pct(sl.season.p) + " — " + esc(sl.season.basis) : "—"}</p>
        <p class="note">Zərgərlik təqvimi: ${sl.jewel ? pct(sl.jewel.p) + " — " + esc(sl.jewel.basis) : "—"}</p></div></div>
      <p class="note">Bu, sübut olmayan fikirdir: AL / SAT yalnız Hakimin sübutu ilə göstərilir.</p>`;
  }
  function ahead() {
    $("ahead").innerHTML = (data.ahead || []).length ? `<ul class="tarules">${data.ahead.map((a) => `<li><b>${esc(a.date)}</b> — ${esc(a.what)}</li>`).join("")}</ul>` : "<p class='note'>yaxın 2 ayda bayram yoxdur</p>";
  }
  function bookBox() {
    $("book").innerHTML = (data.book || []).map((r) => {
      const x = r.record, rr = x && x.rr;
      return `<div class="tarule"><b><i style="display:inline-block;width:10px;height:10px;border-radius:3px;background:${FCOL[r.family] || "#555"}"></i> ${esc(r.name)}</b> <span class="note mono">${esc(r.id)}</span>
        <span class="note">${x ? `${x.n} hal (${esc(tf)}), ${pct(x.hit_rate)} düz, ${ST[x.status] || esc(x.status)}${rr ? ` · stop+hədəf: hədəfə ${pct(rr.target_share)}, ${rr.net_r >= 0 ? "+" : ""}${rr.net_r.toFixed(2)} R` : ""}` : "bu vaxt çərçivəsində ölçülmür"}</span>
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
  addEventListener("resize", () => { if (innerWidth === lastW) return; lastW = innerWidth; if (data) { draw(); stats(); } });
  addEventListener("tst:unfold", () => { if (data) { draw(); stats(); } });     // a folded section opened (fold.js)
  async function go() {
    seg($("sym"), Object.entries(NAMES), sym, (k) => { sym = k; save("sym", k); go(); });
    seg($("tf"), TFS, tf, (k) => { tf = k; save("tf", k); go(); });
    try { const r = await fetch(`/api/vaxt?symbol=${sym}&tf=${tf}`, { credentials: "same-origin" }); if (!r.ok) return; data = await r.json(); } catch (e) { return; }
    $("upd").textContent = "yeniləndi " + new Date().toLocaleTimeString("en-GB", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" }) + " NY";
    draw(); nowBox(); stats(); ahead(); bookBox();
  }
  go(); setInterval(go, 300000);
})();
