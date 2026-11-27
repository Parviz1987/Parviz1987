// Bloklar: the organs of the system — each block's voice now, its methods with their views and the Judge's record,
// the evidence it rests on and what is still missing. Read-only.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const pct = (v) => (v == null ? "—" : Math.round(v * 100) + " %");
  const ST = { "sübut": "✅ sübut", yox: "❌ yox", "zəif": "⚠️ zəif", az: "⏳ az", "xərc": "💸 xərc", "namizəd": "🏁 namizəd (son sınaq gözlənir)", bazis: "bazis" };
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
      <details class="pass"><summary class="note">Ətraflı: nəyi oxuyur, üsulları və Hakim, nəyə əsaslanır, nə çatmır</summary>
      <p class="note"><b>Oxuyur:</b> ${esc(b.reads)}${b.ai ? ` · <b>AI:</b> ${esc(b.ai)}` : ""}</p>
      ${b.methods.length ? `<div class="tbl"><table class="sc"><tr><th>Üsul</th><th>İndi</th><th>Hakim</th><th>Niyə</th></tr>` +
        b.methods.map((m) => `<tr><td>${esc(m.name)}</td><td class="c">${lean(m.p)}</td>
          <td class="c">${m.record && m.record.nh ? `${m.record.nh} hal, ${pct(m.record.hit_rate)} (hədd ${pct(m.record.bar)}) · ${ST[m.record.status] || esc(m.record.status)} <span class="note">${esc(m.record_mode)}</span>` : '<span class="note">hələ yox</span>'}</td>
          <td class="note">${esc(m.basis || "")}</td></tr>`).join("") + "</table></div>" : ""}
      ${b.value ? `<p class="note"><b>Blokun dəyəri</b> (vahid proqnozun öz-özünü sınağı bu blok OLMADAN): düz ${pct(b.value.hit_rate)}${b.value.hit_change != null ? ` (fərq ${b.value.hit_change >= 0 ? "+" : ""}${(b.value.hit_change * 100).toFixed(1)} bənd)` : ""}, Brier bacarığı ${b.value.bss == null ? "—" : b.value.bss.toFixed(4)}${b.value.bss_change != null ? ` (fərq ${b.value.bss_change >= 0 ? "+" : ""}${b.value.bss_change.toFixed(4)})` : ""}. ${b.value.bss_change != null ? (b.value.bss_change < 0 ? "Blok OLMADAN pisləşir: blok kömək edir." : "Blok olmadan pisləşmir: hələ köməyi görünmür.") : ""}</p>` : ""}
      <p class="note"><b>Nəyə əsaslanır:</b> ${esc(b.evidence)}</p>
      <p class="note"><b>Çatmayan:</b> ${esc(b.missing)}</p></details></section>`).join("");
    const fin = d.finals || [];
    $("comb").innerHTML += `<p class="note"><b>Sübutun dürüstlüyü:</b> sistem indiyə qədər <b>${d.trials}</b> fikri sınayıb (hər üsul hər masada, hər qayda hər çərçivədə, hər hipotez). Hər sübut bu sayla birlikdə göstərilir. «Sübut» olan hər şey əvvəlcə <b>namizəd</b> olur və yalnız bundan SONRA gələn məlumatda bir dəfə yoxlanır (son sınaq); keçməsə, sübut sayılmır.` +
      (d.ablation_full ? ` Bu üfüqdə vahid proqnozun öz-özünü sınağı: düz ${pct(d.ablation_full.hit_rate)}, Brier bacarığı ${d.ablation_full.bss == null ? "—" : d.ablation_full.bss.toFixed(4)}.` : "") + "</p>" +
      (fin.length ? `<div class="tbl"><table class="sc"><tr><th>Namizəd</th><th>Masa</th><th>Son sınaq</th></tr>` + fin.map((f) =>
        `<tr><td>${esc(f.kind)}: ${esc(f.name)}</td><td>${esc(f.symbol)} ${esc(f.horizon)}</td><td>${esc(f.status)}${f.n != null ? ` · ${f.n}/${f.need} hal` : ""}</td></tr>`).join("") + "</table></div>" : "<p class='note'>Hələ namizəd yoxdur.</p>");
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
