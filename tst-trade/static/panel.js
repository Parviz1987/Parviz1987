/* TST Trade panel: prices, candles, forecast cards, the Judge's table and the journal. */
const $ = (id) => document.getElementById(id);
const TFS = ["1m", "5m", "15m", "1h", "4h", "1d", "1w"];
const TF_NAMES = { "1m": "1 dəq", "5m": "5 dəq", "15m": "15 dəq", "1h": "1 saat", "4h": "4 saat", "1d": "1 gün", "1w": "1 həftə" };
const STATUS_AZ = { LIVE: "Canlı", DELAYED: "Gecikir", OFFLINE: "Əlaqə yoxdur", DEMO: "DEMO" };
const VERDICT_AZ = { "sübut": "Sübut olunub", "yox": "Sübut yoxdur", "az": "Məlumat azdır", "bazis": "Bazis" };
const PROVIDER_AZ = { goldapi: "gold-api.com", capital: "Capital.com (axın)", twelvedata: "Twelve Data", demo: "DEMO" };
let sym = "XAU", tf = "1m", mode = "live", lastState = null, lastFc = null;
// Chart tools (display only; the Judge tests the same ideas as forecast methods).
let ta = { ema: true, bb: false, fib: false, piv: false, sr: true, round: false, sub: "rsi", show: 120 };
try { sym = localStorage.getItem("tst_sym") || sym; tf = localStorage.getItem("tst_tf") || tf;
  ta = { ...ta, ...JSON.parse(localStorage.getItem("tst_ta") || "{}") }; } catch (e) {}
const TA_TOGGLES = [["ema", "EMA 20/50/200"], ["bb", "Bollinger"], ["fib", "Fibonacci"], ["piv", "Pivot"],
  ["sr", "Dəstək / müqavimət"], ["round", "Dəyirmi səviyyələr"]];
function renderTa() {
  $("ta").innerHTML = TA_TOGGLES.map(([k, n]) => `<button class="chip ${ta[k] ? "on" : ""}" data-k="${k}">${n}</button>`).join("") +
    `<span class="seg">${[["none", "Alt panel yox"], ["rsi", "RSI"], ["macd", "MACD"]].map(([k, n]) =>
      `<button data-sub="${k}" class="${ta.sub === k ? "on" : ""}">${n}</button>`).join("")}</span>` +
    `<span class="seg">${[60, 120, 240].map((k) => `<button data-show="${k}" class="${ta.show === k ? "on" : ""}">${k} şam</button>`).join("")}</span>`;
  const set = () => { try { localStorage.setItem("tst_ta", JSON.stringify(ta)); } catch (e) {} renderTa(); loadChart().catch(() => {}); };
  document.querySelectorAll("#ta [data-k]").forEach((b) => b.onclick = () => { ta[b.dataset.k] = !ta[b.dataset.k]; set(); });
  document.querySelectorAll("#ta [data-sub]").forEach((b) => b.onclick = () => { ta.sub = b.dataset.sub; set(); });
  document.querySelectorAll("#ta [data-show]").forEach((b) => b.onclick = () => { ta.show = +b.dataset.show; set(); });
}

async function api(path) {
  const r = await fetch(path, { credentials: "same-origin" });
  if (r.status === 401) { location.href = "/login"; throw new Error("login"); }
  return r.json();
}
const fmt = (x) => x == null ? "—" : (x >= 100 ? x.toFixed(2) : x.toFixed(3));
// The tile shows the price exactly as the source sent it (no rounding), at least two decimals.
const exact = (x) => { if (x == null) return "—"; const t = String(x); const d = (t.split(".")[1] || "").length;
  return d >= 2 ? t : x.toFixed(2); };
