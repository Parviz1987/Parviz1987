/* TST Trade panel: prices, the chart and its tools, forecast cards and the strategist's note. The Judge's tables and the
   journal are on the results page, news, fundamentals and the calendar on their block pages (static/sections.js). */
const $ = (id) => document.getElementById(id);
const TFS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"];
const TF_NAMES = { "1m": "1 dəq", "5m": "5 dəq", "15m": "15 dəq", "30m": "30 dəq", "1h": "1 saat", "4h": "4 saat", "1d": "1 gün", "1w": "1 həftə" };
const STATUS_AZ = { LIVE: "Canlı", DELAYED: "Gecikir", OFFLINE: "Əlaqə yoxdur", DEMO: "DEMO", QUIET: "Sakit" };
const VERDICT_AZ = { "sübut": "Sübut olunub", "yox": "Sübut yoxdur", "az": "Məlumat azdır", "bazis": "Bazis",
  "xərc": "Spreaddən kiçik" };
const PROVIDER_AZ = { goldapi: "gold-api.com", capital: "Capital.com (axın)", twelvedata: "Twelve Data", demo: "DEMO" };
let sym = "XAU", tf = "1m", lastState = null, lastFc = null;
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
// Block 15: what the full cost is made of (spread, slippage, overnight financing for the nights held)
const costTip = (c) => !c ? "" : `Tam xərc ${(c.total * 100).toFixed(3)} %: spred ${(c.spread * 100).toFixed(3)} % + sürüşmə ${(c.slip * 100).toFixed(3)} %` +
  (c.swap ? ` + gecəlik haqq ${(c.swap * 100).toFixed(3)} %${c.swap_source === "təxmini" ? " (təxmini, broker hələ deməyib)" : " (brokerin öz rəqəmi)"}` : "");
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
  $("ovnote").textContent = ov ? `Aralıq: ${ov.name} proqnozu` : "Bu zaman çərçivəsi üçün proqnoz yoxdur (15 dəq, 30 dəq, 1 saat, 4 saat, 1 gün, 1 həftə seçin)";
  let marks = [];
  try { marks = (await api(`/api/signals?symbol=${sym}&hours=${tf === "1d" || tf === "1w" ? 336 : 48}`)).signals; } catch (e) { /* no marks */ }
  drawChart($("cv"), $("tip"), d.candles, ov, tf, { ...ta, day, marks });
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
    `<p class="note">Bu xətlər yalnız göstəricidir. Texniki analiz bir blokdadır (Bilik kitabı: 12 növ, hər qayda Hakimdə ayrıca);
      proqnoza bir səs kimi gedir — Qaydalar${judgeSays("qaydalar")}; Qrafik analitiki${judgeSays("chartist")}.</p>`;
}

