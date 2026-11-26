/* System status: the same report the read-only diagnostics API gives, for the owner, in words. */
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const when = (ts) => ts ? new Date(ts * 1000).toLocaleString("az") : "—";
const ago = (ts) => {
  if (!ts) return "—";
  const s = Date.now() / 1000 - ts;
  return s < 90 ? Math.round(s) + " san əvvəl" : s < 5400 ? Math.round(s / 60) + " dəq əvvəl"
    : s < 172800 ? Math.round(s / 3600) + " saat əvvəl" : Math.round(s / 86400) + " gün əvvəl";
};
const pill = (ok, text) => `<span class="pill ${ok === true ? "ok" : ok === false ? "bad" : "warn"}">${esc(text)}</span>`;
const NAMES = { XAU: "Qızıl", XAG: "Gümüş", XPT: "Platin", XPD: "Palladium" };
const SRC = { rss: "Xəbərlər (RSS)", forexfactory: "İqtisadi təqvim", fred: "FRED makro", cot: "CFTC COT", alpaca: "Alpaca / Benzinga", fmp: "FMP ABŞ rəqəmləri" };

async function load() {
  const r = await fetch("/api/admin/status", { credentials: "same-origin" });
  if (r.status === 401) { location.href = "/login"; return; }
  if (!r.ok) { $("sumbar").hidden = false; $("sumbar").textContent = "Vəziyyət oxunmadı: HTTP " + r.status; return; }
  const d = await r.json();
  const problems = [];
  $("s-metals").innerHTML = `<table><tr><th>Metal</th><th>Status</th><th>Qiymət</th><th>Son qiymət</th><th>Saatda tik</th><th>Alış / satış</th></tr>` +
    Object.entries(d.metals).map(([s, m]) => {
      if (m.status !== "LIVE" && m.status !== "DEMO") problems.push(`${NAMES[s]}: ${m.status}`);
      return `<tr><td>${NAMES[s]}</td><td>${pill(m.status === "LIVE" ? true : m.status === "OFFLINE" ? false : null, m.status)}</td>
      <td class="n">${m.price ?? "—"}</td><td>${m.age_s == null ? "—" : m.age_s + " san"}</td><td class="n">${m.ticks_hour ?? "—"}</td>
      <td class="n">${m.bid_ask ? m.bid_ask.join(" / ") : "—"}</td></tr>`;
    }).join("") + "</table>" +
    `<p class="note">Mənbə: ${esc(d.provider)}${Object.keys(d.provider_errors || {}).length ? " · " + esc(Object.values(d.provider_errors).join("; ")) : ""}</p>`;
  $("s-src").innerHTML = `<table><tr><th>Mənbə</th><th>Vəziyyət</th><th>Son yoxlama</th><th>Qeyd</th></tr>` +
    Object.entries(d.sources).map(([k, h]) => {
      if (h.ok === false) problems.push(`${SRC[k] || k}: ${h.message}`);
      const word = h.off ? "istifadə olunmur" : h.ok ? "işləyir" : h.ok === false ? "xəta" : "gözlənilir";
      return `<tr><td>${SRC[k] || k}</td><td>${h.off ? `<span class="pill next">${word}</span>` : pill(h.ok, word)}</td>
      <td>${ago(h.checked)}</td><td>${esc(h.message || "")}</td></tr>`;
    }).join("") + "</table>";
  $("s-keys").innerHTML = `<table><tr><th>Yer</th><th>Saxlanıb</th><th>Son yoxlama</th></tr>` +
    Object.entries(d.keys).map(([k, v]) => {
      const c = v.check || {};
      if (v.saved && c.ok === false) problems.push(`Açar ${k}: ${c.message}`);
      return `<tr><td>${esc(k)}</td><td>${v.saved ? (v.unreadable ? pill(false, "oxunmur") : pill(true, "bəli")) : pill(null, "yox")}</td>
      <td>${v.saved ? pill(c.ok, c.message || "yoxlanmayıb") + " " + ago(c.ts) : "—"}</td></tr>`;
    }).join("") + "</table>";
  $("s-brains").innerHTML = `<table><tr><th>Beyin</th><th>Model</th><th>Bu ay</th><th>Son çağırış</th></tr>` +
    d.brains.map((b) => `<tr><td>${esc(b.name)}${b.in_use ? "" : " <span class='note'>(işə qoşulmayıb)</span>"}</td>
      <td>${esc(b.config.provider)} · ${esc(b.config.model)}</td><td class="n">$${(b.spent || 0).toFixed(2)} / $${b.config.month_usd}</td>
      <td>${b.last_call ? ago(b.last_call.ts) + (b.last_call.ok === false ? " " + pill(false, "xəta") : "") : "—"}</td></tr>`).join("") + "</table>" +
    Object.entries(d.brain_jobs || {}).map(([k, v]) => `<p class="note">${esc(k)}: ${esc((v && v.message) || "—")} (${ago(v && v.ts)})</p>`).join("");
  const h = d.history || {};
  $("s-hist").innerHTML = h.result ? `<table><tr><th>Metal</th><th>Nəticə</th></tr>` + Object.entries(h.result).map(([s, r]) =>
    `<tr><td>${NAMES[s] || s}</td><td>${Object.entries(r).map(([tf, t]) => `<b>${esc(tf)}</b> ${esc(t)}`).join("<br>")}</td></tr>`).join("") +
    `</table><p class="note">Son yükləmə ${when(h.ts)} · ${esc(h.source || "")}</p>` : `<p class="note">${esc(h.note || "Hələ yüklənməyib")}</p>`;
  $("s-srv").innerHTML = `<table>
    <tr><td>Versiya</td><td class="n">${esc(d.version)}</td></tr>
    <tr><td>İşləmə müddəti</td><td class="n">${Math.round(d.uptime_s / 360) / 10} saat</td></tr>
    <tr><td>Açıq proqnoz</td><td class="n">${d.forecasts_open}</td></tr>
    <tr><td>Baza ölçüsü</td><td class="n">${d.db_bytes ? (d.db_bytes / 1048576).toFixed(1) + " MB" : "—"}</td></tr></table>`;
  $("s-err").innerHTML = d.errors.length ? `<table><tr><th>Son dəfə</th><th>Say</th><th>Yer</th><th>Xəta</th></tr>` +
    d.errors.map((e) => `<tr><td>${ago(e.last_ts)}</td><td class="n">${e.count}</td><td>${esc(e.logger)}</td>
      <td>${esc(e.message)}${e.trace ? `<details><summary class="note">ətraflı</summary><pre class="trace">${esc(e.trace)}</pre></details>` : ""}</td></tr>`).join("") + "</table>"
    : "<p class='note'>Xəta yoxdur.</p>";
  if (d.errors.some((e) => Date.now() / 1000 - e.last_ts < 3600)) problems.push("son 1 saatda xəta yazılıb (aşağıya baxın)");
  const ST = { ok: [true, "işləyir"], warn: [null, "diqqət"], bad: [false, "işləmir"], closed: [undefined, "bazar bağlı"] };
  $("s-pipe").innerHTML = `<table><tr><th>Halqa</th><th>Vəziyyət</th><th>Nə göstərir</th><th>Nəyə ötürür</th></tr>` +
    (d.pipeline || []).map((r) => { const [ok, t] = ST[r.status] || [null, r.status];
      if (r.status === "warn" || r.status === "bad") problems.push(r.stage + ": " + r.msg);
      return `<tr><td>${esc(r.stage)}</td><td>${r.status === "closed" ? "<span class='pill next'>bazar bağlı</span>" : pill(ok, t)}</td>
        <td>${esc(r.msg)}</td><td class="note">→ ${esc(r.into)}</td></tr>`; }).join("") + "</table>";
  const sec = d.security || {}, cnt = sec.last_24h || {};
  if ((sec.alerts || []).length) problems.push("təhlükəsizlik: " + sec.alerts.length + " xəbərdarlıq (aşağıya baxın)");
  $("s-sec").innerHTML = `<p>${pill((sec.alerts || []).length ? null : true, (sec.alerts || []).length ? "baxın" : "sakit")}
      Son 24 saat: səhv parol ${cnt.login_fail || 0}, bloklanan ${cnt.login_blocked || 0}, giriş ${(cnt.login_ok || 0) + (cnt.login_new_ip || 0)},
      yeni ünvandan giriş ${cnt.login_new_ip || 0}. İndi bloklu ünvan: ${(sec.blocked_now || []).length}. Tanınan ünvan: ${sec.known_ips || 0}.</p>` +
    ((d.security_events || []).length ? `<table><tr><th>Vaxt</th><th>Hadisə</th><th>Ünvan</th><th>Yer</th><th>Qeyd</th></tr>` +
      d.security_events.map((e) => `<tr><td>${ago(e.ts)}</td><td>${esc(e.kind_az)}</td><td class="n">${esc(e.ip)}</td><td>${esc(e.place || "—")}</td><td>${esc(e.detail)}</td></tr>`).join("") + "</table>" +
      `<p class="note">Yer (şəhər, ölkə): <a href="https://db-ip.com" rel="noopener" target="_blank">IP Geolocation by DB-IP</a> — pulsuz baza serverdə saxlanır, ünvanlar heç yerə göndərilmir; dəqiqliyi təxminidir.</p>` : "") +
    `<p class="note">Server firewall-u: internetdən yalnız sayt (80/443) açıqdır, SSH bağlıdır. 15 dəqiqədə 5 səhv parol → həmin ünvan 15 dəqiqə bloklanır.</p>`;
  $("sumbar").hidden = false;
  $("sumbar").className = "evbanner" + (problems.length ? "" : " okbar");
  $("sumbar").textContent = problems.length ? "Diqqət: " + problems.join(" · ") : "Hər şey qaydasındadır.";
  $("upd").textContent = "yeniləndi " + new Date().toLocaleTimeString("az");
}
load();
setInterval(load, 30000);
