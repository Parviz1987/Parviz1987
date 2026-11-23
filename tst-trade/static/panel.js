/* TST Trade panel: prices, candles, forecast cards, the Judge's table and the journal. */
const $ = (id) => document.getElementById(id);
const TFS = ["1m", "5m", "15m", "1h", "4h", "1d", "1w"];
const TF_NAMES = { "1m": "1 dəq", "5m": "5 dəq", "15m": "15 dəq", "1h": "1 saat", "4h": "4 saat", "1d": "1 gün", "1w": "1 həftə" };
const STATUS_AZ = { LIVE: "Canlı", DELAYED: "Gecikir", OFFLINE: "Əlaqə yoxdur", DEMO: "DEMO" };
const VERDICT_AZ = { "sübut": "Sübut olunub", "yox": "Sübut yoxdur", "az": "Məlumat azdır", "bazis": "Bazis" };
const PROVIDER_AZ = { goldapi: "gold-api.com", twelvedata: "Twelve Data", demo: "DEMO" };
let sym = "XAU", tf = "1m", mode = "live", lastState = null, lastFc = null;
try { sym = localStorage.getItem("tst_sym") || sym; tf = localStorage.getItem("tst_tf") || tf; } catch (e) {}

async function api(path) {
  const r = await fetch(path, { credentials: "same-origin" });
  if (r.status === 401) { location.href = "/login"; throw new Error("login"); }
  return r.json();
}
const fmt = (x) => x == null ? "—" : (x >= 100 ? x.toFixed(2) : x.toFixed(3));
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
      <div class="row"><span class="px">${fmt(m.price)}</span><span class="sym">${m.symbol}/USD</span></div>
      <div class="row"><span class="ch ${cls}">${ch == null ? "—" : (ch >= 0 ? "+" : "") + (ch * 100).toFixed(2) + " % gün"}</span>
      <span class="ts">${m.source_ts ? "yeniləndi " + hhmm(m.source_ts) : esc(m.error || "qiymət gözlənilir")}</span></div></button>`;
  }).join("");
  document.querySelectorAll(".tile").forEach((b) => b.onclick = () => { sym = b.dataset.s; save(); refreshAll(); });
  const worst = st.metals.some((m) => m.status === "OFFLINE") ? "OFFLINE" : st.metals.every((m) => m.status === "DEMO") ? "DEMO"
    : st.metals.some((m) => m.status === "DELAYED") ? "DELAYED" : "LIVE";
  $("feed").className = "pill " + worst;
  $("feed").textContent = st.provider === "demo" ? "DEMO məlumat (real deyil)" : (PROVIDER_AZ[st.provider] || st.provider || "—") + " · " + (STATUS_AZ[worst] || worst);
  $("mkt").textContent = st.market_open ? "Bazar açıqdır" : "Bazar bağlıdır (həftə sonu): yeni şam və proqnoz yoxdur";
}

function renderTfs() {
  $("tfs").innerHTML = TFS.map((t) => `<button data-t="${t}" class="${t === tf ? "on" : ""}">${TF_NAMES[t]}</button>`).join("");
  document.querySelectorAll("#tfs button").forEach((b) => b.onclick = () => { tf = b.dataset.t; save(); renderTfs(); loadChart(); });
}

function overlayFor(fc) {
  if (!fc) return null;
  const card = fc.cards.find((c) => c.tf === tf);
  if (!card || !card.methods.length) return null;
  const m = card.methods.find((x) => x.method === (card.verdict.method || "rw")) || card.methods[0];
  return { ...m, name: card.name };
}

async function loadChart() {
  const d = await api(`/api/candles?symbol=${sym}&tf=${tf}&limit=160`);
  const ov = overlayFor(lastFc);
  const name = (lastState?.metals.find((m) => m.symbol === sym) || {}).name || sym;
  $("ctitle").textContent = `${name} · ${TF_NAMES[tf]} şamlar`;
  $("ovnote").textContent = ov ? `Aralıq: ${ov.name} proqnozu` : "Bu zaman çərçivəsi üçün proqnoz aralığı yoxdur (1 dəq, 1 saat, 1 gün, 1 həftə seçin)";
  drawChart($("cv"), $("tip"), d.candles, ov, tf);
}

function cardHtml(c, names) {
  const v = c.verdict;
  const off = c.methods.find((m) => m.method === v.method) || c.methods.find((m) => m.method === "rw");
  let head;
  if (!c.methods.length) {
    head = `<p class="note">Proqnoz hələ yoxdur: ${c.candles_have} bitmiş şam var, ${c.candles_need} lazımdır.
      ${c.tf === "1d" || c.tf === "1w" ? "Bu üfüq üçün tarixçə lazımdır (admin: Twelve Data açarı)." : ""}</p>`;
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

function renderJudge(fc) {
  const key = mode === "live" ? "stats_live" : "stats_history";
  let html = `<table><tr><th>Üfüq</th><th>Üsul</th><th>Yoxlama</th><th>Düz çıxıb</th><th>Keçməli hədd</th><th>p</th>
    <th>Brier bal</th><th>50 % aralıq tutdu</th><th>80 % aralıq tutdu</th><th>Status</th></tr>`;
  for (const c of fc.cards) {
    for (const r of c[key]) {
      const st = r.status === "az" ? `az (${r.n}/${r.min_n})` : VERDICT_AZ[r.status];
      html += `<tr><td>${c.name}</td><td>${esc(fc.method_names[r.method])}</td><td class="n">${r.n}</td>
        <td class="n">${r.method === "rw" ? "—" : pct(r.hit_rate)}</td><td class="n">${r.method === "rw" ? "—" : pct(r.bar)}</td>
        <td class="n">${r.p == null || r.method === "rw" ? "—" : r.p.toFixed(3)}</td>
        <td class="n">${r.bss == null ? "—" : (r.bss * 100).toFixed(1)}</td>
        <td class="n">${pct(r.cover50, 0)}</td><td class="n">${pct(r.cover80, 0)}</td>
        <td><span class="pill ${r.status}">${st}</span></td></tr>`;
    }
  }
  $("judge").innerHTML = html + "</table><p class='note'>Brier bal: 0-dan yuxarı = sikkə atmaqdan yaxşı. 50 % və 80 % aralıq düzgün qurulubsa, uyğun olaraq təxminən 50 % və 80 % tutmalıdır.</p>";
}

async function loadJournal() {
  const d = await api(`/api/journal?symbol=${sym}`);
  const names = lastFc ? lastFc.method_names : {};
  const hn = { "1m": "1 dəq", "1h": "1 saat", "1d": "1 gün", "1w": "1 həftə" };
  if (!d.rows.length) { $("journal").innerHTML = "<p class='note'>Hələ yoxlanmış proqnoz yoxdur. 1 dəqiqəlik proqnozlar bazar açıq olanda hər dəqiqə yoxlanır.</p>"; return; }
  $("journal").innerHTML = `<table><tr><th>Vaxt</th><th>Üfüq</th><th>Üsul</th><th>Başlanğıc</th><th>Nəticə</th><th>Yuxarı ehtimalı</th><th>İstiqamət</th><th>80 % aralıq</th></tr>` +
    d.rows.map((r) => `<tr><td>${hhmm(r.target_t)}</td><td>${hn[r.horizon]}</td><td>${esc(names[r.method] || r.method)}</td>
      <td class="n">${fmt(r.price0)}</td><td class="n">${fmt(r.price1)}</td><td class="n">${(r.p_up * 100).toFixed(1)} %</td>
      <td>${r.hit == null ? "<span class='mut'>—</span>" : r.hit ? "<span class='up'>düz</span>" : "<span class='down'>səhv</span>"}</td>
      <td>${r.in80 ? "<span class='up'>tutdu</span>" : "<span class='down'>tutmadı</span>"}</td></tr>`).join("") + "</table>";
}

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
async function refreshAll() { await refreshState(); await refreshFc(); await loadChart(); await loadJournal(); }

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
refreshAll();
setInterval(() => refreshState().catch(() => {}), 5000);
setInterval(() => loadChart().catch(() => {}), 10000);
setInterval(() => { refreshFc().catch(() => {}); loadJournal().catch(() => {}); }, 20000);
