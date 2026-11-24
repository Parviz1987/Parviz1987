// The panel's HUD (owner 2026-11-24, Radar Gold brief): a live core that breathes with the system's state, the
// decision strip (4 metals x 6 horizons: AL / SAT / GÖZLƏ with the reason), a simple mode, and optional sound and
// vibration on alarms and on a new AL / SAT. Indication only: nothing here places an order.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const NAMES = { XAU: "Qızıl", XAG: "Gümüş", XPT: "Platin", XPD: "Palladium" };
  const DESKS = [["15m", "15 dəq"], ["1h", "1 saat"], ["4h", "4 saat"], ["1d", "1 gün"], ["1w", "1 həftə"], ["1mo", "1 ay"]];
  const ST_COL = { "SAKİT": [56, 200, 255], "DİQQƏT": [240, 181, 74], "HƏYƏCAN": [255, 93, 108] };
  const pref = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } };
  const hud = $("hud");
  if (!hud) return;

  let state = "SAKİT", gates = {}, lastCalls = null, pulseAt = 0;

  // ---------- the core: a particle sphere with the four metals orbiting (green = gate open, amber = closed) ----------
  const cv = $("core"), cx = cv.getContext("2d");
  const PTS = Array.from({ length: 260 }, (_, i) => {
    const y = 1 - (i / 259) * 2, r = Math.sqrt(1 - y * y), a = i * 2.399963;
    return [Math.cos(a) * r, y, Math.sin(a) * r];
  });
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  function frame(tms) {
    const w = cv.clientWidth, h = cv.clientHeight, dpr = devicePixelRatio || 1;
    if (cv.width !== Math.round(w * dpr)) { cv.width = w * dpr; cv.height = h * dpr; }
    cx.setTransform(dpr, 0, 0, dpr, 0, 0); cx.clearRect(0, 0, w, h);
    const t = still ? 0 : tms / 1000, col = ST_COL[state] || ST_COL["SAKİT"];
    const beat = state === "HƏYƏCAN" ? 0.5 + 0.5 * Math.sin(t * 6) : state === "DİQQƏT" ? 0.3 + 0.3 * Math.sin(t * 2.5) : 0.15;
    const flash = Math.max(0, 1 - (performance.now() - pulseAt) / 1200);
    const ox = w / 2, oy = h / 2, R = Math.min(w, h) * 0.3 * (1 + 0.04 * beat + 0.08 * flash);
    const g = cx.createRadialGradient(ox, oy, R * 0.1, ox, oy, R * 1.9);
    g.addColorStop(0, `rgba(${col},${0.25 + 0.25 * beat + 0.3 * flash})`); g.addColorStop(1, "rgba(0,0,0,0)");
    cx.fillStyle = g; cx.beginPath(); cx.arc(ox, oy, R * 1.9, 0, 7); cx.fill();
    const spin = t * (state === "HƏYƏCAN" ? 0.9 : state === "DİQQƏT" ? 0.5 : 0.25), tilt = 0.4;
    for (const [px, py, pz] of PTS) {
      const x = px * Math.cos(spin) - pz * Math.sin(spin), z0 = px * Math.sin(spin) + pz * Math.cos(spin);
      const y = py * Math.cos(tilt) - z0 * Math.sin(tilt), z = py * Math.sin(tilt) + z0 * Math.cos(tilt);
      const a = 0.15 + 0.85 * (z + 1) / 2;
      cx.fillStyle = `rgba(${col},${a})`; cx.beginPath(); cx.arc(ox + x * R, oy + y * R, 0.5 + a * 1.2, 0, 7); cx.fill();
    }
    Object.keys(NAMES).forEach((s, i) => {
      const a = t * 0.6 + i * Math.PI / 2, rx = Math.min(R * 1.45, w / 2 - 26), ry = R * 0.55;
      const X = ox + Math.cos(a) * rx, Y = oy + Math.sin(a) * ry, open = gates[s] !== false;
      cx.fillStyle = open ? "#3ee08f" : "#f0b54a"; cx.shadowColor = cx.fillStyle; cx.shadowBlur = 8;
      cx.beginPath(); cx.arc(X, Y, 3.2, 0, 7); cx.fill(); cx.shadowBlur = 0;
      cx.fillStyle = "rgba(232,238,252,.75)"; cx.font = "9px ui-monospace,monospace";
      cx.fillText(s, X > ox ? X - 24 : X + 5, Y + 3);              // the label always stays inside the core
    });
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

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

  // ---------- decision strip ----------
  async function load() {
    let d;
    try {
      const r = await fetch("/api/decision", { credentials: "same-origin" });
      if (!r.ok) return;
      d = await r.json();
    } catch (e) { return; }
    const ms = d.metals || {}, st = d.state || {};
    const prev = state;
    state = st.state || "SAKİT";
    gates = Object.fromEntries(Object.entries(ms).map(([s, x]) => [s, x.gate.open]));
    const mod = st.mod || {};
    $("hstate").className = "hstate " + state;
    $("hstate").textContent = state;
    $("hwhy").textContent = st.why || "";
    $("hmod").innerHTML = `<span title="Son saatın hərəkəti son 60 günə nisbətən">oyanıqlıq <b>${mod.arousal == null ? "—" : Math.round(mod.arousal * 100) + "%"}</b></span>
      <span title="Strateq, ikinci beyin və müzakirə nə qədər razı deyil">fikir ayrılığı <b>${mod.uncertainty == null ? "—" : Math.round(mod.uncertainty * 100)}</b></span>
      <span title="Qızıl öz 1 saatlıq proqnozumuzdan nə qədər uzaqdır (|z| > 1 = koridordan çıxıb)">sürpriz <b>${mod.surprise && mod.surprise.XAU != null ? mod.surprise.XAU.toFixed(1) : "—"}</b></span>`;
    const calls = [];
    $("hgrid").innerHTML = `<div class="hg-h"></div>` + DESKS.map(([, n]) => `<div class="hg-h">${n}</div>`).join("") +
      Object.keys(NAMES).map((s) => {
        const x = ms[s] || { desks: [], gate: { open: true, reasons: [] } };
        const row = DESKS.map(([h]) => {
          const c = x.desks.find((k) => k.horizon === h) || { call: "GÖZLƏ", why: "hesablanır" };
          if (c.call !== "GÖZLƏ") calls.push(`${s}:${h}:${c.call}`);
          return `<div class="hg ${c.call}" data-m="${s}" data-h="${h}" role="button" tabindex="0" title="${esc(NAMES[s] + " · " + (c.name || h) + ": " + (c.why || "") + " · toxun: proqnoz kartı")}">${c.call === "GÖZLƏ" ? "·" : c.call}</div>`;
        }).join("");
        const gt = x.gate.open ? "açıq" : "bağlı: " + (x.gate.reasons[0] || "");
        return `<div class="hg-m" title="Risk qapısı ${esc(gt)}"><i class="${x.gate.open ? "ok" : "shut"}"></i>${NAMES[s]}</div>${row}`;
      }).join("");
    const newCall = lastCalls && calls.some((c) => !lastCalls.includes(c));
    if ((prev !== "HƏYƏCAN" && state === "HƏYƏCAN" && lastCalls !== null) || newCall) { pulseAt = performance.now(); chime(!newCall); }
    lastCalls = calls;
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
    let html = `<h3>${NAMES[sym]} · ${HN[h]} · proqnoz kartı</h3>`;
    if (desk !== h) html += `<p class="note">Bu müddət (${esc(desk)}) üçün beyin kartı yoxdur; ən yaxın müddət göstərilir. Qərar lentindəki xana Hakimin metodlarından gəlir.</p>`;
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
  }
  $("hgrid").addEventListener("click", (ev) => { const c = ev.target.closest(".hg[data-m]"); if (c) openCard(c.dataset.m, c.dataset.h); });
  $("hgrid").addEventListener("keydown", (ev) => { const c = ev.target.closest(".hg[data-m]"); if (c && (ev.key === "Enter" || ev.key === " ")) { ev.preventDefault(); openCard(c.dataset.m, c.dataset.h); } });

  // ---------- simple mode and sound buttons ----------
  function setSimple(on) {
    document.body.classList.toggle("simple", on);
    $("bsimple").textContent = on ? "Tam görünüş" : "Sadə rejim";
    $("bsimple").setAttribute("aria-pressed", String(on));
    pref("tst_simple", on ? "1" : "0");
    if (!on) window.dispatchEvent(new Event("resize"));
  }
  function setSound(on) {
    $("bsound").textContent = on ? "🔔 Səs açıq" : "🔕 Səs";
    $("bsound").setAttribute("aria-pressed", String(on));
    pref("tst_sound", on ? "1" : "0");
    if (on) chime(false);                               // the tap unlocks sound and lets you hear it once
  }
  $("bsimple").onclick = () => setSimple(!document.body.classList.contains("simple"));
  $("bsound").onclick = () => setSound(pref("tst_sound") !== "1");
  setSimple(pref("tst_simple") === "1");
  $("bsound").textContent = pref("tst_sound") === "1" ? "🔔 Səs açıq" : "🔕 Səs";
  load();
  setInterval(load, 20000);
})();
