// Laboratoriyalar page (owner 28.11): /api/labs — each lab's question, data, result on history in plain words.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const NY = { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" };
  const WORD = { "sübut": ["ok", "✅ sübut"], "yox": ["bad", "❌ yox"], "az": ["", "⚪ az"] };
  const pill = (s) => { const w = WORD[s] || ["", s || "—"]; return `<span class="pill ${w[0]}">${esc(w[1])}</span>`; };
  const pct = (x, d = 1) => x == null ? "—" : (Math.round(x * 100 * 10 ** d) / 10 ** d) + " %";
  const sg = (x) => x == null ? "—" : `<span class="${x > 0 ? "up" : x < 0 ? "down" : ""}">${x > 0 ? "+" : ""}${x.toFixed(3)} %</span>`;
  function result(g) {
    if (!g) return "<p class='note'>Nəticə yoxdur.</p>";
    return `<p>${pill(g.status)} · <b>${g.n ?? 0}</b> hadisə (lazım: ${g.need ?? "—"})${g.first ? ` · ${esc(g.first)} → ${esc(g.last)}` : ""}</p>
      <table class="sc"><tr><th>Düz istiqamət</th><th class="c">Xərcdən sonra orta</th><th class="c">1-ci yarı</th><th class="c">2-ci yarı</th><th class="c">Təsadüf ehtimalı</th></tr>
      <tr><td>${pct(g.hit_rate)}</td><td class="c">${sg(g.net_avg_pct)}</td><td class="c">${sg((g.halves_net_pct || [])[0])}</td>
      <td class="c">${sg((g.halves_net_pct || [])[1])}</td><td class="c">${g.p == null ? "—" : pct(g.p, 2)}</td></tr></table>`;
  }
  async function load() {
    let d;
    try { const r = await fetch("/api/labs", { credentials: "same-origin" });
      if (r.status === 401) { location.href = "/login"; return; } d = await r.json(); } catch (e) { $("labs").innerHTML = "<p class='note'>Məlumat alınmadı.</p>"; return; }
    $("lt").textContent = "hesablandı " + new Date(d.ts * 1000).toLocaleTimeString("az", NY) + " NY";
    $("labs").innerHTML = d.labs.map((x) => `<div class="bpc lab"><div class="bpt">${esc(x.id)} · ${esc(x.name)}</div>
      <p><b>Sual:</b> ${esc(x.question)}</p><p class="note"><b>Məlumat:</b> ${esc(x.data)}</p>
      ${x.error ? `<p class="down">Hesablama xətası: ${esc(x.error)}</p>` : `<h3 class="sub">Qızıl (qərar verir)</h3>${result(x.gold)}
      <p class="note">Gümüş (yalnız göstərilir): ${pill((x.silver_shown || {}).status)} · ${(x.silver_shown || {}).n ?? 0} hadisə · düz ${pct((x.silver_shown || {}).hit_rate)} · xərcdən sonra ${sg((x.silver_shown || {}).net_avg_pct)}</p>`}
    </div>`).join("");
    const o = d.others || [];
    $("others").innerHTML = o.length ? `<table class="sc"><tr><th>Sınaq</th><th>Sual</th><th class="c">Hökm</th><th class="c">Hadisə</th><th class="c">Düz</th><th class="c">Xərcdən sonra</th></tr>` +
      o.map((x) => `<tr><td>${esc(x.name)}</td><td class="note">${esc(x.question)}</td><td class="c">${pill(x.status)}</td>
        <td class="c">${x.n ?? "—"}</td><td class="c">${pct(x.hit_rate)}</td><td class="c">${sg(x.net_avg_pct)}</td></tr>`).join("") + "</table>" :
      "<p class='note'>Hələ yoxdur.</p>";
    $("upd").textContent = "yeniləndi " + new Date().toLocaleTimeString("az", NY) + " NY";
  }
  load(); setInterval(load, 600000);
})();