const pct = (x, d = 1) => x == null ? "—" : (x * 100).toFixed(d) + " %";
const hhmm = (ts) => ts ? new Date(ts * 1000).toLocaleTimeString("az", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—";
const when = (ts, tf) => !ts ? "—" : (tf === "1d" || tf === "1w")
  ? new Date(ts * 1000).toLocaleString("az", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : hhmm(ts);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function renderTiles(st) {
  $("tiles").innerHTML = st.metals.map((m) => {
    const ch = m.price != null && m.day_open ? (m.price / m.day_open - 1) : null;
    const cls = ch == null ? "mut" : ch >= 0 ? "up" : "down";
    return `<button class="tile ${m.symbol === sym ? "sel" : ""}" data-s="${m.symbol}">
      <div class="row"><span class="nm">${esc(m.name)}</span><span class="pill ${m.status}">${STATUS_AZ[m.status] || m.status}</span></div>
      <div class="row"><span class="px">${exact(m.price)}</span><span class="sym">${m.symbol}/USD · unsiya</span></div>
      <div class="row"><span class="ch ${cls}">${ch == null ? "—" : (ch >= 0 ? "+" : "") + (ch * 100).toFixed(2) + " % gün"}</span></div>
      <div class="src">Mənbə: <b>${esc(PROVIDER_AZ[m.source] || m.source || "—")}</b></div>
      <div class="src">${m.source_ts ? (m.ts_missing ? "Mənbə vaxt göstərmədi · alındı " + hhmm(m.recv_ts)
        : "Mənbənin qiymət vaxtı " + hhmm(m.source_ts) + " · alındı " + hhmm(m.recv_ts)) : esc(m.error || "qiymət gözlənilir")}</div></button>`;
  }).join("");
  document.querySelectorAll(".tile").forEach((b) => b.onclick = () => { sym = b.dataset.s; save(); refreshAll(); });
  const worst = st.metals.some((m) => m.status === "OFFLINE") ? "OFFLINE" : st.metals.every((m) => m.status === "DEMO") ? "DEMO"
    : st.metals.some((m) => m.status === "DELAYED") ? "DELAYED" : "LIVE";
  $("feed").className = "pill " + worst;
  $("feed").textContent = st.provider === "demo" ? "DEMO məlumat (real deyil)" : (PROVIDER_AZ[st.provider] || st.provider || "—") + " · " + (STATUS_AZ[worst] || worst);
  const ev = st.event_mode;
  $("evbanner").hidden = !ev;
  if (ev) $("evbanner").textContent = `Hadisə rejimi: «${ev.title}» ${until(ev.ts)}. Bu vaxt qiymət sıçrayışlı olur, qısa proqnozlara ehtiyatla baxın.`;
  $("mkt").textContent = st.market_open ? "Bazar açıqdır" : "Bazar bağlıdır (həftə sonu): yeni şam və proqnoz yoxdur";
}

function renderTfs() {
  $("tfs").innerHTML = TFS.map((t) => `<button data-t="${t}" class="${t === tf ? "on" : ""}">${TF_NAMES[t]}</button>`).join("");
  document.querySelectorAll("#tfs button").forEach((b) => b.onclick = () => { tf = b.dataset.t; save(); renderTfs(); loadChart(); });
}

function overlayFor(fc) {
  if (!fc) return null;
  const card = fc.cards.find((c) => c.horizon === tf);
  if (!card || !card.methods.length) return null;
  const m = card.methods.find((x) => x.method === (card.verdict.method || "rw")) || card.methods[0];
  return { ...m, name: card.name };
}

async function loadChart() {
  // Extra candles before the visible ones, so EMA 200 and RSI start correctly.
  const d = await api(`/api/candles?symbol=${sym}&tf=${tf}&limit=${Math.min(1000, ta.show + 220)}`);
  let day = null;
  if (ta.piv) { const dd = await api(`/api/candles?symbol=${sym}&tf=1d&limit=2`); day = dd.candles.length > 1 ? dd.candles[dd.candles.length - 2] : null; }
  const ov = overlayFor(lastFc);
  const name = (lastState?.metals.find((m) => m.symbol === sym) || {}).name || sym;
  $("ctitle").textContent = `${name} · ${TF_NAMES[tf]} şamlar`;
  $("ovnote").textContent = ov ? `Aralıq: ${ov.name} proqnozu` : "Bu zaman çərçivəsi üçün növbəti şam aralığı yoxdur (1 dəq, 1 saat, 1 gün, 1 həftə seçin)";
  drawChart($("cv"), $("tip"), d.candles, ov, tf, { ...ta, day });
  renderTaSummary(d.candles);
}

// The chart tools in words, and what the Judge says about the same idea as a forecast method on this horizon.
function judgeSays(method) {
  const card = lastFc && lastFc.cards.find((c) => c.horizon === tf);
  if (!card) return "";
  const live = card.stats_live.find((r) => r.method === method), hist = card.stats_history.find((r) => r.method === method);
  const r = live && live.nh >= live.min_n ? live : hist;
  if (!r) return "";
  const hr = r.hit_rate == null ? "—" : (r.hit_rate * 100).toFixed(0) + " %";
  return ` · Hakim: ${VERDICT_AZ[r.status]} (${hr}, ${r.nh} yoxlama)`;
}
function renderTaSummary(all) {
  if (all.length < 30) { $("tasum").innerHTML = ""; return; }
  const c = all.map((x) => x.c), last = c[c.length - 1];
  const e50 = TA.ema(c, 50).pop(), e200 = TA.ema(c, 200).pop(), r = TA.rsi(c).pop(), m = TA.macd(c), a = TA.atr(all);
  const mh = m.hist[m.hist.length - 1], mh0 = m.hist[m.hist.length - 2];
  const lv = TA.levels(all.slice(-Math.max(ta.show, 120)));
  const sup = lv.filter((l) => l.v < last).pop(), res = lv.find((l) => l.v > last);
  const f = TA.fib(all.slice(-ta.show));
  const nf = f ? f.lv.reduce((b, l) => Math.abs(l.v - last) < Math.abs(b.v - last) ? l : b) : null;
  const trend = e200 == null ? (e50 == null ? "—" : last > e50 ? "yuxarı (EMA 50 üstü)" : "aşağı (EMA 50 altı)")
    : last > e50 && e50 > e200 ? "yuxarı (qiymət > EMA 50 > EMA 200)" : last < e50 && e50 < e200 ? "aşağı (qiymət < EMA 50 < EMA 200)" : "qarışıq";
  const row = (k, v, cls = "") => `<div><span>${k}</span><span class="v ${cls}">${v}</span></div>`;
  $("tasum").innerHTML =
    row("Trend", trend, trend.startsWith("yuxarı") ? "up" : trend.startsWith("aşağı") ? "down" : "") +
    row("RSI 14", r == null ? "—" : r.toFixed(0) + (r > 70 ? " · çox alınıb" : r < 30 ? " · çox satılıb" : " · neytral"), r > 70 ? "down" : r < 30 ? "up" : "") +
    row("MACD", mh == null ? "—" : (mh >= 0 ? "müsbət" : "mənfi") + (mh0 != null && Math.sign(mh) !== Math.sign(mh0) ? " · yeni kəsişmə" : ""), mh >= 0 ? "up" : "down") +
    row("ATR 14 (orta şam)", a == null ? "—" : fmt(a) + " · " + (a / last * 100).toFixed(2) + " %") +
    row("Yaxın dəstək", sup ? fmt(sup.v) : "—", "up") + row("Yaxın müqavimət", res ? fmt(res.v) : "—", "down") +
    row("Yaxın Fibonacci", nf ? (nf.f * 100).toFixed(1) + " % · " + fmt(nf.v) : "—") +
    `<p class="note">Bu xətlər yalnız göstəricidir. Eyni fikirlər proqnoz üsulu kimi Hakimdə yoxlanır${judgeSays("trend") ? ":" : "."}
      Trend${judgeSays("trend")}; RSI${judgeSays("rsi")}; Fibonacci${judgeSays("fib")}; Sıçrayış${judgeSays("breakout")}.</p>`;
}

function cardHtml(c, names) {
  const v = c.verdict;
  const off = c.methods.find((m) => m.method === v.method) || c.methods.find((m) => m.method === "rw");
  let head;
  if (!c.methods.length) {
    head = `<p class="note">Proqnoz hələ yoxdur: ${c.candles_have} bitmiş şam var, ${c.candles_need} lazımdır.
      ${c.tf === "1d" || c.tf === "1w" ? "Bu üfüq üçün tarixçə lazımdır (admin: Capital.com və ya Twelve Data açarı)." : ""}</p>`;
  } else if (v.status === "sübut") {
    const p = off.p_up, dir = p > 0.5 ? "yuxarı" : "aşağı";
    head = `<div class="big ${p > 0.5 ? "up" : "down"}">${dir} · ${(Math.max(p, 1 - p) * 100).toFixed(0)} %</div>
      <div class="note">${esc(names[v.method])}: ${esc(off.basis)}</div>`;
  } else {
    head = `<div class="big mut">İstiqamət göstərilmir</div>
      <div class="note">Heç bir üsul hələ bazis qaydalarını sübutla üstələməyib. Aşağıda yalnız gözlənilən aralıq var.</div>`;
  }
  const rng = off ? `<div class="kv"><span>İndiki qiymət</span><span class="num">${fmt(off.price0)}</span>
      <span>50 % aralıq</span><span class="num">${fmt(off.lo50)} – ${fmt(off.hi50)}</span>
      <span>80 % aralıq</span><span class="num">${fmt(off.lo80)} – ${fmt(off.hi80)}</span>
      <span>Yoxlanma vaxtı</span><span class="num">${when(off.target_t, c.tf)}</span></div>` : "";
  const rows = c.methods.map((m) => `<tr><td>${esc(names[m.method])}</td><td class="n">${(m.p_up * 100).toFixed(1)} %</td><td>${esc(m.basis)}</td></tr>`).join("");
  return `<div class="card"><div class="hd"><b>${c.name}</b>
      <span class="pill ${v.status}">${VERDICT_AZ[v.status]}${v.by === "history" ? " · tarixçə" : ""}</span></div>
    ${head}${rng}
    ${rows ? `<details class="meth"><summary>Bütün üsullar</summary><table><tr><th>Üsul</th><th>Yuxarı ehtimalı</th><th>Əsas</th></tr>${rows}</table></details>` : ""}
  </div>`;
}

function renderCards(fc) {
  $("cards").innerHTML = fc.cards.map((c) => cardHtml(c, fc.method_names)).join("");
  $("fcupd").textContent = "yeniləndi " + hhmm(Date.now() / 1000);
}

let jh = "1m";
try { jh = localStorage.getItem("tst_jh") || jh; } catch (e) {}
const MCOL = { momentum: "#4ea1ff", reversal: "#c77dff", trend: "#3fb27f", breakout: "#ff9f43", rsi: "#e0605a",
  fib: "#d4a73c", macro: "#2ec4b6" };
function renderJudge(fc) {
  const key = mode === "live" ? "stats_live" : "stats_history";
  const methods = Object.keys(fc.method_names).filter((m) => m !== "rw");
  // summary matrix: rows = horizons, cells = hit rate coloured by status
  let mx = `<table><tr><th>Üfüq</th>${methods.map((m) => `<th>${esc(fc.method_names[m])}</th>`).join("")}<th>50 % aralıq</th><th>80 % aralıq</th></tr>`;
  for (const c of fc.cards) {
    const by = Object.fromEntries(c[key].map((r) => [r.method, r]));
    const rw = by.rw || {};
    mx += `<tr><td>${c.name}</td>` + methods.map((m) => {
      const r = by[m];
      if (!r) return `<td class="cell mut">·</td>`;
      if (m === "up") return `<td class="cell bazis">${r.n ? pct(r.hit_rate, 0) : "—"}</td>`;
      const cnt = r.nh;
      return `<td class="cell ${r.status}" title="${cnt} yoxlama, keçməli hədd ${pct(r.bar, 0)}">${cnt ? pct(r.hit_rate, 0) : "—"}</td>`;
    }).join("") + `<td class="cell">${rw.n ? pct(rw.cover50, 0) : "—"}</td><td class="cell">${rw.n ? pct(rw.cover80, 0) : "—"}</td></tr>`;
  }
  $("jmatrix").innerHTML = mx + `</table><p class="note">Xanada: üsul istiqamət göstərəndə neçə faiz düz çıxıb. Yaşıl = sübut olunub,
    qırmızı = kifayət qədər yoxlama var, amma sübut yoxdur, sarı = hələ az yoxlama. Bazis «Həmişə yuxarı» sütunu: qiymət neçə faiz hallarda qalxıb.
    Aralıq sütunları: qiymət 50 % və 80 % aralığa neçə faiz düşüb (düzgün aralıq ≈ 50 % və ≈ 80 %).</p>`;

  $("jh").innerHTML = fc.cards.map((c) => `<button data-h="${c.horizon}" class="${c.horizon === jh ? "on" : ""}">${c.name}</button>`).join("");
  document.querySelectorAll("#jh button").forEach((b) => b.onclick = () => { jh = b.dataset.h; try { localStorage.setItem("tst_jh", jh); } catch (e) {} renderJudge(fc); });
  const card = fc.cards.find((c) => c.horizon === jh) || fc.cards[0];
  let html = `<table><tr><th>Üsul</th><th>Yoxlama</th><th>Düz çıxıb</th><th>Keçməli hədd</th><th>p</th>
    <th>Brier bal</th><th>50 % aralıq tutdu</th><th>80 % aralıq tutdu</th><th>Status</th></tr>`;
  for (const r of card[key]) {
    const cnt = r.method === "rw" || r.method === "up" ? r.n : r.nh;
    const st = r.status === "az" ? `az (${cnt}/${r.min_n})` : VERDICT_AZ[r.status];
    html += `<tr><td>${esc(fc.method_names[r.method])}</td><td class="n">${cnt}</td>
      <td class="n">${r.method === "rw" ? "—" : pct(r.hit_rate)}</td><td class="n">${r.method === "rw" ? "—" : pct(r.bar)}</td>
      <td class="n">${r.p == null || r.method === "rw" ? "—" : r.p.toFixed(3)}</td>
      <td class="n">${r.bss == null ? "—" : (r.bss * 100).toFixed(1)}</td>
      <td class="n">${pct(r.cover50, 0)}</td><td class="n">${pct(r.cover80, 0)}</td>
      <td><span class="pill ${r.status}">${st}</span></td></tr>`;
  }
  $("judge").innerHTML = html + `</table><p class='note'>«Yoxlama»: üsulun istiqamət göstərdiyi proqnozların sayı (RSI, Fibonacci, sıçrayış
    yalnız siqnal olanda istiqamət göstərir). 3 gün, 10 gün və 1 ay proqnozları hər gün verilir və üst-üstə düşür: p bunu nəzərə alır
    (say üfüqün gün sayına bölünür). Brier bal: 0-dan yuxarı = sikkə atmaqdan yaxşı.</p>`;
  loadJudgeCharts(card).catch(() => {});
}
async function loadJudgeCharts(card) {
  const d = await api(`/api/judge/series?symbol=${sym}&horizon=${card.horizon}&mode=${mode}`);
  $("jwin").textContent = d.window;
  const names = lastFc.method_names, bar = (card[mode === "live" ? "stats_live" : "stats_history"].find((r) => r.method === "momentum") || {}).bar || 0.5;
  const ser = Object.entries(d.methods).map(([m, pts]) => ({ name: names[m], color: MCOL[m] || "#888", pts }));
  drawLines($("jc1"), ser, [{ v: bar, label: "keçməli hədd " + (bar * 100).toFixed(0) + " %", color: getComputedStyle(document.documentElement).getPropertyValue("--muted") }], 0.3, 0.8);
  $("jl1").innerHTML = ser.map((s) => `<span><i style="background:${s.color}"></i>${esc(s.name)}</span>`).join("");
  const gold = getComputedStyle(document.documentElement).getPropertyValue("--gold"), info = "#4ea1ff";
  drawLines($("jc2"), [{ name: "50 %", color: info, pts: d.cover["50"] }, { name: "80 %", color: gold, pts: d.cover["80"] }],
    [{ v: 0.5, color: info }, { v: 0.8, color: gold }], 0.2, 1.0);
  $("jl2").innerHTML = `<span><i style="background:${info}"></i>50 % aralığa düşən</span><span><i style="background:${gold}"></i>80 % aralığa düşən</span>`;
}

async function loadJournal() {
  const d = await api(`/api/journal?symbol=${sym}`);
  const names = lastFc ? lastFc.method_names : {};
  const hn = Object.fromEntries((lastFc ? lastFc.cards : []).map((c) => [c.horizon, c.name]));
  if (!d.rows.length) { $("journal").innerHTML = "<p class='note'>Hələ yoxlanmış proqnoz yoxdur. 1 dəqiqəlik proqnozlar bazar açıq olanda hər dəqiqə yoxlanır.</p>"; return; }
  $("journal").innerHTML = `<table><tr><th>Vaxt</th><th>Üfüq</th><th>Üsul</th><th>Başlanğıc</th><th>Nəticə</th><th>Yuxarı ehtimalı</th><th>İstiqamət</th><th>80 % aralıq</th></tr>` +
    d.rows.map((r) => `<tr><td>${hhmm(r.target_t)}</td><td>${hn[r.horizon]}</td><td>${esc(names[r.method] || r.method)}</td>
      <td class="n">${fmt(r.price0)}</td><td class="n">${fmt(r.price1)}</td><td class="n">${(r.p_up * 100).toFixed(1)} %</td>
      <td>${r.hit == null ? "<span class='mut'>—</span>" : r.hit ? "<span class='up'>düz</span>" : "<span class='down'>səhv</span>"}</td>
      <td>${r.in80 ? "<span class='up'>tutdu</span>" : "<span class='down'>tutmadı</span>"}</td></tr>`).join("") + "</table>";
}

let nfilter = "metal";
const STR_AZ = ["təsirsiz", "zəif", "orta", "güclü"];
function aiTag(a) {
  if (!a) return "";
  const arrow = a.direction === "up" ? "<span class='up'>↑</span>" : a.direction === "down" ? "<span class='down'>↓</span>" : "→";
  return ` · <b>Oxuyucu:</b> ${esc(a.ai_metals || "—")} ${arrow} ${STR_AZ[a.strength] || ""}${a.event ? " (" + esc(a.event) + ")" : ""}`;
}
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
  if (!x) { $("scout").innerHTML = `<p class="note">${esc((d.scout_state && d.scout_state.message) || "Kəşfiyyatçı (Grok) hələ axtarmayıb: bazar açıq olanda 2 saatda bir, mühüm ABŞ rəqəmi ətrafında 20 dəqiqədə bir axtarır. xAI açarı lazımdır.")}</p>`; $("scmeta").textContent = ""; return; }
  $("scmeta").textContent = `${x.brain} · ${new Date(x.ts * 1000).toLocaleString("az")}`;
  const items = x.items.filter((i) => nfilter === "all" || !i.metals.length || i.metals.includes(sym));
  $("scout").innerHTML = (x.mood ? `<p>${esc(x.mood)}</p>` : "") + (items.length ? items.map((i) => `<div class="nitem">
      ${i.url ? `<a href="${esc(i.url)}" target="_blank" rel="noopener noreferrer">${esc(i.title)}</a>` : `<span>${esc(i.title)}</span>`}
      <span class="m">${esc(i.source)} · ${esc(i.metals.join(", ") || "ümumi")} ${i.direction === "up" ? "<span class='up'>↑</span>" : i.direction === "down" ? "<span class='down'>↓</span>" : "→"} ${STR_AZ[i.strength] || ""}${i.why ? " · " + esc(i.why) : ""}</span></div>`).join("")
    : "<p class='note'>Seçilmiş metal üçün tapılan yoxdur.</p>") +
    `<p class="note">Grok X və vebdə axtarır. Mənbəyə klikləyib yoxlayın: süni intellekt səhv edə bilər. Rəqəm olan cümlələr avtomatik silinir.</p>` +
    (d.scout_state && d.scout_state.message && d.scout_state.ts > x.ts ? `<p class="note">Son cəhd: ${esc(d.scout_state.message)}</p>` : "");
}
async function loadBrains() {
  const d = await api("/api/brains");
  renderReaderScore(d.reader_score);
  renderScout(d);
  const x = d.strategist;
  if (!x) {
    $("strat").innerHTML = `<p class="note">${esc((d.strategist_state && d.strategist_state.message) || "Strateq hələ izah yazmayıb (saatda bir yazır).")}</p>`;
    $("stmeta").textContent = "";
    return;
  }
  $("stmeta").textContent = `${esc(x.brain)} · ${new Date(x.ts * 1000).toLocaleString("az")}`;
  const m = x.metals.find((v) => v.symbol === sym);
  $("strat").innerHTML = `<p>${esc(x.summary)}</p>${m && m.text ? `<p><b>${esc(sym)}:</b> ${esc(m.text)}</p>` : ""}` +
    (x.watch.length ? `<p class="note">Diqqət: ${x.watch.map(esc).join(" · ")}</p>` : "") +
    `<p class="note">Bu, süni intellektin izahıdır, alış-satış məsləhəti deyil. Faktlarda olmayan rəqəmli cümlələr avtomatik silinir.</p>`;
}
// The page reloads itself when the server runs a new version (no manual refresh after an update).
let seenVersion = null;
async function checkVersion() {
  try {
    const v = (await (await fetch("/version", { cache: "no-store" })).json()).commit;
    if (seenVersion && v && v !== seenVersion) location.reload();
    seenVersion = seenVersion || v;
  } catch (e) {}
}
const ago = (ts) => { const m = Math.round((Date.now() / 1000 - ts) / 60);
  return m < 60 ? m + " dəq əvvəl" : m < 1440 ? Math.round(m / 60) + " saat əvvəl" : Math.round(m / 1440) + " gün əvvəl"; };
const until = (ts) => { const m = Math.round((ts - Date.now() / 1000) / 60);
  if (m < 0) return "çıxıb";
  return m < 60 ? m + " dəq sonra" : m < 1440 ? Math.floor(m / 60) + " saat " + (m % 60) + " dəq sonra" : Math.round(m / 1440) + " gün sonra"; };
const SER = { DFII10: 2, DGS10: 2, T10YIE: 2, DTWEXBGS: 2, VIXCLS: 1, SP500: 0 };
const MNAME = { XAU: "Qızıl", XAG: "Gümüş", XPT: "Platin", XPD: "Palladium" };
// Fundamentals in words: each factor, which way it points for gold, and why. Display only: the macro method in the
// Judge is the test of whether this view actually forecasts anything.
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
  const c = (d.cot || []).find((x) => x.symbol === sym);
  if (c && c.date) add(c.rank > 85 ? -1 : c.rank < 15 ? 1 : 0, `Böyük fondlar (${MNAME[sym]}): xalis ${Math.round(c.net).toLocaleString("az")} müqavilə, 3 ilin ${c.rank == null ? "—" : c.rank.toFixed(0) + " %"}-i`,
    c.rank > 85 ? "Fondlar 3 ilin ən yüklü mövqeyinə yaxındır: alan az qalıb, geri çəkilmə riski artır."
      : c.rank < 15 ? "Fondlar 3 ilin ən zəif mövqeyinə yaxındır: satan az qalıb, dönüş potensialı var." : "Fondların mövqeyi ifrat deyil.");
  $("fsig").innerHTML = sig.length ? sig.join("") + `<p class="note">Bunlar izahdır. Makro (real faiz + dollar) üsulu Hakimdə yoxlanır${judgeSays("macro")
    .replace(" · ", ": ")}. COT məlumatı çərşənbə axşamının vəziyyətidir, cümə günü dərc olunur.</p>`
    : `<p class="note">Fundamental məlumat hələ yoxdur (admin: FRED açarı).</p>`;
  const h = (d.health || {}).cot || {};
  $("cot").innerHTML = (d.cot || []).some((x) => x.date) ? `<table><tr><th>Metal</th><th>Hesabat</th><th>Fondların xalis mövqeyi</th><th>Açıq mövqelərin %-i</th><th>Həftəlik dəyişmə</th><th>3 illik diapazonda</th></tr>` +
    d.cot.map((x) => x.date ? `<tr><td>${MNAME[x.symbol]}</td><td>${x.date}</td><td class="n">${Math.round(x.net).toLocaleString("az")}</td>
      <td class="n">${x.net_pct_oi == null ? "—" : x.net_pct_oi.toFixed(1) + " %"}</td>
      <td class="n ${x.change > 0 ? "up" : x.change < 0 ? "down" : ""}">${x.change == null ? "—" : (x.change > 0 ? "+" : "") + Math.round(x.change).toLocaleString("az")}</td>
      <td class="n">${x.rank == null ? "—" : x.rank.toFixed(0) + " %"}</td></tr>` : "").join("") + "</table>" +
    `<p class="note">CFTC COT: «managed money» (hedc fondları, CTA) fyuçers mövqeyi. 100 % = son 3 ilin ən böyük alış mövqeyi.</p>`
    : `<p class="note">CFTC COT: ${esc(h.message || "hələ yüklənməyib")}</p>`;
}

