// Bloklar: the organs of the system — each block's voice now, its methods with their views and the Judge's record,
// the evidence it rests on and what is still missing. Read-only.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const pct = (v) => (v == null ? "—" : Math.round(v * 100) + " %");
  const ST = { "sübut": "✅ sübut", yox: "❌ yox", "zəif": "⚠️ zəif", az: "⏳ az", "xərc": "💸 xərc", bazis: "bazis" };
  const NAMES = { XAU: "Qızıl", XAG: "Gümüş", XPT: "Platin", XPD: "Palladium" };
  const HZ = { "15m": "15 dəq", "1h": "1 saat", "4h": "4 saat", "1d": "1 gün", "1w": "1 həftə", "1mo": "1 ay" };
  const load = (k, d) => { try { return JSON.parse(localStorage.getItem("tst_bl_" + k)) ?? d; } catch (e) { return d; } };
  const save = (k, v) => { try { localStorage.setItem("tst_bl_" + k, JSON.stringify(v)); } catch (e) { /* fine */ } };
  let sym = load("sym", "XAU"), hz = load("hz", "1h");
  function seg(el, items, cur, on) {
    el.innerHTML = Object.entries(items).map(([k, n]) => `<button class="${k === cur ? "on" : ""}" data-k="${k}">${esc(n)}</button>`).join("");
    el.querySelectorAll("button").forEach((b) => b.onclick = () => on(b.dataset.k));
  }
  function lean(p) {
    if (p == null) return '<span class="note">fikir yoxdur</span>';
    const d = Math.abs(p - 0.5) < 0.01 ? "·" : p > 0.5 ? "▲" : "▼";
    return `<b class="${p > 0.5 ? "up" : p < 0.5 ? "down" : ""}">${d} ${pct(p)}</b>`;
  }
  function render(d) {
    $("comb").innerHTML = Object.values(d.combiners || {}).length ? `<p>${Object.values(d.combiners).map((c) => `${esc(c.name)}: ${lean(c.p)}`).join(" · ")}</p>` : "";
    $("blocks").innerHTML = d.blocks.map((b) => `<section class="box"><h2>${esc(b.name)} <span class="sp"></span>
        <span>blokun səsi: ${b.on_desk ? lean(b.voice) : '<span class="note">bu üfüqdə üsulu yoxdur</span>'}</span>
        ${b.page ? `<a class="tabtn" href="${b.page}">aç →</a>` : ""}</h2>
      <p class="note"><b>Oxuyur:</b> ${esc(b.reads)}${b.ai ? ` · <b>AI:</b> ${esc(b.ai)}` : ""}</p>
      ${b.methods.length ? `<div class="tbl"><table class="sc"><tr><th>Üsul</th><th>İndi</th><th>Hakim</th><th>Niyə</th></tr>` +
        b.methods.map((m) => `<tr><td>${esc(m.name)}</td><td class="c">${lean(m.p)}</td>
          <td class="c">${m.record && m.record.nh ? `${m.record.nh} hal, ${pct(m.record.hit_rate)} (hədd ${pct(m.record.bar)}) · ${ST[m.record.status] || esc(m.record.status)} <span class="note">${esc(m.record_mode)}</span>` : '<span class="note">hələ yox</span>'}</td>
          <td class="note">${esc(m.basis || "")}</td></tr>`).join("") + "</table></div>" : ""}
      <p class="note"><b>Nəyə əsaslanır:</b> ${esc(b.evidence)}</p>
      <p class="note"><b>Çatmayan:</b> ${esc(b.missing)}</p></section>`).join("");
    $("support").innerHTML = d.support.map((s) => `<p><b>${esc(s.name)}:</b> <span class="note">${esc(s.does)}</span></p>`).join("");
    $("upd").textContent = "yeniləndi " + new Date().toLocaleTimeString("en-GB", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" }) + " NY";
  }
  async function go() {
    seg($("sym"), NAMES, sym, (k) => { sym = k; save("sym", k); go(); });
    seg($("hz"), HZ, hz, (k) => { hz = k; save("hz", k); go(); });
    try { const r = await fetch(`/api/blocks?symbol=${sym}&horizon=${hz}`, { credentials: "same-origin" }); if (r.ok) render(await r.json()); } catch (e) { /* offline */ }
  }
  go(); setInterval(go, 120000);
})();
