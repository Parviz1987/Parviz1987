// Xəbər bloku: 1-hour candles with the news rules' firings, the mood by topic over 24 hours, the latest headlines
// with the Reader's labels, what the block says now and the book with the Judge's record.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const pct = (v) => (v == null ? "—" : Math.round(v * 100) + " %");
  const NAMES = { XAU: "Qızıl", XAG: "Gümüş", XPT: "Platin", XPD: "Palladium" };
  const ST = { "sübut": "✅ sübut", yox: "❌ yox", "zəif": "⚠️ zəif", az: "⏳ az", "xərc": "💸 xərc", "namizəd": "🏁 namizəd (son sınaq gözlənir)" };
  const FCOL = { "əhval": "#e8b94a", Fed: "#4ea1ff", "ABŞ rəqəmi": "#ff9f43", "geosiyasət": "#ef476f", "tələb-təklif": "#3fb27f",
    "axın sıçrayışı": "#c77dff", "böyük xəbər": "#ffffff" };
  const load = (k, d) => { try { return JSON.parse(localStorage.getItem("tst_nw_" + k)) ?? d; } catch (e) { return d; } };
  const save = (k, v) => { try { localStorage.setItem("tst_nw_" + k, JSON.stringify(v)); } catch (e) { /* fine */ } };
  let sym = load("sym", "XAU"), cnt = load("cnt", 120), data = null;
  const ny = (t) => new Date(t * 1000).toLocaleString("en-GB", { timeZone: "America/New_York", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  function seg(el, items, cur, on) {
    el.innerHTML = items.map(([k, n]) => `<button class="${String(k) === String(cur) ? "on" : ""}" data-k="${k}">${esc(n)}</button>`).join("");
    el.querySelectorAll("button").forEach((b) => b.onclick = () => on(b.dataset.k));
  }
  function draw() {
    if (!data || !data.candles || !data.candles.length) return;
    const fam = Object.fromEntries((data.book || []).map((r) => [r.id, r]));
    const seen = new Set((data.fired || []).map((f) => f.rule + "|" + f.dir + "|" + f.i));
    const marks = (data.fired || []).filter((f) => !seen.has(f.rule + "|" + f.dir + "|" + (f.i - 1))).map((f) => ({
      i: f.i, dir: f.dir, c: FCOL[(fam[f.rule] || {}).family] || "#e8b94a", label: ((fam[f.rule] || {}).name || f.rule) + ": " + (f.note || "") }));
    drawChart($("cv"), $("tip"), data.candles, null, "1h", { show: Math.min(cnt, data.candles.length), ema: true, sub: "none", ext: { marks } });
  }
  function topics() {
    const t = data.topics || {};
    const rows = Object.entries(t).sort((a, b) => b[1].n - a[1].n);
    $("facs").innerHTML = (rows.length ? `<div class="tbl"><table class="sc"><tr><th>Mövzu</th><th>Başlıq</th><th>▲</th><th>▼</th><th>Əhval</th></tr>` +
      rows.map(([k, x]) => `<tr><td>${esc(k)}</td><td class="c">${x.n}</td><td class="c up">${x.up}</td><td class="c down">${x.down}</td>
        <td class="c ${x.score > 0 ? "up" : x.score < 0 ? "down" : ""}">${x.score > 0 ? "+" : ""}${x.score}</td></tr>`).join("") + "</table></div>"
      : "<p class='note'>Son 24 saatda bu metal üçün qiymətləndirilmiş başlıq yoxdur.</p>") +
      `<div class="tbl"><table class="sc"><tr><th>Vaxt (NY)</th><th>Başlıq</th><th>Mövzu</th><th>Oxuyucu</th></tr>` +
      (data.headlines || []).map((h) => `<tr><td class="mut">${ny(h.ts)}</td><td>${esc(h.title || "—")} <span class="note">${esc(h.source || "")}</span></td>
        <td>${esc(h.topic)}</td><td class="c ${h.dir === "up" ? "up" : h.dir === "down" ? "down" : ""}">${h.dir === "up" ? "▲" : h.dir === "down" ? "▼" : "·"} ${h.strength}</td></tr>`).join("") + "</table></div>";
  }
  function nowBox() {
    const n = data.now; if (!n) { $("now").innerHTML = "<p class='note'>məlumat yoxdur</p>"; return; }
    const p = n.vote.p, book = Object.fromEntries((data.book || []).map((r) => [r.id, r]));
    const jl = (m) => { const r = n.judge[m] || {}; return r.nh ? `${r.nh} haldan ${pct(r.hit_rate)} düz (hədd ${pct(r.bar)}) · ${ST[r.status] || esc(r.status || "")}` : "hələ nəticə yoxdur"; };
    $("nowt").textContent = "indi";
    $("now").innerHTML = `<div class="tanow">
      <div><div class="big ${p > 0.5 ? "up" : p < 0.5 ? "down" : ""}">${Math.abs(p - 0.5) < 0.01 ? "fikir yoxdur" : p > 0.5 ? "▲ yuxarı" : "▼ aşağı"} · ${pct(p)}</div>
        <p class="note">«Xəbər» səsi (15 dəqiqə – 1 gün proqnozuna gedir): ${esc(n.vote.basis)}</p><p class="note">Hakim (1 saat): ${jl("xeber")}</p></div>
      <div><p><b>İndi işləyən xəbər qaydaları:</b></p><ul class="tarules">${n.rules.map((r) => `<li><span style="color:${FCOL[(book[r.rule] || {}).family] || "#888"}">${r.dir > 0 ? "▲" : "▼"}</span> ${esc((book[r.rule] || {}).name || r.rule)} <span class="note">${esc(r.note || "")}</span></li>`).join("") || "<li class='note'>yoxdur</li>"}</ul></div>
      <div><p class="note">Rəqəmin ilk saatı («Hadisə sürprizi», fundamental blok): ${jl("surprise")}</p>
        <p class="note">Başlıqları Oxuyucu (AI) qiymətləndirir: metal, istiqamət, güc 0–3, mövzu. Eyni xəbərin surətləri bir dəfə oxunur.</p></div></div>
      <p class="note">Bu, sübut olmayan fikirdir: AL / SAT yalnız Hakimin sübutu ilə göstərilir.</p>`;
  }
  function agentsBox() {
    const ny = (t) => (t ? new Date(t * 1000).toLocaleString("en-GB", { timeZone: "America/New_York", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) + " NY" : "—");
    const num = (a) => a.value == null ? "—" : a.unit === "tarix" ? String(Math.round(a.value)).replace(/(\d{4})(\d{2})(\d{2})/, "$1-$2-$3")
      : Number(a.value).toLocaleString("en-US", { maximumFractionDigits: 3 }) + " " + a.unit;
    const groups = {};
    (data.agents || []).forEach((a) => (groups[a.group] = groups[a.group] || []).push(a));
    $("agents").innerHTML = Object.entries(groups).map(([g, list]) => `<p><b>${esc(g)}</b></p><div class="tbl"><table class="sc">
      <tr><th>Agent</th><th>Son təsdiqlənmiş rəqəm</th><th>Dövr</th><th>Mənbələr</th><th>Son cəhd</th><th>Növbəti</th></tr>` +
      list.map((a) => `<tr><td>${esc(a.name)}</td><td><b>${esc(num(a))}</b></td><td>${esc(a.period || "—")}</td>
        <td class="note">${(a.sources || []).map((s, i) => `<a href="${esc(s.url)}" rel="noopener noreferrer" target="_blank">${i + 1}</a>`).join(" · ") || "—"}</td>
        <td class="note">${a.last_ts ? (a.last_ok ? "✅ " : "⚠️ ") + esc(a.last_note) + " · " + ny(a.last_ts) : "hələ axtarmayıb"}</td>
        <td class="note">${ny(a.next_ts)}</td></tr>`).join("") + "</table></div>").join("") ||
      "<p class='note'>agent yoxdur</p>";
  }
  function bookBox() {
    $("book").innerHTML = (data.book || []).map((r) => {
      const x = r.record, rr = x && x.rr;
      return `<div class="tarule"><b><i style="display:inline-block;width:10px;height:10px;border-radius:3px;background:${FCOL[r.family] || "#555"}"></i> ${esc(r.name)}</b>
        <span class="note">${x ? `${x.n} saat, ${pct(x.hit_rate)} düz, ${ST[x.status] || esc(x.status)}${rr ? ` · stop+hədəf: hədəfə ${pct(rr.target_share)}, ${rr.net_r >= 0 ? "+" : ""}${rr.net_r.toFixed(2)} R` : ""}` : "hələ ölçülməyib"}</span>
        <details><summary class="note">necə işləyir</summary><p class="note">${esc(r.how)}</p>
          <p class="note"><b>Siqnal:</b> ${esc(r.signal)} <b>Ləğv:</b> ${esc(r.void)}</p><p class="note"><b>Mənbə:</b> ${esc(r.source)}</p></details></div>`;
    }).join("");
  }
  const home = $("wrapc").parentNode, after = $("wrapc").nextSibling;
  function setBig(on) { if (on) document.body.appendChild($("wrapc")); else home.insertBefore($("wrapc"), after);
    $("wrapc").classList.toggle("full", on); document.body.classList.toggle("noscroll", on); setTimeout(draw, 30); }
  $("big").onclick = () => setBig(true); $("small").onclick = () => setBig(false);
  addEventListener("keydown", (e) => { if (e.key === "Escape") setBig(false); });
  async function go() {
    seg($("sym"), Object.entries(NAMES), sym, (k) => { sym = k; save("sym", k); go(); });
    seg($("cnt"), [[60, "60"], [120, "120"], [250, "250"]], cnt, (k) => { cnt = +k; save("cnt", cnt); go(); });
    try { const r = await fetch(`/api/xeber?symbol=${sym}`, { credentials: "same-origin" }); if (!r.ok) return; data = await r.json(); } catch (e) { return; }
    $("upd").textContent = "yeniləndi " + new Date().toLocaleTimeString("en-GB", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" }) + " NY";
    draw(); nowBox(); agentsBox(); topics(); bookBox();
  }
  go(); setInterval(go, 120000);
})();
