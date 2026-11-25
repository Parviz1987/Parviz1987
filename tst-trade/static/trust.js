// Etibar işığı: one light and one sentence per analyst (owner 2026-11-24: the raw numbers confused him).
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  async function load() {
    if (!$("trustHead")) return;
    let d;
    try { const r = await fetch("/api/trust", { credentials: "same-origin" }); if (!r.ok) return; d = await r.json(); } catch (e) { return; }
    $("trustHead").textContent = d.head;
    $("trustList").innerHTML = d.items.map((x) => `<div class="tr-row"><span class="tr-l">${esc(d.legend[x.light])}</span><span>${esc(x.text)}</span></div>`).join("")
      || "<p class='note'>Hələ yoxlanmış fikir yoxdur.</p>";
  }
  load();
  setInterval(load, 300000);
})();
