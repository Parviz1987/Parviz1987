/* Results board: what we expect now, the score, and what we said versus what happened. Plain words, New York time. */
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const NAMES = { XAU: "Qızıl", XAG: "Gümüş", XPT: "Platin", XPD: "Palladium" };
let sym = "XAU", hz = "1h";
try { sym = localStorage.getItem("tst_sym") || sym; hz = localStorage.getItem("tst_res_h") || hz; } catch (e) {}

const f = (x) => x == null ? "—" : (x >= 100 ? x.toFixed(2) : x.toFixed(3));
const pc = (x) => x == null ? "—" : Math.round(x * 100) + " %";
const NY = { timeZone: "America/New_York" };
const tm = (ts) => new Date(ts * 1000).toLocaleTimeString("az", { ...NY, hour: "2-digit", minute: "2-digit" });
const dt = (ts) => new Date(ts * 1000).toLocaleString("az", { ...NY, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const day = (h) => ["1d", "3d", "1w", "10d", "1mo"].includes(h);
const when = (ts, h) => day(h) ? dt(ts) : tm(ts);
const left = (ts) => { const m = Math.round((ts - Date.now() / 1000) / 60);
  return m <= 0 ? "yoxlanır" : m < 60 ? m + " dəq sonra" : m < 1440 ? Math.floor(m / 60) + " saat " + (m % 60) + " dəq sonra" : Math.round(m / 1440) + " gün sonra"; };

async function api(path) {
  const r = await fetch(path, { credentials: "same-origin" });
  if (r.status === 401) { location.href = "/login"; throw new Error("login"); }
  return r.json();
}

function metals() {
  $("metals").innerHTML = Object.entries(NAMES).map(([k, n]) => `<button data-s="${k}" class="${k === sym ? "on" : ""}">${n}</button>`).join("");
  document.querySelectorAll("#metals button").forEach((b) => b.onclick = () => { sym = b.dataset.s; save(); metals(); load(); loadSim().catch(() => {}); loadAnalysts().catch(() => {}); });
}
function save() { try { localStorage.setItem("tst_sym", sym); localStorage.setItem("tst_res_h", hz); } catch (e) {} }

function renderExpect(d) {
  $("pnow").textContent = d.price_now ? `${d.name} indi ${f(d.price_now)} $` : "";
  $("expect").innerHTML = d.expect.map((e) => {
    if (e.lo80 == null) return `<div class="exp"><span class="h">${esc(e.name)}</span><span class="note">Hələ proqnoz yoxdur: tarixçə yığılır.</span></div>`;
    const dir = e.direction
      ? `<span class="dir ${e.direction.up ? "up" : "down"}">${e.direction.up ? "↑ yuxarı" : "↓ aşağı"} · ${pc(e.direction.p)}</span>
         <span class="note">${esc(e.direction.method)}${e.direction.condition ? " (yalnız bu şəraitdə sübut olunub)" : ""}</span>`
      : `<span class="note">İstiqamət: göstərilmir — Hakimin sübutu yoxdur.</span>`;
    return `<div class="exp"><span class="h">${esc(e.name)}</span>
      <span>${esc(d.name)} <b>${when(e.target_t, e.horizon)}</b>-də (NY) 80 % ehtimalla
        <span class="big">${f(e.lo80)} – ${f(e.hi80)}</span> arasında olacaq
        <span class="note">· 50 % ehtimalla ${f(e.lo50)} – ${f(e.hi50)} · yoxlanma ${left(e.target_t)}</span><br>${dir}</span></div>`;
  }).join("");
}

function light(v, good, ok) { return v == null ? "⚪" : v >= good ? "🟢" : v >= ok ? "🟡" : "🔴"; }
function renderScore(d) {
  $("score").innerHTML = `<table class="sc"><tr><th>Üfüq</th><th>Koridor tutdu<br><span class="note">hədəf 80 %</span></th>
    <th>İstiqamət düz çıxdı<br><span class="note">seçici konsensus</span></th><th>Keçməli hədd</th><th>Yoxlama</th></tr>` +
    d.score.map((s) => {
      const c = s.cover80 == null ? "—" : `${s.cover80 >= 0.74 && s.cover80 <= 0.88 ? "🟢" : s.cover80 >= 0.65 ? "🟡" : "🔴"} ${pc(s.cover80)}`;
      const dir = !s.dir_n ? "⚪ fikir bildirməyib" : `${light(s.dir_hit, s.bar + 0.02, s.bar - 0.02)} ${pc(s.dir_hit)}`;
      return `<tr><td>${esc(s.name)}</td><td class="c">${c}</td><td class="c">${dir}</td><td class="c">${pc(s.bar)}</td>
        <td class="c">${s.n || 0}${s.dir_n ? " / " + s.dir_n : ""}</td></tr>`;
    }).join("") + `</table><p class="note">«Yoxlama»: koridor üçün yoxlanan proqnoz sayı / istiqamət göstərilən proqnoz sayı.
      Az yoxlamada faiz təsadüfi ola bilər: 100-dən az olanda hələ nəticə çıxarmayın.</p>`;
}

function renderHz(d) {
  $("hz").innerHTML = d.expect.map((e) => `<button data-h="${e.horizon}" class="${e.horizon === hz ? "on" : ""}">${esc(e.name)}</button>`).join("");
  document.querySelectorAll("#hz button").forEach((b) => b.onclick = () => { hz = b.dataset.h; save(); load(); });
}

function renderPast(d) {
  const done = d.past.filter((p) => p.price1 != null);
  $("past").innerHTML = (done.length ? done.slice(0, 15).map((p) => {
    const inR = p.in80 === 1;
    const dirTxt = p.cp == null || p.cp === 0.5 ? "<span class='note'>istiqamət: fikir yox</span>"
      : `istiqamət: dedik <b>${p.cp > 0.5 ? "yuxarı" : "aşağı"}</b> → ${p.price1 > p.price0 ? "qalxdı" : p.price1 < p.price0 ? "endi" : "dəyişmədi"} ${p.chit === 1 ? "✅" : p.chit === 0 ? "❌" : ""}`;
    return `<div class="prow"><span class="ic">${inR ? "✅" : "❌"}</span>
      <span><b>${when(p.issued_t, d.horizon)} → ${when(p.target_t, d.horizon)}</b> NY · başlanğıc ${f(p.price0)}<br>
      dedik <b>${f(p.lo80)} – ${f(p.hi80)}</b> → oldu <b>${f(p.price1)}</b> ${inR ? "<span class='up'>koridora düşdü</span>" : "<span class='down'>koridordan çıxdı</span>"}<br>${dirTxt}</span></div>`;
  }).join("") : "<p class='note'>Bu üfüqdə hələ yoxlanmış canlı proqnoz yoxdur. Yoxlanma vaxtı çatanda burada görünəcək.</p>");
  drawCorridor($("cv"), d);
}

function drawCorridor(cv, d) {
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
  cv.width = W * dpr; cv.height = H * dpr;
  const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
  g.font = "11px " + css("--mono");
  const past = d.past.slice().reverse(), price = d.price;
  if (!past.length && !price.length) { g.fillStyle = css("--muted"); g.fillText("Hələ məlumat yoxdur.", 12, 24); return; }
  const ts = [...past.map((p) => p.issued_t), ...past.map((p) => p.target_t), ...price.map((p) => p[0])];
  const vs = [...past.flatMap((p) => [p.lo80, p.hi80]), ...price.map((p) => p[1])].filter((v) => v != null);
  const t0 = Math.min(...ts), t1 = Math.max(...ts);
  let lo = Math.min(...vs), hi = Math.max(...vs); const pad = (hi - lo) * 0.06 || 1; lo -= pad; hi += pad;
  const padL = 8, padR = 62, padT = 8, padB = 22;
  const x = (t) => padL + (t - t0) / Math.max(1, t1 - t0) * (W - padL - padR);
  const y = (v) => padT + (hi - v) / (hi - lo) * (H - padT - padB);
  g.strokeStyle = css("--line"); g.fillStyle = css("--muted");
  for (let i = 0; i <= 4; i++) { const v = lo + (hi - lo) * i / 4, yy = Math.round(y(v)) + .5;
    g.beginPath(); g.moveTo(padL, yy); g.lineTo(W - padR, yy); g.stroke(); g.fillText(f(v), W - padR + 4, yy + 4); }
  g.fillText(when(t0, d.horizon), padL, H - 6);
  const l1 = when(t1, d.horizon); g.fillText(l1, W - padR - g.measureText(l1).width, H - 6);
  const gold = css("--gold");
  // each forecast's corridor: drawn over the time it covered (the target candle), 80 % light and 50 % darker
  const step = d.tf_seconds;
  past.forEach((p) => {
    const a = x(p.target_t - step), b = Math.max(a + 2, x(p.target_t));
    g.fillStyle = gold; g.globalAlpha = .18; g.fillRect(a, y(p.hi80), b - a, y(p.lo80) - y(p.hi80));
    g.globalAlpha = .38; g.fillRect(a, y(p.hi50), b - a, y(p.lo50) - y(p.hi50)); g.globalAlpha = 1;
  });
  // the real price
  g.strokeStyle = css("--fg"); g.lineWidth = 1.6; g.beginPath();
  price.forEach((p, i) => { const X = x(p[0] + step), Y = y(p[1]); i ? g.lineTo(X, Y) : g.moveTo(X, Y); }); g.stroke(); g.lineWidth = 1;
  // result of each checked forecast: green inside the 80 % corridor, red outside
  past.filter((p) => p.price1 != null).forEach((p) => {
    g.fillStyle = p.in80 === 1 ? css("--up") : css("--down");
    g.beginPath(); g.arc(x(p.target_t), y(p.price1), 3.5, 0, 7); g.fill();
  });
  // "now" line
  const nx = x(Date.now() / 1000);
  if (nx > padL && nx < W - padR) { g.strokeStyle = css("--muted"); g.setLineDash([4, 4]); g.beginPath(); g.moveTo(nx, padT); g.lineTo(nx, H - padB); g.stroke();
    g.setLineDash([]); g.fillStyle = css("--muted"); g.fillText("indi", nx + 3, padT + 10); }
}

let smode = "history";
const SKIP = ["rw"];
function usd(x) { return x == null ? "—" : (x >= 0 ? "+" : "−") + Math.abs(x * 1000).toFixed(2) + " $"; }
async function loadSim() {
  $("smode").innerHTML = [["history", "Tarixçə"], ["live", "Canlı"]].map(([k, n]) => `<button data-m="${k}" class="${k === smode ? "on" : ""}">${n}</button>`).join("");
  document.querySelectorAll("#smode button").forEach((b) => b.onclick = () => { smode = b.dataset.m; loadSim(); });
  $("simmap").innerHTML = "<p class='note'>Hesablanır… (bir neçə saniyə)</p>";
  const d = await api(`/api/simulate?symbol=${sym}&mode=${smode}`);
  const methods = Object.keys(d.method_names).filter((m) => !SKIP.includes(m) && d.horizons.some((h) => h.methods[m]));
  if (!methods.length) { $("simmap").innerHTML = "<p class='note'>Hələ oynanılacaq proqnoz yoxdur.</p>"; $("simbest").innerHTML = ""; return; }
  const short = (m) => d.method_names[m].replace(/\s*\(.*\)/, "");
  $("simmap").innerHTML = `<table class="sc"><tr><th>Üfüq</th><th>Almaq və saxlamaq</th>${methods.map((m) => `<th>${esc(short(m))}</th>`).join("")}</tr>` +
    d.horizons.map((h) => `<tr><td>${esc(h.name)}</td><td class="c mut">${usd(h.buy_hold && h.buy_hold.avg)}</td>` + methods.map((m) => {
      const r = h.methods[m];
      if (!r || !r.n) return `<td class="c mut">·</td>`;
      const cls = r.status === "sübut" ? "sübut" : r.status === "az" ? "az" : r.avg > 0 ? "" : "yox";
      return `<td class="cell ${cls}" title="${r.n} sövdələşmə · uduş ${pc(r.win)} · stop ${pc(r.stops)} · hədəf ${pc(r.targets)} · risk-gəlir ${r.ratio == null ? "—" : r.ratio.toFixed(2)} · yarılar: ${r.halves ? r.halves.map(usd).join(" / ") : "—"}${r.steady ? " (hər iki yarıda müsbət)" : ""}">${usd(r.avg)}${r.status === "sübut" ? " ✓" : ""}${r.steady && r.status !== "sübut" ? " ◐" : ""}<br><span class="note">${r.n}</span></td>`;
    }).join("") + "</tr>").join("") + `</table><p class="note">Xanadakı kiçik rəqəm: sövdələşmə sayı. Qırmızı = zərər, sarı = hələ az sövdələşmə (100-dən az),
      ✓ = qazanc sübut olunub, ◐ = dövrün hər iki yarısında müsbət (dayanıqlı, amma hələ sübut deyil). Hamısı tam xərcdən sonra. «Almaq və saxlamaq»: heç bir proqnoz olmadan sadəcə almaq — müqayisə üçün.</p>`;
  const proven = [];
  d.horizons.forEach((h) => Object.entries(h.methods).forEach(([m, r]) => { if (r.status === "sübut") proven.push({ h, m, r }); }));
  $("simbest").innerHTML = proven.length
    ? "<h3 class='sub'>Pul qazandırdığı sübut olunanlar</h3>" + proven.map(({ h, m, r }) =>
        `<div class="prow"><span class="ic">✅</span><span><b>${esc(d.method_names[m])}</b> · ${esc(h.name)} · ${r.n} sövdələşmə<br>
        1000 $-lıq sövdələşmədə orta ${usd(r.avg)} · uduş ${pc(r.win)} · ən böyük düşüş ${usd(r.max_dd)} · risk-gəlir ${r.ratio == null ? "—" : r.ratio.toFixed(2)} · ${r.steady ? "hər iki yarıda müsbət" : "yarılardan birində mənfi"}</span></div>`).join("")
    : `<p class="note"><b>Hələ heç bir üsul pul qazandırdığını sübut etməyib.</b> Bu o deməkdir ki, indi ticarət açmaq üçün əsas yoxdur.
       Sübut gələndə burada yaşıl ✓ ilə görünəcək.</p>`;
}

let ahz = "1h", adata = null;
const BRAIN_NAMES = { strateq: "Strateq (Claude)", brain2: "İkinci beyin (OpenAI)", strategist: "Strateq", analyst2: "İkinci analitik", reviewer: "Nəzarətçi (müzakirə)", reader: "Oxuyucu", hunter: "Rəqəm ovçusu", scout: "Kəşfiyyatçı" };
function renderAnalysts() {
  const d = adata; if (!d) return;
  $("ahz").innerHTML = d.desks.map((x) => `<button data-h="${x.horizon}" class="${x.horizon === ahz ? "on" : ""}">${esc(x.name)}</button>`).join("");
  document.querySelectorAll("#ahz button").forEach((b) => b.onclick = () => { ahz = b.dataset.h; renderAnalysts(); });
  const desk = d.desks.find((x) => x.horizon === ahz) || d.desks[0];
  const cell = (r) => !r || !r.nh ? `<td class="c mut">·</td>` :
    `<td class="c ${r.hit_rate > r.bar ? "" : "mut"}">${pc(r.hit_rate)} <span class="note">/ ${pc(r.bar)} · ${r.nh}</span></td>`;
  const rows = desk.rows.slice().sort((a, b) => b.weight - a.weight);
  $("analysts").innerHTML = `<table class="sc"><tr><th>Analitik</th><th>Ailə</th><th>Canlı: düz / hədd · say</th><th>Tarixçə: düz / hədd · say</th><th>Çəki</th></tr>` +
    rows.map((r) => `<tr><td>${esc(r.name)}</td><td class="mut">${esc(r.family)}</td>${cell(r.live)}${cell(r.history)}
      <td class="c">${r.weight > 0 ? "<b>" + r.weight.toFixed(1) + "</b>" : "<span class='mut'>0</span>"}</td></tr>`).join("") + "</table>";
  $("brainscore").innerHTML = d.brains.length
    ? `<table class="sc"><tr><th>Beyin</th><th>Nə vaxt</th><th>Üfüq</th><th>Düz</th><th>Say</th></tr>` +
      d.brains.map((b) => `<tr><td>${esc(BRAIN_NAMES[b.brain] || b.brain)}</td><td>${esc(b.when)}</td><td>${esc(b.horizon)}</td>
        <td class="c" title="${esc(Object.entries(b.by_metal || {}).map(([m, x]) => m + ": " + Math.round(x.hit_rate * 100) + " % düz, " + x.n + " dəfə, xərcdən sonra " + (x.net_avg * 100).toFixed(3) + " %").join(" · "))}">${pc(b.hit_rate)}</td><td class="c mut">${b.n}</td></tr>`).join("") + "</table>"
    : "<p class='note'>Hələ yoxlanmış beyin fikri yoxdur: ilk nəticələr fikir verildikdən 1 saat sonra gəlir.</p>";
  // Block 17: the source checker — numbers a brain wrote that it was not given (30 days)
  const ck = d.checks || [];
  if (ck.length) $("brainscore").innerHTML += `<p class="note" style="margin-top:10px"><b>Mənbə yoxlayıcısı</b> (30 gün): beyin ona verilməyən rəqəm yazıbsa, o, uydurma sayılır və sizə göstərilmir.</p>
    <table class="sc"><tr><th>Beyin</th><th>Cavab</th><th>Uydurma rəqəmli cavab</th><th>Uydurma rəqəm</th></tr>` +
    ck.map((c) => `<tr><td>${esc(BRAIN_NAMES[c.slot] || c.slot)}</td><td class="c mut">${c.answers}</td>
      <td class="c ${c.bad_share > 0.1 ? "down" : ""}">${pc(c.bad_share)}</td><td class="c mut">${c.invented || 0}</td></tr>`).join("") + "</table>";
}
async function loadAnalysts() { adata = await api(`/api/analysts?symbol=${sym}`); renderAnalysts(); }

async function loadHyp() {
  const d = await api("/api/hypotheses");
  $("hreg").textContent = "qeyd: " + dt(d.registered) + " NY";
  const ST = { "sübut": "✅ sübut", yox: "❌ yox", az: "⏳ az məlumat", "bağlandı": "⛔ bağlandı" };
  $("hyp").innerHTML = `<table class="sc"><tr><th></th><th>Fərziyyə</th><th>Düz</th><th>Hədd</th><th>Spreddən sonra (qeyd olunduğu kimi)</th><th>Say</th><th>Hökm</th></tr>` +
    d.items.map((h) => `<tr><td class="mut">${h.id}</td><td><b>${esc(h.name)}</b><br><span class="note">${esc(h.idea)} · Mənbə: ${esc(h.source)}</span></td>
      <td class="c">${pc(h.hit_rate)}</td><td class="c mut">${pc(h.bar)}</td>
      <td class="c">${h.net_avg == null ? "—" : usd(h.net_avg)}</td><td class="c mut">${h.n}</td><td class="c">${ST[h.status] || h.status}</td></tr>`).join("") +
    "</table><p class='note'>«Spreddən sonra»: 1000 $-lıq bir sövdələşmənin orta nəticəsi; H1–H8 qeyd olunduğu kimi yalnız spredlə ölçülür, əsas hədəflər isə tam xərclə. «Az məlumat»: sübut üçün hələ yetərli yeni proqnoz yoxdur.</p>";
  if (d.v) {
    $("vreg").textContent = "qeyd: " + dt(d.v_registered) + " NY · hədd p < " + d.v_p_bar.toFixed(3) + " · hamısı pulla, tam xərcdən sonra";
    $("vtests").innerHTML = `<table class="sc"><tr><th></th><th>Sınaq</th><th>Düz</th><th>Tam xərcdən sonra</th><th>Hal</th><th>p</th><th>Hökm</th></tr>` +
      d.v.map((h) => `<tr><td class="mut">${h.id}</td><td><b>${esc(h.name)}</b><br><span class="note">${esc(h.idea)}</span></td>
        <td class="c">${pc(h.hit_rate)}</td><td class="c">${h.net_avg == null ? "—" : usd(h.net_avg)}</td><td class="c mut">${h.n}</td>
        <td class="c mut">${h.p == null ? "—" : h.p.toFixed(3)}</td><td class="c">${ST[h.status] || h.status}</td></tr>`).join("") + "</table>";
  }
  if (d.focus) {
    $("freg").textContent = "qeyd: " + dt(d.focus_registered) + " NY · hədd p < " + d.focus_p_bar.toFixed(4);
    $("focus").innerHTML = `<table class="sc"><tr><th></th><th>Hədəf</th><th>Düz</th><th>Hədd</th><th>Tam xərcdən sonra</th><th>Say</th><th>Hökm</th></tr>` +
      d.focus.map((h) => `<tr><td class="mut">${h.id}</td><td><b>${esc(h.name)}</b><br><span class="note">${esc(h.idea)}</span></td>
        <td class="c">${pc(h.hit_rate)}</td><td class="c mut">${pc(h.bar)}</td>
        <td class="c">${h.net_avg == null ? "—" : usd(h.net_avg)}</td><td class="c mut">${h.n}</td><td class="c">${ST[h.status] || h.status}</td></tr>`).join("") + "</table>";
  }
}

// Block 21: the futures tests
async function loadFut() {
  const d = await api("/api/futstudy");
  const st = d.study;
  if (!st) {
    const dl = d.download;
    $("fut").innerHTML = `<p class="note">${dl ? (dl.ok === false ? "Yükləmə: " + esc(dl.msg || (dl.errors || []).join("; ")) : "Məlumat yüklənir…")
      : "Hələ məlumat yoxdur: Databento tarixçəsi yüklənəndən sonra sınaqlar özü hesablanır."}</p>`;
    return;
  }
  $("futwhen").textContent = "hesablandı " + dt(st.computed) + " NY · hədd p < " + (st.p_bar || 0).toExponential(1);
  const NM = { XAU: "Qızıl (GC)", XAG: "Gümüş (SI)", XPT: "Platin (PL)", XPD: "Palladium (PA)" };
  const V = { "sübut": "✅ sübut", yox: "❌ yox", az: "⏳ az" };
  $("fut").innerHTML = Object.entries(st.metals).map(([sym, m]) => {
    const c = st.check[sym] || {};
    return `<h3 class="sub">${NM[sym] || sym} · ${m.bars} dəqiqə (${esc(c.first || "")} – ${esc(c.last || "")}) · xərc: fyuçers ${(m.cost_futures * 100).toFixed(3)} %, Capital ${(m.cost_capital * 100).toFixed(3)} %</h3>
      <table class="sc"><tr><th>Qrup</th><th>Sonra</th><th>Say</th><th>Davam etdi</th><th>Fyuçersdə</th><th>Capital-da</th><th>Hər iki il</th><th>Hökm</th></tr>` +
      m.rows.map((x) => `<tr><td>${esc(x.group)}</td><td class="c">${x.H} dəq</td><td class="c mut">${x.n}</td>
        <td class="c ${x.continues > 0.5 ? "" : "mut"}">${pc(x.continues)}</td><td class="c ${x.net_futures > 0 ? "up" : "down"}">${usd(x.net_futures)}</td>
        <td class="c ${x.net_capital > 0 ? "up" : "down"}">${usd(x.net_capital)}</td><td class="c">${x.both_years ? "✓" : "—"}</td>
        <td class="c">${V[x.verdict] || ""}</td></tr>`).join("") + "</table>" +
      (m.vwap && m.vwap["cəmi"] ? `<p class="note"><b>Həcm (VWAP, 24 saat):</b> qiymət VWAP-dan yuxarı olanda növbəti 1 saatda davam etdi
        ${pc(m.vwap["cəmi"].continues)} (${m.vwap["cəmi"].n} saat) · «davam» strategiyası ${usd(m.vwap["cəmi"].net_continue)},
        «geri dönüş» ${usd(m.vwap["cəmi"].net_revert)} · illər: ${["1-ci il", "2-ci il"].map((y) => m.vwap[y] ? y + " " + pc(m.vwap[y].continues) : "").join(", ")}</p>` : "");
  }).join("");
}

async function load() {
  const d = await api(`/api/results?symbol=${sym}&horizon=${hz}`);
  renderExpect(d); renderScore(d); renderHz(d); renderPast(d);
}
setInterval(() => { $("clock").textContent = "Nyu-York " + new Date().toLocaleTimeString("az", { ...NY, hour: "2-digit", minute: "2-digit" }); }, 1000);
metals(); load(); loadSim().catch(() => {}); loadAnalysts().catch(() => {}); loadHyp().catch(() => {}); loadFut().catch(() => {}); setInterval(() => load().catch(() => {}), 30000);
window.addEventListener("resize", () => load().catch(() => {}));
