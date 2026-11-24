// Bilik kitabı: our rules, each with its method, signal, void condition, source and the Judge's record per timeframe.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const NAMES = { XAU: "Qızıl", XAG: "Gümüş", XPT: "Platin", XPD: "Palladium" };
  const ST = { "sübut": "✅ sübut", yox: "❌ yox", "zəif": "⚠️ zəif (coin-dən pis)", az: "⏳ az" };
  let area = "Texniki", data = null;
  try { area = localStorage.getItem("tst_bilik") || area; } catch (e) { /* fine */ }
  function render() {
    if (!data) return;
    $("areas").innerHTML = data.areas.map((a) => `<button class="${a === area ? "on" : ""}" data-a="${esc(a)}">${esc(a)}</button>`).join("");
    document.querySelectorAll("#areas button").forEach((b) => b.onclick = () => {
      area = b.dataset.a; try { localStorage.setItem("tst_bilik", area); } catch (e) { /* fine */ } render();
    });
    const rec = data.records.rules || {};
    $("rules").innerHTML = data.rules.filter((r) => r.area === area).map((r) => {
      const rr = rec[r.id] || {};
      const cells = ["1h", "4h", "1d"].map((tf) => rr[tf]
        ? `<span class="rtf"><b>${tf}</b> ${Math.round(rr[tf].hit_rate * 100)} % · ${rr[tf].n} dəfə · xərcdən sonra ${(rr[tf].net_avg * 100).toFixed(3)} % · ${ST[rr[tf].status] || rr[tf].status}</span>` : "").join("");
      return `<div class="rule"><div class="rh"><b>${esc(r.id)}</b> ${esc(r.name)}
          <span class="note">${r.detector ? "kod özü tapır, Hakim ölçür" : "analitik faktlardan tətbiq edir"}</span></div>
        <div class="rr"><span>Üsul</span><span>${esc(r.how)}</span></div>
        <div class="rr"><span>Siqnal</span><span>${esc(r.signal)}</span></div>
        <div class="rr"><span>Ləğv</span><span>${esc(r.void)}</span></div>
        <div class="rr"><span>Mənbə</span><span>${esc(r.source)}</span></div>
        ${cells ? `<div class="rr"><span>Hakim</span><span>${cells}</span></div>` : ""}</div>`;
    }).join("");
    const act = [];
    Object.entries(data.active).forEach(([s, xs]) => xs.forEach((x) => act.push({ s, ...x })));
    $("active").innerHTML = act.length ? `<table class="sc"><tr><th>Metal</th><th>Çərçivə</th><th>Qayda</th><th>İstiqamət</th><th>Nə görüldü</th></tr>` +
      act.map((x) => `<tr><td>${NAMES[x.s] || esc(x.s)}</td><td class="c">${esc(x.tf)}</td><td>${esc(x.rule)}</td>
        <td class="c ${x.dir > 0 ? "up" : "down"}">${x.dir > 0 ? "▲ yuxarı" : "▼ aşağı"}</td><td class="note">${esc(x.note)}</td></tr>`).join("") + "</table>"
      : "<p class='note'>Hələ siqnal yoxdur: qaydalar 15 dəqiqədə bir yoxlanır.</p>";
    $("props").innerHTML = data.proposals.length ? `<table class="sc"><tr><th>Vaxt</th><th>Təklif</th><th>Status</th></tr>` +
      data.proposals.map((p) => `<tr><td class="mut">${new Date(p.ts * 1000).toLocaleDateString("az")}</td><td>${esc(p.text)}</td><td>${esc(p.status)}</td></tr>`).join("") + "</table>"
      : "<p class='note'>Hələ təklif yoxdur.</p>";
    $("ver").textContent = "versiya " + data.version + " · hədd p < " + (data.records.bar || 0).toExponential(1);
  }
  async function load() {
    try { const r = await fetch("/api/bilik", { credentials: "same-origin" }); if (!r.ok) return; data = await r.json(); } catch (e) { return; }
    render();
  }
  load(); setInterval(load, 300000);
})();
