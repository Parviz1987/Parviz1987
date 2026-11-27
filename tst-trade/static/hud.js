// The panel's forecasts table (owner 2026-11-26: one place for forecasts, no big empty boxes): 4 metals x 6 horizons,
// each cell the decision (AL / SAT / GÖZLƏ with the reason) and the 80 % range; a cell opens the forecast card with
// both ranges and every method. The system's state sits in the header. Sound and vibration on alarms and on a new
// AL / SAT, and a simple mode. Indication only: nothing here places an order.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const NAMES = { XAU: "Qızıl", XAG: "Gümüş", XPT: "Platin", XPD: "Palladium" };
  // 27.11 (owner: «artıqları çıxar»): three horizons, the range first (the proven part); AL / SAT only with proof
  const DESKS = [["1h", "1 saat"], ["1d", "1 gün"], ["1w", "1 həftə"]];
  const pref = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } };
  const grid = $("fgrid");
  if (!grid) return;

  let state = "SAKİT", lastCalls = null;
  const ranges = {};          // metal -> horizon -> {lo50, hi50, lo80, hi80, target_t, direction}
  const rf = (v) => v == null ? "—" : v >= 1000 ? v.toFixed(0) : v >= 100 ? v.toFixed(1) : v.toFixed(2);
  const curSym = () => { try { return typeof sym === "string" ? sym : "XAU"; } catch (e) { return "XAU"; } };

  // ---------- sound and vibration (off by default; the browser allows sound only after a tap) ----------
  let audio = null;
  function chime(alarm) {
    if (pref("tst_sound") !== "1") return;
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      const notes = alarm ? [880, 660, 880] : [523, 784];
      notes.forEach((f, i) => {
        const o = audio.createOscillator(), gn = audio.createGain();
        o.type = "sine"; o.frequency.value = f; o.connect(gn); gn.connect(audio.destination);
        const t0 = audio.currentTime + i * 0.18;
        gn.gain.setValueAtTime(0.0001, t0); gn.gain.exponentialRampToValueAtTime(0.25, t0 + 0.02);
        gn.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.16); o.start(t0); o.stop(t0 + 0.17);
      });
    } catch (e) { /* no audio */ }
    if (navigator.vibrate) navigator.vibrate(alarm ? [180, 90, 180, 90, 180] : [120, 60, 120]);
  }

  // ---------- the forecasts table ----------
  async function loadRanges() {
    await Promise.all(Object.keys(NAMES).map(async (s) => {
      try {
        const r = await fetch(`/api/results?symbol=${s}&horizon=1h`, { credentials: "same-origin" });
        if (!r.ok) return;
        const d = await r.json();
        ranges[s] = Object.fromEntries((d.expect || []).map((e) => [e.horizon, e]));
      } catch (e) { /* the cell shows — */ }
    }));
  }
  let lastD = null;
  async function load() {
    let d;
    try {
      const r = await fetch("/api/decision", { credentials: "same-origin" });
      if (!r.ok) return;
      d = await r.json();
    } catch (e) { return; }
    lastD = d;
    const st = d.state || {};
    const prev = state;
    state = st.state || "SAKİT";
    const mod = st.mod || {};
    $("hstate").className = "hstate " + state;
    $("hstate").textContent = state;
    $("hstate").title = `Sistemin vəziyyəti · oyanıqlıq ${mod.arousal == null ? "—" : Math.round(mod.arousal * 100) + "%"} · fikir ayrılığı ` +
      `${mod.uncertainty == null ? "—" : Math.round(mod.uncertainty * 100)} · qızılda sürpriz ${mod.surprise && mod.surprise.XAU != null ? mod.surprise.XAU.toFixed(1) : "—"}`;
    $("hwhy").textContent = st.why || "";
    draw();
    const calls = [];
    Object.entries(d.metals || {}).forEach(([s, x]) => x.desks.forEach((c) => { if (c.call !== "GÖZLƏ") calls.push(`${s}:${c.horizon}:${c.call}`); }));
    const newCall = lastCalls && calls.some((c) => !lastCalls.includes(c));
    if ((prev !== "HƏYƏCAN" && state === "HƏYƏCAN" && lastCalls !== null) || newCall) chime(!newCall);
    lastCalls = calls;
  }
  function draw() {
    if (!lastD) return;
    const ms = lastD.metals || {}, cur = curSym();
    grid.innerHTML = `<div class="fg-h"></div>` + DESKS.map(([, n]) => `<div class="fg-h">${n}</div>`).join("") +
      Object.keys(NAMES).map((s) => {
        const x = ms[s] || { desks: [], gate: { open: true, reasons: [] } };
        const gt = x.gate.open ? "risk qapısı açıq" : "risk qapısı bağlı: " + (x.gate.reasons[0] || "");
        const row = DESKS.map(([h]) => {
          const c = x.desks.find((k) => k.horizon === h) || { call: "GÖZLƏ", why: "hesablanır" };
          const e = (ranges[s] || {})[h];
          const dir = e && e.direction ? (e.direction.up ? "▲" : "▼") : "";
          return `<div class="fc ${c.call}${s === cur ? " cur" : ""}" data-m="${s}" data-h="${h}" data-n="${DESKS.find((k) => k[0] === h)[1]}" role="button" tabindex="0"
            title="${esc(NAMES[s] + " · " + (c.name || h) + ": " + (c.why || "") + " · toxunun: ətraflı")}">
            <b>${e && e.lo80 != null ? rf(e.lo80) + " – " + rf(e.hi80) : "—"}</b>${c.call !== "GÖZLƏ" ? `<span class="${c.call}">${dir} ${c.call}</span>` : ""}</div>`;
        }).join("");
        return `<button type="button" class="fg-m${s === cur ? " cur" : ""}" data-sel="${s}" title="${esc(gt)} · toxunun: qrafik bu metala keçir"><i class="${x.gate.open ? "ok" : "shut"}"></i>${NAMES[s]}</button>${row}`;
      }).join("");
    const live = [];
    Object.entries(ms).forEach(([s, x]) => x.desks.forEach((c) => { if (c.call !== "GÖZLƏ") live.push(`${NAMES[s]} ${c.name || c.horizon}: ${c.call}`); }));
    $("fcdec").innerHTML = live.length ? `<b>AL / SAT:</b> ${live.map(esc).join(" · ")}` :
      `<b>AL / SAT yoxdur</b> <span class="note">— hələ heç bir metalda və müddətdə Hakimin sübutu yoxdur (sübut olanda burada yazılacaq)</span>`;
    $("fcupd").textContent = "yeniləndi " + new Date().toLocaleTimeString("az", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" }) + " NY";
  }

  // ---------- Block 16: the frozen forecast card (opens on a decision cell) ----------
  const CARD_H = { "15m": "1h", "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1d", "1mo": "1d" };
  const HN = { "1h": "1 saat", "4h": "4 saat", "1d": "1 gün" };
  const nyTime = (t) => new Date(t * 1000).toLocaleString("az-Latn-AZ", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
  const RES = { "düz": "✅ düz çıxdı", "səhv": "❌ səhv çıxdı", "istiqamətsiz": "· istiqamət yox idi", "ölçülmədi": "· ölçülmədi (bazar bağlı)" };
  async function openCard(sym, desk) {
    const h = CARD_H[desk] || "1h";
    let d;
    try { const r = await fetch(`/api/cards?symbol=${sym}&limit=60`, { credentials: "same-origin" }); if (!r.ok) return; d = await r.json(); } catch (e) { return; }
    const mine = d.cards.filter((c) => c.horizon === h);
    const c = mine[0];
    const pct = (p) => (p == null ? "—" : Math.round(p * 100) + " %");
    const row = (k, v) => `<div class="cr"><span>${k}</span><span>${v}</span></div>`;
    const DN = Object.fromEntries(DESKS);
    const dc = ((lastD && lastD.metals[sym]) || { desks: [] }).desks.find((k) => k.horizon === desk) || {};
    const e = (ranges[sym] || {})[desk];
    let html = `<h3>${NAMES[sym]} · ${DN[desk] || desk}</h3><div class="cgrid">` +
      row("Qərar", `<b>${esc(dc.call || "GÖZLƏ")}</b> · ${esc(dc.why || "—")}`) +
      row("50 % aralıq", e && e.lo50 != null ? `${rf(e.lo50)} – ${rf(e.hi50)}` : "—") +
      row("80 % aralıq", e && e.lo80 != null ? `${rf(e.lo80)} – ${rf(e.hi80)}` : "—") +
      row("Yoxlanır", e && e.target_t ? nyTime(e.target_t) + " NY" : "—") +
      row("İstiqamət", e && e.direction ? `${e.direction.up ? "▲ yuxarı" : "▼ aşağı"} ${pct(e.direction.p)} · ${esc(e.direction.method)}` : "göstərilmir: Hakimin sübutu yoxdur") +
      `</div><details class="meth" id="cardMeth"><summary>Bütün üsullar</summary><p class="note">yüklənir…</p></details>
      <h3 class="sub">Strateqin kartı (${HN[h]})</h3>`;
    if (desk !== h) html += `<p class="note">Bu müddət üçün strateqin kartı yoxdur; ən yaxın müddət (${HN[h]}) göstərilir.</p>`;
    if (!c) {
      html += `<p class="note">Hələ kart yoxdur: Strateq növbəti dəfə işləyəndə yaranacaq.</p>`;
    } else {
      const dir = Math.abs(c.p - 0.5) < 0.02 ? "istiqamət yox (0.5)" : c.p > 0.5 ? "yuxarı" : "aşağı";
      html += `<div class="cgrid">` +
        row("Alət və an", `${sym} · Capital.com · ${nyTime(c.known_ts)} NY · qiymət ${c.price0 == null ? "—" : c.price0.toFixed(2)}`) +
        row("Müddət", `${HN[h]} (${nyTime(c.known_ts + { "1h": 3600, "4h": 14400, "1d": 86400 }[h])} NY-dək)`) +
        row("Əsas ssenari", `${esc(dir)} · ${esc(c.scenario || "—")}`) +
        row("Ehtimal (yuxarı)", `${pct(c.p)} beyin · ${c.p_cal == null ? "kalibrlənməyib (ölçülməyib)" : pct(c.p_cal) + " kalibrlənmiş"}`) +
        row("80 % aralıq", c.lo80 == null ? "—" : `${c.lo80.toFixed(2)} – ${c.hi80.toFixed(2)} · real tutma ${pct(c.cover80)}`) +
        row("Əks ssenari", esc(c.counter || "—")) +
        row("Zəifləmə şərti", esc(c.invalidation || "—")) +
        row("Məlumat keyfiyyəti", c.quality.length ? esc(c.quality.join(" · ")) : "tam") +
        row("Növbəti yenilənmə", esc(c.next_update || "—")) +
        row("Versiya", `kod ${esc(c.version)} · ${esc(c.model)} · təlimat ${esc(c.prompt_hash)} · ${esc(c.chain || "")}`) +
        row("Nəticə", c.result ? `${RES[c.result] || esc(c.result)}${c.price1 ? " · qiymət " + c.price1.toFixed(2) : ""}` : "gözlənilir") +
        `</div>`;
    }
    const s = d.summary[`strateq:${h}`] || {};
    html += `<p class="note">Strateq ${HN[h]} kartları (30 gün): düz ${s["düz"] || 0}, səhv ${s["səhv"] || 0}, istiqamətsiz ${s["istiqamətsiz"] || 0}. Bu, ilk baxışdır; sübut qaydaları Hakimdədir.</p>`;
    if (mine.length > 1) html += `<div class="chist">` + mine.slice(1, 8).map((x) => `<div>${nyTime(x.known_ts)} · ${pct(x.p)} · ${x.result ? (RES[x.result] || esc(x.result)) : "gözlənilir"}</div>`).join("") + `</div>`;
    $("cardBody").innerHTML = html;
    $("cardDlg").showModal();
    // every method's view on this horizon, only when asked (the forecasts reply is large)
    $("cardMeth").addEventListener("toggle", async () => {
      if (!$("cardMeth").open || $("cardMeth").dataset.done) return;
      try {
        const f = await (await fetch(`/api/forecasts?symbol=${sym}`, { credentials: "same-origin" })).json();
        const c = f.cards.find((k) => k.horizon === desk);
        $("cardMeth").dataset.done = "1";
        $("cardMeth").innerHTML = `<summary>Bütün üsullar</summary>` + (c && c.methods.length ? `<table><tr><th>Üsul</th><th>Yuxarı ehtimalı</th><th>Əsas</th></tr>` +
          c.methods.map((m) => `<tr><td>${esc(f.method_names[m.method])}</td><td class="n">${(m.p_up * 100).toFixed(1)} %</td><td>${esc(m.basis)}</td></tr>`).join("") + "</table>"
          : "<p class='note'>Hələ proqnoz yoxdur.</p>");
        $("cardMeth").open = true;
      } catch (err) { /* stays «yüklənir» */ }
    });
  }
  grid.addEventListener("click", (ev) => {
    const c = ev.target.closest(".fc[data-m]"); if (c) { openCard(c.dataset.m, c.dataset.h); return; }
    const m = ev.target.closest("[data-sel]");      // a metal's name: the panel (tiles, chart) moves to that metal
    if (m) { const t = document.querySelector(`.tile[data-s="${m.dataset.sel}"]`); if (t) t.click(); setTimeout(draw, 50); }
  });
  grid.addEventListener("keydown", (ev) => { const c = ev.target.closest(".fc[data-m]"); if (c && (ev.key === "Enter" || ev.key === " ")) { ev.preventDefault(); openCard(c.dataset.m, c.dataset.h); } });
  document.addEventListener("click", (ev) => { if (ev.target.closest(".tile")) setTimeout(draw, 50); });

  // ---------- the sound button (the simple mode left 27.11: the panel itself is simple now) ----------
  document.body.classList.remove("simple");
  function setSound(on) {
    $("bsound").textContent = on ? "🔔 Səs açıq" : "🔕 Səs";
    $("bsound").setAttribute("aria-pressed", String(on));
    pref("tst_sound", on ? "1" : "0");
    if (on) chime(false);                               // the tap unlocks sound and lets you hear it once
  }
  $("bsound").onclick = () => setSound(pref("tst_sound") !== "1");
  $("bsound").textContent = pref("tst_sound") === "1" ? "🔔 Səs açıq" : "🔕 Səs";
  loadRanges().then(load);
  setInterval(load, 20000);
  setInterval(() => loadRanges().then(draw), 60000);
})();
