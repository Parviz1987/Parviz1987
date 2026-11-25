// Strategy registry (Radar Gold): finalists that passed the one-look final test and the independent re-check wait for
// the owner's approval here; only an approved one may give AL / SAT. Also: every finalist, the experiment journal,
// the price audit against an independent source.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const day = (t) => (t ? new Date(t * 1000).toLocaleString("en-GB", { timeZone: "America/New_York" }) : "—");
  let armed = null;
  async function load() {
    let d;
    try { const r = await fetch("/api/admin/registry", { credentials: "same-origin" }); if (!r.ok) return; d = await r.json(); } catch (e) { return; }
    const reg = d.registry || [], fin = d.finals || [], pa = d.price_audit;
    $("reg").innerHTML =
      `<p class="note">Sistem indiyə qədər <b>${d.trials}</b> fikri sınayıb. Proses: sübut → namizəd → yalnız SONRAKI məlumatda bir dəfə son sınaq → məlumatın müstəqil təkrar hesablanması → sizin təsdiqiniz → reyestr. Təsdiqsiz heç bir şey AL / SAT verə bilməz.</p>` +
      (reg.length ? `<div class="tbl"><table class="sc"><tr><th>Növ</th><th>Ad</th><th>Masa</th><th>Versiya</th><th>Status</th><th>Qeyd</th><th></th></tr>` +
        reg.map((r, i) => `<tr><td>${esc(r.kind)}</td><td>${esc(r.name)}</td><td>${esc(r.symbol)} ${esc(r.horizon)}</td><td class="mono">${esc(r.version)}</td>
          <td>${esc(r.status)}</td><td class="note">${esc(r.note || "")}</td>
          <td>${r.status === "təsdiq gözləyir" ? `<button class="tabtn" data-a="${i}" data-v="1">${armed === i + ":1" ? "Yenə bas: təsdiqlə" : "Təsdiqlə"}</button>
            <button class="tabtn" data-a="${i}" data-v="0">${armed === i + ":0" ? "Yenə bas: rədd et" : "Rədd et"}</button>` : ""}</td></tr>`).join("") + "</table></div>"
        : "<p class='note'>Reyestr boşdur: hələ heç bir fikir son sınaqdan keçməyib.</p>") +
      (fin.length ? `<p><b>Namizədlər və son sınaq:</b></p><div class="tbl"><table class="sc"><tr><th>Ad</th><th>Masa</th><th>Namizəd olub</th><th>Son sınaq</th></tr>` +
        fin.map((f) => `<tr><td>${esc(f.kind)}: ${esc(f.name)}</td><td>${esc(f.symbol)} ${esc(f.horizon)}</td><td>${day(f.since)}</td><td>${esc(f.status)}${f.n != null ? ` · ${f.n}/${f.need}` : ""}</td></tr>`).join("") + "</table></div>" : "") +
      (pa ? `<p class="note"><b>Müstəqil qiymət yoxlaması</b> (bizim gündəlik bağlanışlar ↔ Twelve Data, son 30 gün): ${Object.entries(pa.metals || {}).map(([m, x]) => x.error ? `${m}: ${esc(x.error)}` : `${m}: orta fərq ${x.median_gap == null ? "—" : (x.median_gap * 100).toFixed(3) + " %"}, ən böyük ${x.worst_gap == null ? "—" : (x.worst_gap * 100).toFixed(2) + " %"}`).join(" · ")} — ${pa.ok ? "✅ uyğundur" : "⚠️ böyük fərq var"}</p>` : "") +
      `<p><b>Fərziyyə agenti</b> <span class="note">(həftədə bir; növbəti: ${day(d.ideas_next)} NY). AI yaddaşdan yeni fikir təklif edir, proqram onu
        sərt şablonla HY- qaydasına çevirir, Hakim ölçür. Tarixə baxılaraq tapılan fikir yalnız namizəddir: işə düşmək üçün sonrakı məlumatda son sınaq və sizin təsdiqiniz lazımdır.</span></p>` +
      ((d.ideas || []).length ? `<div class="tbl"><table class="sc"><tr><th>Vaxt</th><th>Qayda</th><th>Fikir</th><th>Səbəb</th><th>Status</th></tr>` +
        d.ideas.map((x) => { let sp = {}; try { sp = JSON.parse(x.spec); } catch (e) {} return `<tr><td class="mut">${day(x.ts)}</td><td class="mono">${esc(x.rule || "—")}</td>
          <td class="note">${esc(x.base)} ${esc(x.tf)}${sp.metals && sp.metals.length ? " · " + esc(sp.metals.join(",")) : ""}${sp.dir ? (sp.dir > 0 ? " · yalnız AL" : " · yalnız SAT") : ""}${sp.adx && sp.adx.length ? " · ADX " + esc(sp.adx.join(",")) : ""}${sp.hours ? " · NY " + sp.hours[0] + "–" + sp.hours[1] : ""}${sp.confirm ? " · təsdiq " + esc(sp.confirm[0]) + " ≤" + sp.confirm[1] : ""}${sp.fa ? " · fundamental razı" : ""}</td>
          <td class="note">${esc(x.why || "")}${x.expect ? "<br><i>Səhv olduğunu göstərər: " + esc(x.expect) + "</i>" : ""}</td><td>${esc(x.status)}${x.reason ? "<br><span class='note'>" + esc(x.reason) + "</span>" : ""}</td></tr>`; }).join("") + "</table></div>"
        : "<p class='note'>Hələ fikir yoxdur.</p>") +
      `<details><summary class="note">Eksperiment jurnalı (son ${(d.experiments || []).length})</summary><div class="tbl"><table class="sc"><tr><th>Vaxt</th><th>Növ</th><th>Ad</th><th>Versiya</th></tr>` +
      (d.experiments || []).map((e) => `<tr><td class="mut">${day(e.ts)}</td><td>${esc(e.kind)}</td><td>${esc(e.name)}</td><td class="mono">${esc(e.version)}</td></tr>`).join("") + "</table></div></details>";
    document.querySelectorAll("#reg [data-a]").forEach((b) => b.onclick = async () => {
      const tag = b.dataset.a + ":" + b.dataset.v;
      if (armed !== tag) { armed = tag; load(); setTimeout(() => { if (armed === tag) { armed = null; load(); } }, 4000); return; }
      armed = null;
      const r = reg[+b.dataset.a];
      await fetch("/api/admin/registry", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind: r.kind, name: r.name, symbol: r.symbol, horizon: r.horizon, approve: b.dataset.v === "1" }) });
      load();
    });
  }
  load(); setInterval(load, 120000);
})();
