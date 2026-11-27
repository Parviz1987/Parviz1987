// «Analitiklər nə deyir» on the panel (owner 2026-11-27 04:57 NY: «analitiklərin mənə konkret rəyi lazımdır ki, filan
// qiymətdə qalxacaq, filan qiymətdə düşəcək»; «Əhməd qızılda düz deyir, gümüşdə səhv — qızılını gətirmək olar»).
// For the metal on the chart and one horizon: each analyst's view now (▲ / ▼ and how sure), the price now and where
// it should be (the 80 % range, the same for all: it comes from the market's own volatility), and that analyst's
// record IN THIS METAL on this horizon (right / checked, the last ten) with a plain word: listen / no different from
// chance / comes out the other way / too few yet. A record, not the Judge's proof (that stays on «Nəticələr»).
// Data: the panel's own /api/forecasts (lastFc, static/panel.js) and the record book /api/record (the Analysts page).
(function () {
  "use strict";
  const box = document.getElementById("says");
  if (!box) return;
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const HS = [["15m", "15 dəq"], ["1h", "1 saat"], ["4h", "4 saat"], ["1d", "1 gün"], ["1w", "1 həftə"]];
  const MNAME = { XAU: "Qızıl", XAG: "Gümüş", XPT: "Platin", XPD: "Palladium" };
  const HIDE = new Set(["rw", "up", "garch", "gvz", "consensus", "terazi"]);   // benchmarks, ranges, the back-room combiners
  const ENOUGH = 20, GOOD = 0.55, BAD = 0.45;            // the same thresholds as the Analysts page
  const NY = { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" };
  let hz = "1h", rec = null, recAt = 0;
  try { hz = localStorage.getItem("tst_says_h") || hz; } catch (e) {}
  const price = (x) => x == null ? "—" : x >= 100 ? x.toFixed(2) : x.toFixed(3);

  async function record() {
    if (rec && Date.now() - recAt < 300000) return rec;
    const r = await fetch("/api/record", { credentials: "same-origin" });
    if (!r.ok) throw new Error("record " + r.status);
    rec = await r.json(); recAt = Date.now();
    return rec;
  }
  function word(c) {
    if (!c || !c.n) return ["mut", "qeyd yoxdur"];
    if (c.n < ENOUGH) return ["mut", `hələ az (${c.n})`];
    const s = c.right / c.n;
    return s >= GOOD ? ["up", "dinlə"] : s <= BAD ? ["down", "tərsinə çıxır"] : ["mut", "şansdan fərqi yoxdur"];
  }
  const dots = (last) => `<span class="dots">${[...(last || "")].map((x) => `<i class="${x === "1" ? "y" : "n"}"></i>`).join("")}</span>`;

  let cur = { sym: "XAU", fc: null };       // given by static/panel.js after each forecasts refresh
  async function render() {
    const fc = cur.fc, sym = cur.sym;
    document.getElementById("saysm").textContent = MNAME[sym] || sym;
    const seg = document.getElementById("sayh");
    seg.innerHTML = HS.map(([k, n]) => `<button type="button" data-h="${k}" class="${k === hz ? "on" : ""}">${n}</button>`).join("");
    seg.querySelectorAll("button").forEach((b) => b.onclick = () => {
      hz = b.dataset.h; try { localStorage.setItem("tst_says_h", hz); } catch (e) {} render();
    });
    const card = fc && fc.symbol === sym && fc.cards.find((c) => c.horizon === hz);
    if (!card || !card.methods.length) { box.innerHTML = "<p class='note'>Bu müddət üçün hələ proqnoz yoxdur.</p>"; return; }
    let R = null;
    try { R = await record(); } catch (e) { /* the views are still shown without the record */ }
    const names = fc.method_names || {};
    const short = (m) => String(names[m] || m).split(" (")[0];
    const ms = card.methods.filter((x) => !HIDE.has(x.method));
    const any = ms[0];
    const cell = (m) => R && ((R.methods[m] || {})[sym] || {})[hz];
    const rank = (m) => { const [t] = word(cell(m)); return t === "up" ? 0 : t === "mut" ? 1 : 2; };
    const viewed = ms.filter((x) => x.p_up !== 0.5 && x.method !== "vahid")
      .sort((a, b) => rank(a.method) - rank(b.method) || Math.abs(b.p_up - 0.5) - Math.abs(a.p_up - 0.5));
    const quiet = ms.filter((x) => x.p_up === 0.5 && x.method !== "vahid").map((x) => short(x.method));
    const vahid = ms.find((x) => x.method === "vahid");
    const row = (x, lead) => {
      const up = x.p_up > 0.5, none = x.p_up === 0.5;
      const pct = Math.round(Math.max(x.p_up, 1 - x.p_up) * 1000) / 10;
      const say = none ? "<span class='mut'>fikri yoxdur</span>" :
        `<b class="${up ? "up" : "down"}">${up ? "▲ qalxacaq" : "▼ düşəcək"}</b> <span class="note">${pct} %${pct < 52 ? " · zəif" : ""}</span>`;
      const c = cell(x.method), [tone, w] = word(c);
      const recd = c && c.n ? `${c.right}/${c.n} düz ${dots(c.last)}` : "";
      return `<div class="sy-r${lead ? " lead" : ""}"><span class="sy-n" title="${esc(names[x.method] || x.method)}">${esc(lead ? "Sistemin son sözü" : short(x.method))}</span>
        <span class="sy-v">${say}</span><span class="sy-b note" title="${esc(x.basis)}">${esc(String(x.basis || "").slice(0, 90))}</span>
        <span class="sy-rec">${tone === "mut" ? `<span class="mut">${w}</span>` : `<b class="${tone}">${w}</b>`} <span class="note">${recd}</span></span></div>`;
    };
    const tt = any.target_t ? new Date(any.target_t * 1000).toLocaleString("az", { ...NY, day: "2-digit", month: "2-digit" }) : "—";
    box.innerHTML = `<p class="sy-px">Qiymət indi <b>${price(any.price0)}</b> → ${HS.find((h) => h[0] === hz)[1]} sonra (${tt} NY)
        80 % ehtimalla <b>${price(any.lo80)} – ${price(any.hi80)}</b> arasında <span class="note">(bazarın öz dəyişkənliyindən; hamı üçün eyni)</span></p>` +
      (vahid ? row(vahid, true) : "") + viewed.map((x) => row(x, false)).join("") +
      (quiet.length ? `<p class="note">İndi fikri olmayanlar: ${quiet.map(esc).join(", ")}.</p>` : "") +
      `<p class="note">«Dinlə / tərsinə çıxır» — bu analitikin <b>${MNAME[sym] || sym}</b>da, bu müddətdə yoxlanmış fikirlərinin sadə sayıdır
        (ən az ${ENOUGH} fikir; 55 %-dən çox düz — dinlə, 45 %-dən az — tərsinə). Hakimin sübutu deyil. Hamısı və hər fikrin jurnalı:
        <a href="/analitikler">Analitiklər</a>.</p>`;
  }
  window.renderSays = (sym, fc) => { cur = { sym, fc }; render().catch(() => {}); };
})();