async function loadFeeds() {
  const d = await api(`/api/feeds${nfilter === "metal" ? "?metal=" + sym : ""}`);
  const h = d.health || {};
  try { renderFund(d); } catch (e) {}
  $("macro").innerHTML = d.macro.map((m) => m.value == null
    ? `<div class="mrow"><span>${esc(m.name)}</span><span class="mut">—</span><span></span></div>`
    : `<div class="mrow"><span>${esc(m.name)}<br><span class="note">${esc(m.date)}</span></span>
       <span class="v">${m.value.toFixed(SER[m.series] || 2)}</span>
       <span class="v ${m.change_week > 0 ? "up" : m.change_week < 0 ? "down" : "mut"}">${m.change_week >= 0 ? "+" : ""}${m.change_week.toFixed(2)}</span></div>`).join("") +
    `<p class="note">${h.fred && h.fred.ok ? "Son: həftəlik dəyişmə sağda. Real faiz yüksələndə qızıl adətən sıxılır, amma 2022-dən bu əlaqə zəifləyib."
      : "FRED: " + esc((h.fred && h.fred.message) || "hələ yüklənməyib")}</p>`;
  $("events").innerHTML = d.events.length ? `<table><tr><th>Vaxt</th><th>Hadisə</th><th>Gözlənti</th><th>Əvvəlki</th><th>Fakt</th></tr>` +
    d.events.map((e) => `<tr><td>${new Date(e.ts * 1000).toLocaleString("az", { weekday: "short", hour: "2-digit", minute: "2-digit" })}<br>
      <span class="note">${until(e.ts)}</span></td><td><span class="${e.impact === "High" ? "hi" : "me"}">●</span> ${esc(e.title)}</td>
      <td class="n">${esc(e.forecast || "—")}</td><td class="n">${esc(e.previous || "—")}</td><td class="n">${esc(e.actual || "—")}</td></tr>`).join("") + "</table>"
    : `<p class="note">${h.forexfactory && h.forexfactory.ok === false ? "Təqvim: " + esc(h.forexfactory.message) : "Yaxın 7 gündə mühüm ABŞ hadisəsi yoxdur və ya təqvim hələ yüklənməyib."}</p>`;
  $("news").innerHTML = d.news.length ? d.news.slice(0, 20).map((n) => `<div class="nitem">
      ${n.url ? `<a href="${esc(n.url)}" target="_blank" rel="noopener noreferrer">${esc(n.title)}</a>` : `<span>${esc(n.title)}</span>`}
      <span class="m">${esc(n.source)} · ${ago(n.ts)}${n.metals ? " · " + esc(n.metals) : ""}${aiTag(n.ai)}</span></div>`).join("")
    : `<p class="note">${h.rss && h.rss.ok === false ? "Xəbər: " + esc(h.rss.message) : "Hələ başlıq yoxdur."}</p>`;
}
document.querySelectorAll("#nfilter button").forEach((b) => b.onclick = () => {
  nfilter = b.dataset.f; document.querySelectorAll("#nfilter button").forEach((x) => x.classList.toggle("on", x === b));
  loadFeeds().catch(() => {});
});

