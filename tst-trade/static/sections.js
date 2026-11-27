/* Sections that used to crowd the main panel, each now on the page it belongs to (owner 2026-11-26: «nə harada
   olmalıdırsa, öz yerində olsun»). One file, same renderers as before; a section draws only where its container
   exists, so a page includes this file and the containers it wants:
     Fundamental page: #fsig (factors in words), #macro (FRED), #cot (CFTC), #releases (figures vs expectation)
     Vaxt page:        #events (US economic calendar)
     Xəbər page:       #scout (X and web, Grok), #rscore (does the Reader's up/down come true)
     Nəticələr page:   the Judge in detail (#jmatrix, #judge, #jc1/#jc2, #jwhere, #passports) and #journal */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const has = (id) => !!document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const pct = (x, d = 1) => x == null ? "—" : (x * 100).toFixed(d) + " %";
  const fmt = (x) => x == null ? "—" : (x >= 100 ? x.toFixed(2) : x.toFixed(3));
  const NY = { timeZone: "America/New_York" };
  const hhmm = (ts) => ts ? new Date(ts * 1000).toLocaleTimeString("az", { ...NY, hour: "2-digit", minute: "2-digit" }) : "—";
  const ago = (ts) => { const m = Math.round((Date.now() / 1000 - ts) / 60);
    return m < 60 ? m + " dəq əvvəl" : m < 1440 ? Math.round(m / 60) + " saat əvvəl" : Math.round(m / 1440) + " gün əvvəl"; };
  const until = (ts) => { const m = Math.round((ts - Date.now() / 1000) / 60);
    if (m < 0) return "çıxıb";
    return m < 60 ? m + " dəq sonra" : m < 1440 ? Math.floor(m / 60) + " saat " + (m % 60) + " dəq sonra" : Math.round(m / 1440) + " gün sonra"; };
  const nyDay = (ts) => new Date(ts * 1000).toLocaleString("az", { ...NY, weekday: "short", hour: "2-digit", minute: "2-digit" });
  async function api(path) {
    const r = await fetch(path, { credentials: "same-origin" });
    if (r.status === 401) { location.href = "/login"; throw new Error("login"); }
    return r.json();
  }
  // The metal chosen on this page (the results page keeps it in its own variable; elsewhere the last chosen metal).
  const pageSym = () => { try { if (typeof sym === "string") return sym; } catch (e) { /* not defined here */ }
    try { return localStorage.getItem("tst_sym") || "XAU"; } catch (e) { return "XAU"; } };
  const MNAME = { XAU: "Qızıl", XAG: "Gümüş", XPT: "Platin", XPD: "Palladium" };
  const STR_AZ = ["təsirsiz", "zəif", "orta", "güclü"];
  const VERDICT_AZ = { "sübut": "Sübut olunub", "yox": "Sübut yoxdur", "az": "Məlumat azdır", "bazis": "Bazis", "xərc": "Spreaddən kiçik" };

  // ---------- Fundamental page and Vaxt page: /api/feeds ----------
  const SER = { DFII10: 2, DGS10: 2, T10YIE: 2, DTWEXBGS: 2, VIXCLS: 1, SP500: 0 };
  function renderFund(d) {
    const m = Object.fromEntries(d.macro.map((x) => [x.series, x]));
    const sig = [];
    const add = (dir, title, text) => sig.push(`<div class="fsig"><span class="ar ${dir > 0 ? "up" : dir < 0 ? "down" : "mut"}">${dir > 0 ? "↑" : dir < 0 ? "↓" : "→"}</span>
      <span><b>${title}</b><br><span class="note">${text}</span></span></div>`);
    const r = m.DFII10, usd = m.DTWEXBGS, vix = m.VIXCLS, sp = m.SP500;
    if (r && r.value != null) add(r.change_week < -0.03 ? 1 : r.change_week > 0.03 ? -1 : 0, `Real faiz ${r.value.toFixed(2)} % (həftədə ${r.change_week >= 0 ? "+" : ""}${r.change_week.toFixed(2)})`,
      "Real faiz enəndə qızıl saxlamağın «itirilmiş gəliri» azalır: adətən qızıl üçün müsbət. 2022-dən bu əlaqə zəifləyib.");
    if (usd && usd.value != null) { const p = usd.change_week / (usd.value - usd.change_week) * 100;
      add(p < -0.3 ? 1 : p > 0.3 ? -1 : 0, `Dollar indeksi ${usd.value.toFixed(1)} (həftədə ${p >= 0 ? "+" : ""}${p.toFixed(2)} %)`,
        "Dollar zəifləyəndə qızıl başqa valyutalarda ucuzlaşır, tələb artır: qızıl üçün müsbət."); }
    if (vix && vix.value != null) add(vix.value > 25 ? 1 : 0, `VIX ${vix.value.toFixed(1)}`,
      vix.value > 25 ? "Bazarda qorxu yüksəkdir: sığınacaq kimi qızıla tələb arta bilər (amma ilk panikada qızıl da satıla bilər)."
        : vix.value < 15 ? "Bazar sakitdir: sığınacaq tələbi zəifdir." : "Qorxu səviyyəsi normaldır.");
    if (sp && sp.value != null) { const p = sp.change_week / (sp.value - sp.change_week) * 100;
      add(p < -3 ? 1 : 0, `S&P 500 həftədə ${p >= 0 ? "+" : ""}${p.toFixed(1)} %`, p < -3 ? "Səhmlərdə kəskin düşüş: risk-off, qızıla axın ola bilər." : "Səhm bazarında risk-off yoxdur."); }
    const s = pageSym(), c = (d.cot || []).find((x) => x.symbol === s);
    if (c && c.date) add(c.rank > 85 ? -1 : c.rank < 15 ? 1 : 0, `Böyük fondlar (${MNAME[s]}): xalis ${Math.round(c.net).toLocaleString("az")} müqavilə, 3 ilin ${c.rank == null ? "—" : c.rank.toFixed(0) + " %"}-i`,
      c.rank > 85 ? "Fondlar 3 ilin ən yüklü mövqeyinə yaxındır: alan az qalıb, geri çəkilmə riski artır."
        : c.rank < 15 ? "Fondlar 3 ilin ən zəif mövqeyinə yaxındır: satan az qalıb, dönüş potensialı var." : "Fondların mövqeyi ifrat deyil.");
    if (has("fsig")) $("fsig").innerHTML = sig.length ? sig.join("") + `<p class="note">Bunlar izahdır, proqnoz deyil: fundamental qaydalar
      aşağıda Hakimdə ayrıca yoxlanır. COT məlumatı çərşənbə axşamının vəziyyətidir, cümə günü dərc olunur.</p>`
      : `<p class="note">Fundamental məlumat hələ yoxdur (admin: FRED açarı).</p>`;
    const h = (d.health || {}).cot || {};
    if (has("cot")) $("cot").innerHTML = (d.cot || []).some((x) => x.date) ? `<table><tr><th>Metal</th><th>Hesabat</th><th>Fondların xalis mövqeyi</th><th>Açıq mövqelərin %-i</th><th>Həftəlik dəyişmə</th><th>3 illik diapazonda</th></tr>` +
      d.cot.map((x) => x.date ? `<tr><td>${MNAME[x.symbol]}</td><td>${x.date}</td><td class="n">${Math.round(x.net).toLocaleString("az")}</td>
        <td class="n">${x.net_pct_oi == null ? "—" : x.net_pct_oi.toFixed(1) + " %"}</td>
        <td class="n ${x.change > 0 ? "up" : x.change < 0 ? "down" : ""}">${x.change == null ? "—" : (x.change > 0 ? "+" : "") + Math.round(x.change).toLocaleString("az")}</td>
        <td class="n">${x.rank == null ? "—" : x.rank.toFixed(0) + " %"}</td></tr>` : "").join("") + "</table>" +
      `<p class="note">CFTC COT: «managed money» (hedc fondları, CTA) fyuçers mövqeyi. 100 % = son 3 ilin ən böyük alış mövqeyi.</p>`
      : `<p class="note">CFTC COT: ${esc(h.message || "hələ yüklənməyib")}</p>`;
  }
  async function loadFeeds() {
    if (!["fsig", "macro", "cot", "releases", "events"].some(has)) return;
    const d = await api("/api/feeds");
    const h = d.health || {};
    try { renderFund(d); } catch (e) { /* the other parts still draw */ }
    if (has("macro")) $("macro").innerHTML = d.macro.map((m) => m.value == null
      ? `<div class="mrow"><span>${esc(m.name)}</span><span class="mut">—</span><span></span></div>`
      : `<div class="mrow"><span>${esc(m.name)}<br><span class="note">${esc(m.date)}</span></span>
         <span class="v">${m.value.toFixed(SER[m.series] || 2)}</span>
         <span class="v ${m.change_week > 0 ? "up" : m.change_week < 0 ? "down" : "mut"}">${m.change_week >= 0 ? "+" : ""}${m.change_week.toFixed(2)}</span></div>`).join("") +
      `<p class="note">${h.fred && h.fred.ok ? "Sağda: həftəlik dəyişmə." : "FRED: " + esc((h.fred && h.fred.message) || "hələ yüklənməyib")}</p>`;
    if (has("events")) $("events").innerHTML = d.events.length ? `<table><tr><th>Vaxt (NY)</th><th>Hadisə</th><th>Gözlənti</th><th>Əvvəlki</th><th>Fakt</th></tr>` +
      d.events.map((e) => `<tr><td>${nyDay(e.ts)}<br><span class="note">${until(e.ts)}</span></td><td><span class="${e.impact === "High" ? "hi" : "me"}">●</span> ${esc(e.title)}</td>
        <td class="n">${esc(e.forecast || "—")}</td><td class="n">${esc(e.previous || "—")}</td><td class="n">${esc(e.actual || "—")}</td></tr>`).join("") + "</table>"
      : `<p class="note">${h.forexfactory && h.forexfactory.ok === false ? "Təqvim: " + esc(h.forexfactory.message) : "Yaxın 7 gündə mühüm ABŞ hadisəsi yoxdur və ya təqvim hələ yüklənməyib."}</p>`;
    if (!has("releases")) return;
    const fx = (v) => v == null ? "—" : Math.abs(v) >= 1e5 ? (v / 1e3).toFixed(0) + "K" : String(+v.toFixed(3));
    let html = (d.releases || []).length ? `<table><tr><th>Vaxt (NY)</th><th>Rəqəm</th><th>Gözlənti</th><th>Fakt</th><th>Qızıl üçün</th></tr>` +
      d.releases.map((r) => `<tr><td>${nyDay(r.ts)}</td>
        <td><span class="${r.impact === "High" ? "hi" : "me"}">●</span> ${esc(r.event)}</td><td class="n">${fx(r.estimate)}</td>
        <td class="n"><b>${fx(r.actual)}</b></td>
        <td>${r.actual == null ? "<span class='mut'>gözlənilir</span>" : !r.scored ? "<span class='mut'>—</span>" : r.gold > 0 ? "<span class='up'>↑ müsbət</span>" : "<span class='down'>↓ mənfi</span>"}</td></tr>`).join("") +
      `</table><p class="note">İnflyasiya və ya iş yerləri gözləntidən yüksək çıxanda dollar güclənir, bu adətən qızıl üçün mənfidir. Bu, ehtimaldır: «Hadisə sürprizi» üsulu Hakimdə yoxlanır.</p>`
      : `<p class="note">Hələ açıqlanan rəqəm yoxdur.</p>`;
    const hu = d.hunter || [];
    html += hu.length ? `<p class="note"><b>Rəqəm ovçusu</b> (iki beyin vebdə ayrı-ayrı axtarır): ` +
      hu.map((x) => `${esc(x.event)} — ${x.accepted ? "<span class='up'>təsdiqləndi</span>" : "<span class='mut'>" + esc(x.note) + "</span>"}` +
        [x.a, x.b].filter((v) => v && v.url).map((v) => ` <a href="${esc(v.url)}" target="_blank" rel="noopener noreferrer">${esc(v.raw)}</a>`).join("")).join(" · ") + "</p>"
      : `<p class="note"><b>Rəqəm ovçusu:</b> mühüm ABŞ rəqəmi çıxandan 2–20 dəqiqə sonra iki beyin faktı vebdən tapır; üst-üstə düşsə, istifadə olunur.</p>`;
    $("releases").innerHTML = html;
  }

  // ---------- Xəbər page: /api/brains (scout, reader score) ----------
  function renderReaderScore(rs) {
    if (!rs || !rs.n) { $("rscore").innerHTML = "<p class='note'>Hələ yoxlanmış qiymətləndirmə yoxdur: Oxuyucu başlığa «yuxarı» və ya «aşağı» deyəndən 1 saat sonra yoxlanır.</p>"; return; }
    $("rscore").innerHTML = `<table><tr><th>Güc</th><th>Yoxlama</th><th>Düz çıxıb</th><th>p (sikkəyə qarşı)</th></tr>` +
      rs.rows.map((r) => `<tr><td>${STR_AZ[r.strength] || r.strength}</td><td class="n">${r.n}</td><td class="n">${pct(r.hit_rate)}</td>
        <td class="n">${r.p == null ? "—" : r.p.toFixed(3)}</td></tr>`).join("") +
      `<tr><td><b>Cəmi</b></td><td class="n">${rs.n}</td><td class="n"><b>${pct(rs.hit_rate)}</b></td><td></td></tr></table>
      <p class="note">Eyni hadisə haqqında bir neçə başlıq bir-birindən asılıdır: bu ilk baxışdır, sübut deyil. Müqayisə üçün: bu saatlarda qiymət ${pct(rs.up_rate, 0)} hallarda qalxıb.</p>`;
  }
  function renderScout(d) {
    const x = d.scout;
    if (!x) { $("scout").innerHTML = `<p class="note">${esc((d.scout_state && d.scout_state.message) || "Kəşfiyyatçı (Grok) hələ axtarmayıb: bazar açıq olanda 4 saatda bir, mühüm ABŞ rəqəmi ətrafında 30 dəqiqədə bir axtarır.")}</p>`;
      if (has("scmeta")) $("scmeta").textContent = ""; return; }
    if (has("scmeta")) $("scmeta").textContent = `${x.brain} · ${hhmm(x.ts)} NY`;
    $("scout").innerHTML = (x.mood ? `<p>${esc(x.mood)}</p>` : "") + (x.items.length ? x.items.map((i) => `<div class="nitem">
        ${i.url ? `<a href="${esc(i.url)}" target="_blank" rel="noopener noreferrer">${esc(i.title)}</a>` : `<span>${esc(i.title)}</span>`}
        <span class="m">${esc(i.source)} · ${esc(i.metals.join(", ") || "ümumi")} ${i.direction === "up" ? "<span class='up'>↑</span>" : i.direction === "down" ? "<span class='down'>↓</span>" : "→"} ${STR_AZ[i.strength] || ""}${i.why ? " · " + esc(i.why) : ""}</span></div>`).join("")
      : "<p class='note'>Tapılan yoxdur.</p>") +
      `<p class="note">Grok X və vebdə axtarır. Mənbəyə klikləyib yoxlayın: süni intellekt səhv edə bilər. Rəqəm olan cümlələr avtomatik silinir.</p>` +
      (d.scout_state && d.scout_state.message && d.scout_state.ts > x.ts ? `<p class="note">Son cəhd: ${esc(d.scout_state.message)}</p>` : "");
  }
  async function loadBrains() {
    if (!has("scout") && !has("rscore")) return;
    const d = await api("/api/brains");
    if (has("rscore")) renderReaderScore(d.reader_score);
    if (has("scout")) renderScout(d);
  }

  // ---------- Nəticələr page: the Judge in detail and the journal ----------
  let fc = null, mode = null, jh = "15m";
  try { jh = localStorage.getItem("tst_jh") || jh; if (jh === "1m") jh = "15m"; } catch (e) { /* fine */ }
  const MCOL = { qaydalar: "#3fb27f", chartist: "#c77dff", vahid: "#d4a73c", momentum: "#4ea1ff", reversal: "#c77dff", trend: "#3fb27f", breakout: "#ff9f43", rsi: "#e0605a",
    fib: "#d4a73c", macro: "#2ec4b6", session: "#f78fb3", surprise: "#ffd166", dollar: "#06d6a0", oil: "#8d6e63",
    news: "#ef476f", strateq: "#118ab2", pullback: "#b5e48c", consensus: "#9aa5b1" };
  const costTip = (c) => !c ? "" : `Tam xərc ${(c.total * 100).toFixed(3)} %: spred ${(c.spread * 100).toFixed(3)} % + sürüşmə ${(c.slip * 100).toFixed(3)} %` +
    (c.swap ? ` + gecəlik haqq ${(c.swap * 100).toFixed(3)} %` : "");
  const nyHour = (utcH) => { const d = new Date(); d.setUTCHours(utcH, 0, 0, 0);
    return d.toLocaleTimeString("az", { ...NY, hour: "2-digit", minute: "2-digit" }); };
  const GROUP_AZ = { asia: `Asiya seansı (${nyHour(22)}–${nyHour(7)} NY)`, london: `London (${nyHour(7)}–${nyHour(13)} NY)`,
    ny: `Nyu-York (${nyHour(13)}–${nyHour(22)} NY)`, calm: "Sakit bazar", wild: "Dalğalı bazar" };
  function renderJudge() {
    const key = mode === "live" ? "stats_live" : "stats_history";
    const methods = Object.keys(fc.method_names).filter((m) => m !== "rw");
    let mx = `<table><tr><th>Üfüq</th>${methods.map((m) => `<th>${esc(fc.method_names[m])}</th>`).join("")}<th>50 % aralıq</th><th>80 % aralıq</th></tr>`;
    for (const c of fc.cards) {
      const by = Object.fromEntries(c[key].map((r) => [r.method, r]));
      const rw = by.rw || {};
      mx += `<tr><td>${c.name}</td>` + methods.map((m) => {
        const r = by[m];
        if (!r) return `<td class="cell mut">·</td>`;
        if (m === "up") return `<td class="cell bazis">${r.n ? pct(r.hit_rate, 0) : "—"}</td>`;
        return `<td class="cell ${r.status}" title="${r.nh} yoxlama, keçməli hədd ${pct(r.bar, 0)}">${r.nh ? pct(r.hit_rate, 0) : "—"}</td>`;
      }).join("") + `<td class="cell">${rw.n ? pct(rw.cover50, 0) : "—"}</td><td class="cell">${rw.n ? pct(rw.cover80, 0) : "—"}</td></tr>`;
    }
    $("jmatrix").innerHTML = mx + `</table><p class="note">Xanada: üsul istiqamət göstərəndə neçə faiz düz çıxıb. Yaşıl = sübut olunub,
      qırmızı = kifayət qədər yoxlama var, amma sübut yoxdur, sarı = hələ az yoxlama, nöqtəli sarı = statistik düzdür, amma hərəkət spreaddən kiçikdir.
      Aralıq sütunları: qiymət 50 % və 80 % aralığa neçə faiz düşüb (düzgün aralıq ≈ 50 % və ≈ 80 %).</p>`;
    $("jh").innerHTML = fc.cards.map((c) => `<button data-h="${c.horizon}" class="${c.horizon === jh ? "on" : ""}">${c.name}</button>`).join("");
    document.querySelectorAll("#jh button").forEach((b) => b.onclick = () => { jh = b.dataset.h; try { localStorage.setItem("tst_jh", jh); } catch (e) { /* fine */ } renderJudge(); });
    const card = fc.cards.find((c) => c.horizon === jh) || fc.cards[0];
    let html = `<table><tr><th>Üsul</th><th>Yoxlama</th><th>Düz çıxıb</th><th title="Şansla düz çıxma səviyyəsi">Şans səviyyəsi</th><th title="Pul sınağı: xərcdən sonra orta nəticə sıfırdan böyükdürmü">p (pul)</th>
      <th title="Tam xərc: spred + sürüşmə + gecəlik saxlama haqqı">Orta qazanc / tam xərc</th><th>Brier bal</th><th>50 % aralıq</th><th>80 % aralıq</th><th>Status</th></tr>`;
    for (const r of card[key]) {
      const cnt = r.method === "rw" || r.method === "up" ? r.n : r.nh;
      const st = r.status === "az" ? `az (${cnt}/${r.min_n})` : VERDICT_AZ[r.status];
      html += `<tr><td>${esc(fc.method_names[r.method])}</td><td class="n">${cnt}</td>
        <td class="n">${r.method === "rw" ? "—" : pct(r.hit_rate)}</td><td class="n">${r.method === "rw" ? "—" : pct(r.bar)}</td>
        <td class="n">${r.p == null || r.method === "rw" ? "—" : r.p.toFixed(3)}</td>
        <td class="n ${r.edge > r.cost ? "up" : ""}" title="${costTip(r.cost_parts)}">${r.edge == null || r.method === "rw" ? "—" : (r.edge * 100).toFixed(3) + " / " + (r.cost * 100).toFixed(3) + " %"}</td>
        <td class="n">${r.bss == null ? "—" : (r.bss * 100).toFixed(1)}</td>
        <td class="n">${pct(r.cover50, 0)}</td><td class="n">${pct(r.cover80, 0)}</td>
        <td><span class="pill ${r.status}">${st}</span></td></tr>`;
    }
    $("judge").innerHTML = html + `</table><p class='note'>«Yoxlama»: üsulun istiqamət göstərdiyi proqnozların sayı. Eyni məlumatda çox üsul
      yoxlandığı üçün p həddi üsulların sayına bölünür (indi ${card[key][2] ? card[key][2].p_bar.toFixed(4) : "—"}).
      «Orta qazanc» tam xərcdən kiçikdirsə, statistik düz olsa da pul qazandırmaz. Brier bal: 0-dan yuxarı = sikkə atmaqdan yaxşı.</p>`;
    const holder = $("jc1") && $("jc1").closest("details");
    if (holder && !holder.dataset.wired) { holder.dataset.wired = "1"; holder.addEventListener("toggle", () => { if (holder.open && fc) renderJudge(); }); }
    if (!holder || holder.open) loadJudgeCharts(card).catch(() => {});
    loadWhere(card).catch(() => {});
    loadPassports().catch(() => {});
  }
  async function loadJudgeCharts(card) {
    if (!has("jc1") || !window.drawLines) return;
    const d = await api(`/api/judge/series?symbol=${pageSym()}&horizon=${card.horizon}&mode=${mode}`);
    $("jwin").textContent = d.window;
    const names = fc.method_names, bar = (card[mode === "live" ? "stats_live" : "stats_history"].find((r) => r.method === "qaydalar") || {}).bar || 0.5;
    const ser = Object.entries(d.methods).map(([m, pts]) => ({ name: names[m], color: MCOL[m] || "#888", pts }));
    const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v);
    drawLines($("jc1"), ser, [{ v: bar, label: "keçməli hədd " + (bar * 100).toFixed(0) + " %", color: css("--muted") }], 0.3, 0.8);
    $("jl1").innerHTML = ser.map((s) => `<span><i style="background:${s.color}"></i>${esc(s.name)}</span>`).join("");
    const gold = css("--gold"), info = "#4ea1ff";
    drawLines($("jc2"), [{ name: "50 %", color: info, pts: d.cover["50"] }, { name: "80 %", color: gold, pts: d.cover["80"] }],
      [{ v: 0.5, color: info }, { v: 0.8, color: gold }], 0.2, 1.0);
    $("jl2").innerHTML = `<span><i style="background:${info}"></i>50 % aralığa düşən</span><span><i style="background:${gold}"></i>80 % aralığa düşən</span>`;
  }
  async function loadWhere(card) {
    if (!has("jwhere")) return;
    const d = await api(`/api/judge/where?symbol=${pageSym()}&horizon=${card.horizon}&mode=history`);
    const ms = Object.keys(d.methods);
    if (!ms.length) { $("jwhere").innerHTML = "<p class='note'>Hələ məlumat yoxdur.</p>"; return; }
    $("jwhere").innerHTML = `<table><tr><th>Üsul</th>${d.groups.map((g) => `<th>${GROUP_AZ[g]}</th>`).join("")}</tr>` +
      ms.map((m) => `<tr><td>${esc(fc.method_names[m] || m)}</td>${d.groups.map((g) => { const c = d.methods[m][g];
        const cls = c.status === "sübut" ? "sübut" : c.status === "xərc" ? "xərc" : c.hit_rate == null || c.n < 50 ? "mut" : c.hit_rate < d.bar - 0.03 ? "yox" : "";
        return `<td class="cell ${cls}" title="${c.n} yoxlama, p ${c.p == null ? "—" : c.p.toFixed(4)}">${c.n ? pct(c.hit_rate, 0) : "—"}${c.status === "sübut" ? " ✓" : ""}</td>`; }).join("")}</tr>`).join("") +
      `</table><p class="note">✓ yaşıl = bu şəraitdə sübut olunub (p həddi bütün xanaların sayına bölünür: ${d.p_bar ? d.p_bar.toFixed(4) : "—"}).
      Qırmızı = həddən (${pct(d.bar, 0)}) 3 bənd aşağı, boz = 50-dən az yoxlama. Sübutsuz xanalar yalnız müşahidədir.</p>`;
  }
  async function loadPassports() {
    if (!has("passports")) return;
    const d = await api(`/api/passports?symbol=${pageSym()}`);
    const short = { "sübut": "✓", "xərc": "xərc", "yox": "✗", "az": "az" };
    $("passports").innerHTML = `<table><tr><th>Üsul</th><th>Niyə var</th><th>Nə gözləyirik</th><th>Hakim indi (üfüq: nəticə)</th><th>Nəticə verməsə</th></tr>` +
      d.methods.map((m) => `<tr><td><b>${esc(m.name)}</b>${m.family ? `<br><span class="note">ailə: ${esc(m.family)}</span>` : ""}</td><td>${esc(m.why)}</td><td>${esc(m.expect)}</td>
        <td><div class="res">${Object.entries(m.results).map(([h, r]) => { const x = r.live && r.live.nh >= 1 && r.live.status !== "az" ? r.live : r.history || r.live || {};
          return `<span class="${x.status || "az"}" title="${x.nh ?? x.n ?? 0} yoxlama">${esc(d.horizons[h])}: ${short[x.status] || x.status || "—"}${x.hit_rate != null && m.method !== "rw" ? " " + Math.round(x.hit_rate * 100) + "%" : ""}</span>`; }).join("")}</div></td>
        <td>${esc(m.else)}</td></tr>`).join("") + `</table><p class="note">✓ sübut · ✗ kifayət qədər yoxlama var, sübut yoxdur · xərc: düzdür, amma tam xərcdən kiçik · az: hələ az yoxlama.</p>`;
  }
  async function loadJournal() {
    if (!has("journal")) return;
    const d = await api(`/api/journal?symbol=${pageSym()}`);
    const names = fc ? fc.method_names : {};
    const hn = Object.fromEntries((fc ? fc.cards : []).map((c) => [c.horizon, c.name]));
    if (!d.rows.length) { $("journal").innerHTML = "<p class='note'>Hələ yoxlanmış proqnoz yoxdur. Ən qısa proqnoz 15 dəqiqəlikdir: bazar açıq olanda hər 15 dəqiqədə yoxlanır.</p>"; return; }
    $("journal").innerHTML = `<table><tr><th>Vaxt (NY)</th><th>Üfüq</th><th>Üsul</th><th>Başlanğıc</th><th>Nəticə</th><th>Yuxarı ehtimalı</th><th>İstiqamət</th><th>80 % aralıq</th></tr>` +
      d.rows.map((r) => `<tr><td>${hhmm(r.target_t)}</td><td>${hn[r.horizon] || r.horizon}</td><td>${esc(names[r.method] || r.method)}</td>
        <td class="n">${fmt(r.price0)}</td><td class="n">${fmt(r.price1)}</td><td class="n">${(r.p_up * 100).toFixed(1)} %</td>
        <td>${r.hit == null ? "<span class='mut'>—</span>" : r.hit ? "<span class='up'>düz</span>" : "<span class='down'>səhv</span>"}</td>
        <td>${r.in80 ? "<span class='up'>tutdu</span>" : "<span class='down'>tutmadı</span>"}</td></tr>`).join("") + "</table>";
  }
  let modeTouched = false;
  async function loadJudge() {
    if (!has("jmatrix") && !has("journal")) return;
    fc = await api(`/api/forecasts?symbol=${pageSym()}`);
    if (!modeTouched) {   // until live forecasts are scored, open on the history tab (live would be all zeros)
      const liveN = fc.cards.reduce((a, c) => a + c.stats_live.reduce((b, r) => b + r.n, 0), 0);
      mode = liveN ? "live" : "history";
    }
    document.querySelectorAll("#modes button").forEach((x) => x.classList.toggle("on", x.dataset.m === mode));
    if (has("jmatrix")) renderJudge();
    loadJournal().catch(() => {});
  }
  document.querySelectorAll("#modes button").forEach((b) => b.onclick = () => {
    mode = b.dataset.m; modeTouched = true; document.querySelectorAll("#modes button").forEach((x) => x.classList.toggle("on", x === b));
    if (fc && has("jmatrix")) renderJudge();
  });

  function refresh() { loadFeeds().catch(() => {}); loadBrains().catch(() => {}); loadJudge().catch(() => {}); }
  window.TSTSections = { refresh };
  refresh();
  setInterval(refresh, 60000);
})();
