// Bilik kitabı: our rules, each with its method, signal, void condition, source and the Judge's record per timeframe.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const NAMES = { XAU: "Qızıl", XAG: "Gümüş", XPT: "Platin", XPD: "Palladium" };
  const ST = { "sübut": "✅ sübut", yox: "❌ yox", "zəif": "⚠️ zəif (coin-dən pis)", az: "⏳ az", "namizəd": "🏁 namizəd (son sınaq gözlənir)" };
  let area = "Texniki", data = null;
  const OPEN = new Set();
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
        ? `<span class="rtf"><b>${tf}</b> ${Math.round(rr[tf].hit_rate * 100)} % · ${rr[tf].n} dəfə · xərcdən sonra ${(rr[tf].net_avg * 100).toFixed(3)} % · ${ST[rr[tf].status] || rr[tf].status}
            ${rr[tf].rr ? `<span class="note">· stop+hədəf: hədəfə çatdı ${Math.round(rr[tf].rr.target_share * 100)} %, xərcdən sonra ${rr[tf].rr.net_r >= 0 ? "+" : ""}${rr[tf].rr.net_r.toFixed(2)} R · ${ST[rr[tf].rr.status] || esc(rr[tf].rr.status)}</span>` : ""}
${Object.keys(rr[tf].by_adx || {}).length ? `<span class="note">· ADX: ${Object.entries(rr[tf].by_adx).map(([g, b]) => `${esc(g)} ${Math.round(b.hit_rate * 100)} % (${b.n})`).join(" · ")}</span>` : ""}
            <span class="note">· ${Object.entries(rr[tf].by_metal || {}).map(([m, b]) => `${esc(m)} ${Math.round(b.hit_rate * 100)} %, ${(b.net_avg * 100).toFixed(3)} %`).join(" · ")}</span></span>` : "").join("");
      // one line per rule (owner 2026-11-26: compact): code, name and the Judge's short verdict per timeframe; the
      // method, signal, void condition, source and the full record open with a click (and stay open on a re-draw)
      const ICON = { "sübut": "✅", yox: "❌", "zəif": "⚠️", az: "⏳", "namizəd": "🏁" };
      const short = ["1h", "4h", "1d"].filter((tf) => rr[tf]).map((tf) =>
        `<span class="rchip ${esc(rr[tf].status)}">${tf} ${ICON[rr[tf].status] || ""} ${Math.round(rr[tf].hit_rate * 100)} %</span>`).join("");
      return `<details class="rule" data-r="${esc(r.id)}" ${OPEN.has(r.id) ? "open" : ""}><summary class="rh"><b>${esc(r.id)}</b> <span class="rn">${esc(r.name)}</span>
          <span class="rsum">${short || `<span class="note">${r.detector ? "hələ ölçü yoxdur" : "analitik tətbiq edir"}</span>`}</span></summary>
        <div class="rr"><span>Necə</span><span class="note">${r.detector ? "kod özü tapır, Hakim ölçür" : "analitik faktlardan tətbiq edir"}</span></div>
        <div class="rr"><span>Üsul</span><span>${esc(r.how)}</span></div>
        <div class="rr"><span>Siqnal</span><span>${esc(r.signal)}</span></div>
        <div class="rr"><span>Ləğv</span><span>${esc(r.void)}</span></div>
        <div class="rr"><span>Mənbə</span><span>${esc(r.source)}</span></div>
        ${cells ? `<div class="rr"><span>Hakim</span><span>${cells}</span></div>` : ""}
        ${(data.brain_rules || {})[r.id] ? `<div class="rr"><span>Beyinlər</span><span>${Object.entries(data.brain_rules[r.id]).map(([src, [ok, bad]]) =>
          `${esc(src === "strateq" ? "Strateq" : src === "chartist" ? "Qrafik analitiki" : src)}: düz ${ok}, səhv ${bad}`).join(" · ")}</span></div>` : ""}</details>`;
    }).join("");
    document.querySelectorAll("#rules details.rule").forEach((d) => d.ontoggle = () => { d.open ? OPEN.add(d.dataset.r) : OPEN.delete(d.dataset.r); });
    const act = [];
    Object.entries(data.active).forEach(([s, xs]) => xs.forEach((x) => act.push({ s, ...x })));
    const arow = (x) => `<tr><td>${NAMES[x.s] || esc(x.s)}</td><td class="c">${esc(x.tf)}</td><td>${esc(x.rule)}</td>
        <td class="c ${x.dir > 0 ? "up" : "down"}">${x.dir > 0 ? "▲ yuxarı" : "▼ aşağı"}</td><td class="note">${esc(x.note)}</td></tr>`;
    const head = `<table class="sc"><tr><th>Metal</th><th>Çərçivə</th><th>Qayda</th><th>İstiqamət</th><th>Nə görüldü</th></tr>`;
    // the first 10 at once, the rest one click away (owner 2026-11-26: compact)
    $("active").innerHTML = !act.length ? "<p class='note'>Hələ siqnal yoxdur: qaydalar 15 dəqiqədə bir yoxlanır.</p>"
      : head + act.slice(0, 10).map(arow).join("") + "</table>" + (act.length > 10
        ? `<details class="more"><summary class="note">Hamısını göstər (${act.length})</summary>${head}${act.slice(10).map(arow).join("")}</table></details>` : "");
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
