// Bazar axını page (plan 27.11 step 11.1): /api/flow per metal — the stream's state, the last hour's volume and the
// share started by buyers, the big trades of the day, minute by minute.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const NAMES = { XAU: "Qızıl", XAG: "Gümüş", XPT: "Platin", XPD: "Palladium" };
  const NY = { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" };
  let sym = "XAU";
  try { sym = localStorage.getItem("tst_flow_sym") || sym; } catch (e) {}
  const pc = (x) => x == null ? "—" : Math.round(x * 100) + " %";
  function seg() {
    $("sym").innerHTML = Object.entries(NAMES).map(([k, n]) => `<button type="button" data-k="${k}" class="${k === sym ? "on" : ""}">${n}</button>`).join("");
    $("sym").querySelectorAll("button").forEach((b) => b.onclick = () => { sym = b.dataset.k; try { localStorage.setItem("tst_flow_sym", sym); } catch (e) {} load(); });
  }
  async function load() {
    seg();
    let d;
    try { const r = await fetch(`/api/flow?symbol=${sym}&minutes=60`, { credentials: "same-origin" });
      if (r.status === 401) { location.href = "/login"; return; } d = await r.json(); } catch (e) { $("fstate").textContent = "Məlumat alınmadı."; return; }
    const h = d.health;
    $("fstate").innerHTML = !h ? "Canlı axın hələ başlamayıb." :
      `${h.ok ? "🟢" : h.ok === false ? "🔴" : "⏳"} ${esc(h.msg)} <span class="note">(${new Date(h.ts * 1000).toLocaleTimeString("az", NY)} NY)</span>`;
    const big = d.minutes.reduce((a, m) => a + m.big_buy + m.big_sell, 0);
    $("fsum").innerHTML = d.minutes.length ? `<p>Son 60 dəqiqə: həcm <b>${d.vol.toLocaleString("az")}</b> lot · alıcıların payı
      <b class="${d.buy_share > 0.55 ? "up" : d.buy_share < 0.45 ? "down" : ""}">${pc(d.buy_share)}</b> · böyük əməliyyat ${big}</p>` :
      "<p class='note'>Son 60 dəqiqədə əməliyyat yoxdur (axın başlamayıb və ya bazar bağlıdır).</p>";
    $("fbig").innerHTML = d.big.length ? `<table class="sc"><tr><th>Vaxt</th><th>Tərəf</th><th class="c">Lot</th><th class="c">Qiymət</th></tr>` +
      d.big.map((b) => `<tr><td>${new Date(b.ts * 1000).toLocaleTimeString("az", NY)}</td><td class="${b.side === "buy" ? "up" : "down"}">${b.side === "buy" ? "▲ alış" : "▼ satış"}</td>
        <td class="c">${b.size}</td><td class="c">${b.price.toFixed(2)}</td></tr>`).join("") + "</table>" : "<p class='note'>Hələ yoxdur.</p>";
    const rows = d.minutes.slice(-30).reverse();
    $("fmin").innerHTML = rows.length ? `<table class="sc"><tr><th>Dəqiqə</th><th class="c">Həcm</th><th class="c">Alanlar</th><th class="c">Satanlar</th><th class="c">Böyük</th></tr>` +
      rows.map((m) => { const s = m.buy + m.sell ? m.buy / (m.buy + m.sell) : null;
        return `<tr><td>${new Date(m.t * 1000).toLocaleTimeString("az", NY)}</td><td class="c">${m.vol}</td>
          <td class="c ${s > 0.6 ? "up" : ""}">${pc(s)}</td><td class="c ${s != null && s < 0.4 ? "down" : ""}">${pc(s == null ? null : 1 - s)}</td>
          <td class="c">${m.big_buy ? "▲" + m.big_buy : ""} ${m.big_sell ? "▼" + m.big_sell : ""}</td></tr>`; }).join("") + "</table>" : "";
    $("upd").textContent = "yeniləndi " + new Date().toLocaleTimeString("az", NY) + " NY";
  }
  load(); setInterval(load, 15000);
})();