function save() { try { localStorage.setItem("tst_sym", sym); localStorage.setItem("tst_tf", tf); } catch (e) {} }

async function refreshState() { lastState = await api("/api/state"); renderTiles(lastState); }
let modeTouched = false;
async function refreshFc() {
  lastFc = await api(`/api/forecasts?symbol=${sym}`);
  // Until live forecasts have been scored, open the Judge on the history tab (live would be all zeros).
  if (!modeTouched) {
    const liveN = lastFc.cards.reduce((a, c) => a + c.stats_live.reduce((b, r) => b + r.n, 0), 0);
    mode = liveN ? "live" : "history";
    document.querySelectorAll("#modes button").forEach((x) => x.classList.toggle("on", x.dataset.m === mode));
  }
  renderCards(lastFc); renderJudge(lastFc);
}
async function refreshAll() { await refreshState(); await refreshFc(); await loadChart(); await loadJournal(); await loadFeeds(); await loadBrains(); }

document.querySelectorAll("#modes button").forEach((b) => b.onclick = () => {
  mode = b.dataset.m; modeTouched = true; document.querySelectorAll("#modes button").forEach((x) => x.classList.toggle("on", x === b));
  if (lastFc) renderJudge(lastFc);
});
setInterval(() => {
  const d = new Date();
  $("clock").textContent = "UTC " + d.toISOString().slice(11, 19) + " · Bakı " +
    d.toLocaleTimeString("az", { timeZone: "Asia/Baku", hour: "2-digit", minute: "2-digit" });
}, 1000);
renderTfs();
renderTa();
refreshAll();
// A guest has no admin page: the link is hidden for them.
api("/api/me").then((m) => { if (m.role === "guest") document.querySelectorAll('a[href="/admin"],a[href="/status"]').forEach((a) => a.hidden = true); }).catch(() => {});
setInterval(() => refreshState().catch(() => {}), 5000);
setInterval(() => loadChart().catch(() => {}), 10000);
setInterval(() => { refreshFc().catch(() => {}); loadJournal().catch(() => {}); }, 20000);
setInterval(() => { loadFeeds().catch(() => {}); loadBrains().catch(() => {}); }, 60000);
checkVersion(); setInterval(checkVersion, 60000);
