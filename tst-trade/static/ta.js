// Texniki analiz bloku: one big chart with every layer of the block (each switchable), every rule's firings as ▲/▼
// marks (each rule switchable), what the block says now on this timeframe, and the book with the Judge's record.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const pct = (v) => (v == null ? "—" : Math.round(v * 100) + " %");
  const NAMES = { XAU: "Qızıl", XAG: "Gümüş", XPT: "Platin", XPD: "Palladium" };
  const TFN = { "1h": "1 saat", "4h": "4 saat", "1d": "1 gün" };
  const ST = { "sübut": "✅ sübut", yox: "❌ yox", "zəif": "⚠️ zəif", az: "⏳ az", "xərc": "💸 xərc", "namizəd": "🏁 namizəd (son sınaq gözlənir)" };
  // the 12 kinds of technical analysis and which rules of the block belong to each
  const KINDS = [
    ["Klassik qrafik", ["TA-SR-1", "TA-TL-1", "TA-PIVOT-1", "TA-BRK-1", "TA-LDN-1"]],
    ["Fiqurlar", ["TA-PAT-1", "TA-PAT-HS", "TA-PAT-TRI", "TA-PAT-WEDGE", "TA-PAT-FLAG"]],
    ["Yapon şamları", ["TA-CDL-1"]],
    ["Trend indikatorları", ["TA-TREND-1", "TA-TREND-2", "TA-MACD-1", "TA-ICHI-1", "TA-ADX-1"]],
    ["Osilyatorlar", ["TA-RSI-1", "TA-STOCH-1", "TA-DIV-1"]],
    ["Dəyişkənlik", ["TA-BB-1"]],
    ["Həcm", ["VOL-SPIKE-1", "VOL-OBV-1", "VOL-VWAP-1", "VOL-POC-1"]],
    ["Fibonacci", ["TA-FIB-1", "TA-FIB-2", "TA-FIB-EXT"]],
    ["Nəzəriyyələr (Dow, Elliott, Wyckoff)", ["TH-DOW-1", "TH-ELL-1", "TH-ELL-2", "TH-WYC-1"]],
    ["Price action / «Smart money»", ["PA-LIQ-1", "PA-BOS-1", "PA-OB-1"]],
    ["Bazarlar arası", ["IM-RATIO-1"]],
  ];
  const FCOL = { trend: "#3fb27f", "qırılma": "#ff9f43", "səviyyə": "#4ea1ff", "yalançı qırılma": "#ef476f",
    osilyator: "#c77dff", "dönüş fiquru": "#e0b84f", "bazarlar arası": "#2ec4b6", "həcm": "#a1887f" };
  const LAYERS = [["ema", "EMA 20/50/200"], ["bb", "Bollinger"], ["ich", "İçimoku"], ["fib", "Fibonacci"], ["piv", "Pivot"],
    ["sr", "Dəstək / müqavimət"], ["round", "Dəyirmi rəqəmlər"], ["zig", "Zirvə-dib (Dow, Elliott)"], ["tl", "Trend xətləri"],
    ["marks", "Qayda işarələri"]];
  const SUBS = [["none", "Alt panel yox"], ["rsi", "RSI"], ["macd", "MACD"], ["stoch", "Stoxastik"], ["adx", "ADX"], ["vol", "Həcm"]];

  const load = (k, d) => { try { const v = JSON.parse(localStorage.getItem("tst_ta_" + k)); return v ?? d; } catch (e) { return d; } };
  const save = (k, v) => { try { localStorage.setItem("tst_ta_" + k, JSON.stringify(v)); } catch (e) { /* fine */ } };
  let sym = load("sym", "XAU"), tf = load("tf", "1h"), cnt = load("cnt", 120);
  let lay = load("lay", { ema: true, bb: false, ich: false, fib: false, piv: false, sr: true, round: false, zig: true, tl: true, marks: true, sub: "rsi" });
  let off = new Set(load("off", []));          // rules switched off on the chart
  let data = null;

  function seg(el, items, cur, on) {
    el.innerHTML = items.map(([k, n]) => `<button class="${String(k) === String(cur) ? "on" : ""}" data-k="${esc(k)}">${esc(n)}</button>`).join("");
    el.querySelectorAll("button").forEach((b) => b.onclick = () => on(b.dataset.k));
  }
  function controls() {
    seg($("sym"), Object.entries(NAMES), sym, (k) => { sym = k; save("sym", k); controls(); fetchData(); });
    seg($("tf"), Object.entries(TFN), tf, (k) => { tf = k; save("tf", k); controls(); fetchData(); });
    seg($("cnt"), [[60, "60"], [120, "120"], [250, "250"]], cnt, (k) => { cnt = +k; save("cnt", cnt); controls(); draw(); });
    $("layers").innerHTML = LAYERS.map(([k, n]) => `<label class="chk"><input type="checkbox" data-l="${k}" ${lay[k] ? "checked" : ""}> ${esc(n)}</label>`).join("") +
      `<span class="seg" id="subs"></span>`;
    $("layers").querySelectorAll("input").forEach((i) => i.onchange = () => { lay[i.dataset.l] = i.checked; save("lay", lay); draw(); });
    seg($("subs"), SUBS, lay.sub, (k) => { lay.sub = k; save("lay", lay); controls(); draw(); });
  }

  function prevPeriod(cs) {          // pivots come from the previous trading day (the previous week on the daily chart)
    const key = (t) => tf === "1d" ? Math.floor((t + 7200 - 345600) / 604800) : Math.floor((t + 7200) / 86400);
    const last = key(cs[cs.length - 1].t);
    let k = null; const span = [];
    for (let i = cs.length - 1; i >= 0; i--) {
      const kk = key(cs[i].t);
      if (kk === last) continue;
      if (k === null) k = kk;
      if (kk !== k) break;
      span.push(cs[i]);
    }
    if (!span.length) return null;
    return { h: Math.max(...span.map((c) => c.h)), l: Math.min(...span.map((c) => c.l)), c: span[0].c };
  }

  function draw() {
    if (!data || !data.candles || !data.candles.length) return;
    const cs = data.candles, L = data.layers || {}, fam = {};
    (data.book || []).forEach((r) => { fam[r.id] = r; });
    const ext = {};
    if (lay.ich && L.ichimoku) {
      ext.cloud = { a: L.ichimoku.a, b: L.ichimoku.b };
      ext.lines = [{ v: L.ichimoku.tenkan, c: "#4ea1ff", w: 1 }, { v: L.ichimoku.kijun, c: "#ef476f", w: 1 }];
    }
    if (lay.zig && L.zig) ext.zig = L.zig;
    if (lay.tl && L.tl) ext.tl = L.tl.map((t) => ({ ...t, c: t.kind === "up" ? "#3ee08f" : "#ff5d6c" }));
    // a rule that stays on candle after candle (a trend state) is marked only where it starts: the chart stays readable
    const seen = new Set((data.fired || []).map((f) => f.rule + "|" + f.dir + "|" + f.i));
    if (lay.marks) ext.marks = (data.fired || []).filter((f) => !off.has(f.rule) && !seen.has(f.rule + "|" + f.dir + "|" + (f.i - 1))).map((f) => ({
      i: f.i, dir: f.dir, c: FCOL[(fam[f.rule] || {}).family] || "#e8b94a",
      label: ((fam[f.rule] || {}).name || f.rule) + (f.note ? ": " + f.note : "") }));
    ext.stoch = L.stoch; ext.adx = L.adx; ext.vol = L.vol;
    drawChart($("cv"), $("tip"), cs, null, tf, { show: Math.min(cnt, cs.length), ema: lay.ema, bb: lay.bb, fib: lay.fib,
      piv: lay.piv, sr: lay.sr, round: lay.round, sub: lay.sub, day: prevPeriod(cs), ext });
  }

  function nowBox() {
    const n = data.now;
    if (!n) { $("now").innerHTML = `<p class="note">${esc(data.note || "məlumat yoxdur")}</p>`; return; }
    const p = n.vote.p, dir = Math.abs(p - 0.5) < 0.01 ? "fikir yoxdur" : p > 0.5 ? "▲ yuxarı" : "▼ aşağı";
    const book = Object.fromEntries((data.book || []).map((r) => [r.id, r]));
    const j = n.judge.qaydalar, jl = j.live.nh ? j.live : j.history;
    const jc = n.judge.chartist, jcl = jc.live.nh ? jc.live : jc.history;
    const fams = Object.entries(n.families).map(([f, v]) => `<span class="pill" style="border-color:${FCOL[f] || "#888"}">${esc(f)} ${v > 0 ? "▲" : v < 0 ? "▼" : "·"}</span>`).join(" ");
    const rng = n.range ? `${n.range.lo80.toFixed(2)} – ${n.range.hi80.toFixed(2)} (80 %)` : "—";
    const ch = n.chartist;
    $("nowt").textContent = "son şam " + new Date(n.t * 1000).toLocaleString("en-GB", { timeZone: "America/New_York", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) + " NY";
    $("now").innerHTML = `<div class="tanow">
      <div><div class="big ${p > 0.5 ? "up" : p < 0.5 ? "down" : ""}">${dir} · ${pct(p)}</div>
        <p class="note">«Qaydalar» səsi (${TFN[tf]} proqnozuna gedir): ${esc(n.vote.basis)}</p>
        <p class="note">Hakim: ${jl.nh ? `${jl.nh} haldan ${pct(jl.hit_rate)} düz (hədd ${pct(jl.bar)}) · ${ST[jl.status] || esc(jl.status || "")}` : "hələ nəticə yoxdur"}
          · gözlənilən aralıq ${rng}</p></div>
      <div><p><b>Bazar rejimi:</b> ${esc(n.regime || "—")} (ADX ${n.adx ?? "—"})</p>
        <p><b>Son şamda fikirlər:</b> ${n.up} ▲ · ${n.down} ▼ ${fams || "<span class='note'>son şamda qayda işə düşməyib</span>"}</p>
        <ul class="tarules">${n.rules.map((r) => `<li><span style="color:${FCOL[(book[r.rule] || {}).family] || "#888"}">${r.dir > 0 ? "▲" : "▼"}</span> ${esc((book[r.rule] || {}).name || r.rule)} <span class="note">${esc(r.note || "")}</span></li>`).join("")}</ul></div>
      <div><p><b>Qrafik analitiki (AI):</b> ${ch ? `${pct(ch.p)} yuxarı · ${esc(ch.trend || "")}` : "fikri yoxdur"}</p>
        ${ch ? `<p class="note">${esc(ch.why || "")}</p><p class="note">Səviyyələr: ${esc(ch.levels || "—")} · Fiqur: ${esc(ch.pattern || "—")}</p>` : ""}
        <p class="note">Hakim: ${jcl.nh ? `${jcl.nh} haldan ${pct(jcl.hit_rate)} düz · ${ST[jcl.status] || esc(jcl.status || "")}` : "hələ nəticə yoxdur"}</p></div>
    </div>
    <p class="note">Bu, sübut olmayan fikirdir: AL / SAT yalnız Hakimin sübutu ilə göstərilir.</p>`;
  }

  function bookBox() {
    const by = Object.fromEntries((data.book || []).map((r) => [r.id, r]));
    const lastT = data.now ? data.now.t : null;
    const firingNow = new Set((data.fired || []).filter((f) => f.t === lastT).map((f) => f.rule));
    const count = {};
    (data.fired || []).forEach((f) => { count[f.rule] = (count[f.rule] || 0) + 1; });
    $("book").innerHTML = KINDS.map(([kind, ids]) => `<details class="takind" open><summary><b>${esc(kind)}</b> <span class="note">${ids.length} qayda</span></summary>` +
      ids.filter((id) => by[id]).map((id) => {
        const r = by[id], x = r.record, rr = x && x.rr;
        const adx = x && x.by_adx ? Object.entries(x.by_adx).map(([g, b]) => `${esc(g.split(" (")[0])} ${pct(b.hit_rate)}`).join(" · ") : "";
        return `<div class="tarule"><label class="chk"><input type="checkbox" data-r="${esc(id)}" ${off.has(id) ? "" : "checked"}>
            <i style="background:${FCOL[r.family] || "#888"}"></i> <b>${esc(r.name)}</b></label>
          ${firingNow.has(id) ? '<span class="pill on">indi işləyir</span>' : ""}
          <button class="tabtn" data-only="${esc(id)}">yalnız bu</button>
          <span class="note">${count[id] || 0} dəfə qrafikdə · ${x ? `${x.n} hal, ${pct(x.hit_rate)} düz, ${ST[x.status] || esc(x.status)}` : "hələ ölçülməyib"}
            ${rr ? ` · stop+hədəf: hədəfə ${pct(rr.target_share)}, ${rr.net_r >= 0 ? "+" : ""}${rr.net_r.toFixed(2)} R` : ""}${adx ? " · ADX: " + adx : ""}</span>
          <details><summary class="note">necə işləyir</summary><p class="note">${esc(r.how)}</p>
            <p class="note"><b>Siqnal:</b> ${esc(r.signal)} <b>Ləğv:</b> ${esc(r.void)}</p><p class="note"><b>Mənbə:</b> ${esc(r.source)}</p></details></div>`;
      }).join("") + "</details>").join("") +
      `<p class="note"><b>Sistematik ölçmə</b> (12-ci növ) ayrıca qayda deyil: Hakim yuxarıdakı hər qaydanı iki cür ölçür — növbəti şam
       və treyder kimi (stop 1 ATR, hədəf 2 ATR, xərcdən sonra R ilə), üç ADX rejimində ayrıca.</p>`;
    $("book").querySelectorAll("input[data-r]").forEach((i) => i.onchange = () => {
      i.checked ? off.delete(i.dataset.r) : off.add(i.dataset.r); save("off", [...off]); draw();
    });
    $("book").querySelectorAll("button[data-only]").forEach((b) => b.onclick = () => {
      off = new Set((data.book || []).map((r) => r.id).filter((id) => id !== b.dataset.only));
      save("off", [...off]); lay.marks = true; save("lay", lay); controls(); bookBox(); draw();
      $("wrapc").scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }
  $("allon").onclick = () => { off = new Set(); save("off", []); bookBox(); draw(); };
  $("alloff").onclick = () => { off = new Set((data && data.book || []).map((r) => r.id)); save("off", [...off]); bookBox(); draw(); };

  const home = $("wrapc").parentNode, after = $("wrapc").nextSibling;
  function setBig(on) {
    // the box has a blur filter, which would trap a fixed element inside it: the chart moves to <body> while big
    if (on) document.body.appendChild($("wrapc")); else home.insertBefore($("wrapc"), after);
    $("wrapc").classList.toggle("full", on);
    document.body.classList.toggle("noscroll", on);
    setTimeout(draw, 30);
  }
  $("big").onclick = () => setBig(true);
  $("small").onclick = () => setBig(false);
  addEventListener("keydown", (e) => { if (e.key === "Escape") setBig(false); });

  async function fetchData() {
    try {
      const r = await fetch(`/api/ta?symbol=${sym}&tf=${tf}`, { credentials: "same-origin" });
      if (!r.ok) return;
      data = await r.json();
    } catch (e) { return; }
    $("upd").textContent = "yeniləndi " + new Date().toLocaleTimeString("en-GB", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" }) + " NY";
    draw(); nowBox(); bookBox();
  }
  controls(); fetchData(); setInterval(fetchData, 60000);
})();
