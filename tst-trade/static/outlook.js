// «Sabah üçün proqnoz» (owner 2026-11-24): per metal ONE answer — the unified forecast — with the 1-day range and the
// voices that explain it (Strateq, Qrafik analitiki, Tərəzi, the analysts' vote) and their records.
// Indication only, and honest about proof: a lean is shown as a lean, never as a proven forecast.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const NAMES = { XAU: "Qızıl", XAG: "Gümüş", XPT: "Platin", XPD: "Palladium" };
  const pct = (p) => (p == null ? "—" : Math.round(p * 100) + " %");
  const px = (v) => (v == null ? "—" : v >= 100 ? v.toFixed(2) : v.toFixed(3));
  const ny = (t) => new Date(t * 1000).toLocaleString("az-Latn-AZ", { timeZone: "America/New_York", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  const dirWord = (p) => (p == null ? "—" : Math.abs(p - 0.5) < 0.03 ? "fikir yox" : p > 0.5 ? "yuxarı" : "aşağı");
  const ev = (x) => `<span title="${esc(x.why)}">${esc(x.block)}: ${esc(x.name)} ${pct(x.p)}</span>`;
  const PROOF = { "sübut": "✅ sübut var", yox: "❌ istiqamət sübutu yoxdur", az: "⏳ hələ az yoxlanıb" };
  async function load() {
    let d;
    try { const r = await fetch("/api/outlook", { credentials: "same-origin" }); if (!r.ok) return; d = await r.json(); } catch (e) { return; }
    if (!$("outlook")) return;
    $("olnote").textContent = "yeniləndi " + ny(d.ts) + " NY";
    $("outlook").innerHTML = d.metals.map((m) => {
      const s = m.strateq, t = m.terazi, v = m.vote, rg = m.range;
      const cls = m.lean_dir > 0 ? "up" : m.lean_dir < 0 ? "down" : "mut";
      const arrow = (m.lean_dir || m.weak_dir) > 0 ? "▲ " : (m.lean_dir || m.weak_dir) < 0 ? "▼ " : "";
      // At a glance: the lean, the unified forecast, the two ranges and the analysts' vote. Everything else (proof,
      // the three-way split, the strategist's reasons, the chart reader, the scale, scenarios, evidence) is one click away.
      const vp = m.vahid ? m.vahid.p : null;
      return `<div class="olc">
        <div class="olh"><b>${NAMES[m.symbol]}</b><span class="ol-lean ${cls}">${arrow}${esc(m.lean)}</span></div>
        ${m.vahid ? `<div class="olv"><span>Vahid proqnoz · ${PROOF[m.vahid.proof] || "⏳ hələ az yoxlanıb"}</span>
          <b class="${vp >= 0.53 ? "up" : vp <= 0.47 ? "down" : "mut"}">${dirWord(vp)} ${pct(vp)}</b></div>` : ""}
        <div class="olr"><span>Aralıq (80 %)</span><span class="num">${rg ? px(rg.lo80) + " – " + px(rg.hi80) : "—"}</span></div>
        <div class="olr"><span>Aralıq (50 %)</span><span class="num">${rg ? px(rg.lo50) + " – " + px(rg.hi50) : "—"}</span></div>
        <div class="olr"><span>Səslər</span><span>Strateq ${s ? dirWord(s.p) + " " + pct(s.p) : "—"} · Qrafik ${m.chartist ? dirWord(m.chartist.p) : "—"} · ▲ ${v.up} ▼ ${v.down}</span></div>
        <details class="olmore"><summary>Ətraflı: sübut, səbəblər, ssenarilər</summary>
        <div class="note">${esc(m.agree)}${m.proof === "sübut" ? " · 1 günlük masada sübutlu üsul: " + esc(m.proof_method || "") : ""}</div>
        ${m.vahid ? `${m.three_way ? `<div class="note">Üç nəticə: ▲ ${pct(m.three_way.up)} · ▼ ${pct(m.three_way.down)} · neytral (xərcdən kiçik hərəkət, ±${(m.three_way.band * 100).toFixed(2)} %) ${pct(m.three_way.neutral)}</div>` : ""}
          <div class="note">Öz-özünü sınaq: ${m.vahid.self_test.n || 0} proqnoz, düz ${pct(m.vahid.self_test.hit_rate)} (hədd ${pct(m.vahid.self_test.bar)}) · canlı: ${m.vahid.live.n || 0} yoxlanıb${m.vahid.live.n ? ", düz " + pct(m.vahid.live.hit_rate) : ""}</div>` : ""}
        ${m.breakeven ? `<div class="note">Xərci ödəmək üçün lazım olan düzlük: ${pct(m.breakeven)}${m.breakeven > 0.6 ? " — bu brokerdə ticarət üçün çox bahadır" : ""}</div>` : ""}
        ${rg ? `<div class="note">80 % aralığın real tutması: ${pct(rg.cover80)}</div>` : ""}
        <div class="olr"><span>Strateq (AI)</span><span>${s ? `${dirWord(s.p)} ${pct(s.p)}${s.calibrated ? " (kalibrli)" : ""} <span class="note">· indiyə qədər: düz ${s.record.right}, səhv ${s.record.wrong}</span>` : "kart hələ yoxdur"}</span></div>
        ${s ? `<div class="olw"><b>Səbəb:</b> ${esc(s.scenario || "—")}</div>
        <div class="olw"><b>Əks ssenari:</b> ${esc(s.counter || "—")}</div>
        <div class="olw"><b>Fikri zəiflədər:</b> ${esc(s.invalidation || "—")}</div>
        <div class="olw note">Növbəti yenilənmə: ${esc(s.next_update || "—")} · ${ny(s.ts)} NY</div>` : ""}
        <div class="olr"><span>Qrafik analitiki</span><span>${m.chartist ? `${dirWord(m.chartist.p)} ${pct(m.chartist.p)}` : "fikir hələ yoxdur"}</span></div>
        ${m.chartist ? `<div class="olw"><b>Qrafik:</b> ${esc(m.chartist.trend || "")}${m.chartist.levels ? " · " + esc(m.chartist.levels) : ""}${m.chartist.pattern ? " · " + esc(m.chartist.pattern) : ""}</div>` : ""}
        <div class="olr"><span>Tərəzi (Hakim)</span><span>${t ? (String(t.basis || "").startsWith("çəkilər yoxdur") ? `<span class="note">Hakim hələ heç bir analitikə güvənmir</span>` : `${dirWord(t.p)} ${pct(t.p)} <span class="note">· ${esc(t.basis || "")}</span>`) : "—"}</span></div>
        ${m.scenarios ? `<div class="olw"><b>Ssenarilər (1 gün):</b><br>${m.scenarios.map((x) => x.name === "aralıq"
          ? `↔ aralıq ${pct(x.p)}: ${px(x.from)} – ${px(x.to)} <span class="note">(xərcdən kiçik hərəkət)</span>`
          : `${x.name === "yuxarı" ? "▲" : "▼"} ${x.name} ${pct(x.p)}: ${px(x.from)}-dən ${x.name === "yuxarı" ? "yuxarı" : "aşağı"}, ehtimal olunan ${px(x.mid)}, uzaq hədd ${px(x.far)}`).join("<br>")}</div>` : ""}
        ${m.evidence && (m.evidence.pro.length || m.evidence.con.length) ? `<div class="olw"><b>${m.evidence.lean ? "Lehinə dəlillər" : "Yuxarı deyənlər"}:</b> ${m.evidence.pro.map(ev).join("; ") || "yoxdur"}</div>
        <div class="olw"><b>${m.evidence.lean ? "Əleyhinə dəlillər (əks dəlil)" : "Aşağı deyənlər"}:</b> ${m.evidence.con.map(ev).join("; ") || "yoxdur"}</div>` : ""}
        </details>
      </div>`;
    }).join("");
  }
  load();
  setInterval(load, 120000);
})();
