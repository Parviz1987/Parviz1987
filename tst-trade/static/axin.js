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
  // «Böyük oyunçular indi» and the client sentiment (owner 28.11): the newest reading of each free source and what
  // it usually means. Nothing here is a signal yet: each is a voice the Judge measures (link to Fundamental).
  const sgn = (x, d = 0) => x == null ? "—" : (x > 0 ? "+" : "") + x.toLocaleString("az", { maximumFractionDigits: d });
  const cls = (x) => x > 0 ? "up" : x < 0 ? "down" : "";
  const card = (title, value, sub, mean) => `<div class="bpc"><div class="bpt">${title}</div><div class="bpv">${value}</div>
    <div class="note">${sub}</div><div class="bpm">${mean}</div></div>`;
  async function loadBig() {
    let d;
    try { const r = await fetch("/api/bigplayers", { credentials: "same-origin" });
      if (r.status === 401) { location.href = "/login"; return; } d = await r.json(); } catch (e) { $("bp").innerHTML = "<p class='note'>Məlumat alınmadı.</p>"; return; }
    const out = [];
    const c = d.cot && d.cot.XAU;
    if (c) out.push(card("İri fondlar qızılda (CFTC COT)", `<span class="${cls(c.net)}">${sgn(c.net)}</span> müqavilə xalis alış`,
      `həftəlik dəyişmə <b class="${cls(c.change)}">${sgn(c.change)}</b> · ${c.d} · son 3 ildə yeri: ${c.rank_3y == null ? "—" : Math.round(c.rank_3y * 100) + " / 100"}`,
      c.rank_3y >= 0.85 ? "Fondlar son 3 ilin ən yüksək alış mövqeyinə yaxındır: yeni alıcı az qalıb, düzəliş riski artır." :
      c.rank_3y <= 0.15 ? "Fondlar son 3 ilin ən aşağı mövqeyinə yaxındır: geri alış (yuxarı) potensialı var." :
      "Fondların mövqeyi orta səviyyədədir."));
    const g = d.gld;
    if (g) out.push(card("Dünyanın ən böyük qızıl fondu (GLD)", `${g.tonnes.toLocaleString("az")} ton`,
      `gün <b class="${cls(g.ch_1d)}">${sgn(g.ch_1d, 1)}</b> · 5 gün <b class="${cls(g.ch_5d)}">${sgn(g.ch_5d, 1)}</b> · 20 gün <b class="${cls(g.ch_20d)}">${sgn(g.ch_20d, 1)}</b> ton · ${g.d}`,
      g.ch_20d > 0 ? "Son 20 gündə investorlar fonda qızıl yığır (tələb artır)." : g.ch_20d < 0 ? "Son 20 gündə investorlar fonddan qızıl çıxarır (tələb azalır)." : ""));
    const cb = d.central_banks || [];
    if (cb.length) { const last = cb[cb.length - 1];
      out.push(card("Mərkəzi banklar (BVF)", `<span class="${cls(last.tonnes)}">${sgn(last.tonnes, 1)}</span> ton`,
        `${last.month} · ${last.banks} bank · əvvəlki aylar: ${cb.slice(0, -1).map((x) => sgn(x.tonnes, 1)).join(", ") || "—"}`,
        last.tonnes > 0 ? "Mərkəzi banklar xalis alıcıdır: uzunmüddətli dəstək." : "Mərkəzi banklar bu ay xalis satıcıdır.")); }
    const ind = d.india || [];
    if (ind.length) { const last = ind[ind.length - 1];
      out.push(card("Hindistan qızıl fondlarına axın (AMFI)", `<span class="${cls(last.net_crore)}">${sgn(last.net_crore)}</span> krore rupi`,
        `${last.month} · əvvəlki: ${ind.slice(0, -1).map((x) => sgn(x.net_crore)).join(", ") || "—"}`,
        last.net_crore > 0 ? "Hindistan investorları qızıl alır." : "Hindistan investorları qızıl satır.")); }
    const sh = d.shanghai;
    if (sh) out.push(card("Şanxay qızıl birjası (SGE)", `${sh.volume_kg.toLocaleString("az")} kq`,
      `${sh.d} · 20 günlük ortaya nisbətən <b>${sh.vs_20d == null ? "—" : "×" + sh.vs_20d}</b>`,
      sh.vs_20d >= 1.3 ? "Çində alqı-satqı adətindən xeyli çoxdur (tələb canlıdır)." : sh.vs_20d <= 0.7 ? "Çində alqı-satqı adətindən azdır." : "Çində alqı-satqı adi səviyyədədir."));
    $("bp").innerHTML = out.length ? out.join("") : "<p class='note'>Hələ məlumat yoxdur.</p>";
    // client sentiment: the crowd's side per metal, with the pre-registered test
    const s = d.sentiment || {}, m = s.metals || {}, t = d.sentiment_test || {}, h = s.health;
    const rows = Object.keys(NAMES).filter((k) => m[k]).map((k) => { const v = m[k];
      return `<tr><td>${NAMES[k]}</td><td class="c"><b>${Math.round(v.long_pct)} %</b> alışda</td><td class="c">${100 - Math.round(v.long_pct)} % satışda</td>
        <td class="c ${cls(v.change_24h)}">${v.change_24h == null ? "—" : sgn(v.change_24h, 1) + " (24 saat)"}</td></tr>`; }).join("");
    $("sent").innerHTML = (rows ? `<table class="sc"><tr><th>Metal</th><th class="c">Alıcılar</th><th class="c">Satıcılar</th><th class="c">Dəyişmə</th></tr>${rows}</table>` :
      `<p class="note">${h ? esc(h.msg) : "Oxunuş hələ başlamayıb"} (15 dəqiqədən bir oxunur).</p>`) +
      `<p class="note">İdeya: adi alıcılar bir tərəfə yığılanda qiymət çox vaxt əks tərəfə gedir. Bu hələ fərziyyədir — qayda
        qabaqcadan yazılıb (hər iş günü 12:00 NY oxunuşu, qızıl 24 saat, tam xərcdən sonra, ən az 60 gün). Hakimin sayı:
        <b>${t.n ?? 0}/${t.need ?? 60}</b> gün${t.status && t.status !== "az" ? " · nəticə: <b>" + esc(t.status) + "</b>" : ""}.</p>`;
  }
  load(); setInterval(load, 15000);
  loadBig(); setInterval(loadBig, 300000);
})();