// One forecast card, compact (owner 2026-11-26: no long repeated sentences): the horizon, the Judge's status, the
// direction only when proven, the two ranges and when it is checked. The rule «a direction only with the Judge's
// proof» is said once above the cards; every method's number stays under «Bütün üsullar».
const VSHORT = { "sübut": "✓ sübut", "yox": "sübut yox", "az": "az məlumat", "bazis": "bazis", "xərc": "xərcdən kiçik" };
function cardHtml(c, names) {
  const v = c.verdict;
  const off = c.methods.find((m) => m.method === v.method) || c.methods.find((m) => m.method === "rw");
  let head;
  if (!c.methods.length) {
    head = `<div class="dir mut">hələ yoxdur</div><div class="note">${c.candles_have} / ${c.candles_need} şam${c.tf === "1d" || c.tf === "1w" ? " · tarixçə lazımdır" : ""}</div>`;
  } else if (v.status === "sübut") {
    const p = off.p_up, dir = p > 0.5 ? "▲ yuxarı" : p < 0.5 ? "▼ aşağı" : "fikir yox";
    head = `<div class="dir ${p > 0.5 ? "up" : p < 0.5 ? "down" : "mut"}">${dir}${p === 0.5 ? "" : " · " + (Math.max(p, 1 - p) * 100).toFixed(0) + " %"}</div>
      <div class="note">${esc(names[v.method])}: ${esc(off.basis)}</div>` +
      (v.condition ? `<div class="note"><b>Şərtli:</b> yalnız «${esc(GROUP_AZ[v.condition] || v.condition)}» şəraitində (${pct(v.cond_hit_rate, 0)}, ${v.cond_n} yoxlama).</div>` : "");
  } else {
    head = `<div class="dir mut">istiqamət yox</div>`;
  }
  const rng = off ? `<div class="kv"><span>50 %</span><span class="num">${fmt(off.lo50)} – ${fmt(off.hi50)}</span>
      <span>80 %</span><span class="num">${fmt(off.lo80)} – ${fmt(off.hi80)}</span>
      <span>yoxlanır</span><span class="num">${when(off.target_t, c.tf)}</span></div>` : "";
  const rows = c.methods.map((m) => `<tr><td>${esc(names[m.method])}</td><td class="n">${(m.p_up * 100).toFixed(1)} %</td><td>${esc(m.basis)}</td></tr>`).join("");
  return `<div class="card"><div class="hd"><b>${c.name}</b>
      <span class="pill ${v.status}" title="${VERDICT_AZ[v.status]}${v.by === "history" ? " (tarixçə üzrə)" : ""}">${VSHORT[v.status] || v.status}</span></div>
    ${head}${rng}
    ${rows ? `<details class="meth"><summary>Bütün üsullar</summary><table><tr><th>Üsul</th><th>Yuxarı ehtimalı</th><th>Əsas</th></tr>${rows}</table></details>` : ""}
  </div>`;
}

function renderCards(fc) {
  $("cards").innerHTML = fc.cards.map((c) => cardHtml(c, fc.method_names)).join("");
  $("fcupd").textContent = "yeniləndi " + hhmm(Date.now() / 1000);
}

// Session hours are fixed in UTC (22-07, 07-13, 13-22); shown in New York time for the owner (DST included).
const nyHour = (utcH) => { const d = new Date(); d.setUTCHours(utcH, 0, 0, 0);
  return d.toLocaleTimeString("az", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" }); };
const GROUP_AZ = { asia: `Asiya seansı (${nyHour(22)}–${nyHour(7)} NY)`, london: `London (${nyHour(7)}–${nyHour(13)} NY)`,
  ny: `Nyu-York (${nyHour(13)}–${nyHour(22)} NY)`, calm: "Sakit bazar", wild: "Dalğalı bazar" };
async function loadBrains() {
  const d = await api("/api/brains");
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
const ago = (ts) => { const m = Math.round((Date.now() / 1000 - ts) / 60);
  return m < 60 ? m + " dəq əvvəl" : m < 1440 ? Math.round(m / 60) + " saat əvvəl" : Math.round(m / 1440) + " gün əvvəl"; };
const until = (ts) => { const m = Math.round((ts - Date.now() / 1000) / 60);
  if (m < 0) return "çıxıb";
  return m < 60 ? m + " dəq sonra" : m < 1440 ? Math.floor(m / 60) + " saat " + (m % 60) + " dəq sonra" : Math.round(m / 1440) + " gün sonra"; };
function save() { try { localStorage.setItem("tst_sym", sym); localStorage.setItem("tst_tf", tf); } catch (e) {} }

async function refreshState() { lastState = await api("/api/state"); renderTiles(lastState); }
async function refreshFc() {
  lastFc = await api(`/api/forecasts?symbol=${sym}`);
  renderCards(lastFc);
}
async function refreshAll() { await refreshState(); await refreshFc(); await loadChart(); await loadBrains(); }
setInterval(() => {
  const d = new Date();
  // The owner lives in New York: New York time first (winter/summer time handled by the browser), UTC for the data.
  $("clock").textContent = "Nyu-York " + d.toLocaleTimeString("az", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", second: "2-digit" }) +
    " · UTC " + d.toISOString().slice(11, 16);
}, 1000);
renderTfs();
renderTa();
refreshAll();

setInterval(() => refreshState().catch(() => {}), 5000);
setInterval(() => loadChart().catch(() => {}), 10000);
setInterval(() => { refreshFc().catch(() => {}); }, 20000);
setInterval(() => { loadBrains().catch(() => {}); }, 60000);
// a new server version reloads the page: static/nav.js (the same for every page)
