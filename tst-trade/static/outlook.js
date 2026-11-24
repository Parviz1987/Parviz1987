// «Sabah üçün proqnoz» (owner 2026-11-24): per metal the 1-day range, the three voices on direction and their records.
// Indication only, and honest about proof: a lean is shown as a lean, never as a proven forecast.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const NAMES = { XAU: "Qızıl", XAG: "Gümüş", XPT: "Platin", XPD: "Palladium" };
  const pct = (p) => (p == null ? "—" : Math.round(p * 100) + " %");
  const px = (v) => (v == null ? "—" : v >= 100 ? v.toFixed(2) : v.toFixed(3));
  const ny = (t) => new Date(t * 1000).toLocaleString("az-Latn-AZ", { timeZone: "America/New_York", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  const dirWord = (p) => (p == null ? "—" : Math.abs(p - 0.5) < 0.03 ? "fikir yox" : p > 0.5 ? "yuxarı" : "aşağı");
  const PROOF = { "sübut": "✅ sübut var", yox: "❌ istiqamət sübutu yoxdur", az: "⏳ hələ az yoxlanıb" };
  async function load() {
    let d;
    try { const r = await fetch("/api/outlook", { credentials: "same-origin" }); if (!r.ok) return; d = await r.json(); } catch (e) { return; }
    if (!$("outlook")) return;
    $("olnote").textContent = "yeniləndi " + ny(d.ts) + " NY";
    $("outlook").innerHTML = d.metals.map((m) => {
      const s = m.strateq, t = m.terazi, v = m.vote, rg = m.range;
      const cls = m.lean_dir > 0 ? "up" : m.lean_dir < 0 ? "down" : "mut";
      const arrow = (m.lean_dir || m.weak_dir) > 0 ? "▲ " : (m.lean_dir || m.weak_dir) < 0 ? "▼ " : "";
      return `<div class="olc">
        <div class="olh"><b>${NAMES[m.symbol]}</b><span class="ol-lean ${cls}">${arrow}${esc(m.lean)}</span></div>
        <div class="note">${esc(m.agree)} · ${PROOF[m.proof] || esc(m.proof)}</div>
        <div class="olr"><span>Aralıq (80 %)</span><span>${rg ? px(rg.lo80) + " – " + px(rg.hi80) + ` <span class="note">real tutma ${pct(rg.cover80)}</span>` : "—"}</span></div>
        <div class="olr"><span>Aralıq (50 %)</span><span>${rg ? px(rg.lo50) + " – " + px(rg.hi50) : "—"}</span></div>
        <div class="olr"><span>Strateq (AI)</span><span>${s ? `${dirWord(s.p)} ${pct(s.p)}${s.calibrated ? " (kalibrli)" : ""} <span class="note">· indiyə qədər: düz ${s.record.right}, səhv ${s.record.wrong}</span>` : "kart hələ yoxdur"}</span></div>
        ${s ? `<div class="olw"><b>Səbəb:</b> ${esc(s.scenario || "—")}</div>
        <div class="olw"><b>Əks ssenari:</b> ${esc(s.counter || "—")}</div>
        <div class="olw"><b>Fikri zəiflədər:</b> ${esc(s.invalidation || "—")}</div>
        <div class="olw note">Növbəti yenilənmə: ${esc(s.next_update || "—")} · ${ny(s.ts)} NY</div>` : ""}
        <div class="olr"><span>Tərəzi (Hakim)</span><span>${t ? (String(t.basis || "").startsWith("çəkilər yoxdur") ? `<span class="note">Hakim hələ heç bir analitikə güvənmir</span>` : `${dirWord(t.p)} ${pct(t.p)} <span class="note">· ${esc(t.basis || "")}</span>`) : "—"}</span></div>
        <div class="olr"><span>Analitiklərin səsi</span><span>▲ ${v.up} · ▼ ${v.down}</span></div>
      </div>`;
    }).join("");
  }
  load();
  setInterval(load, 120000);
})();
