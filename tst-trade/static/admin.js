/* TST Trade admin: key places, data sources, brain slots, price source, history. */
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const PROV = { goldapi: "gold-api.com (pulsuz)", twelvedata: "Twelve Data (açar)", demo: "DEMO (yalnız sınaq)" };
const BRAIN_PROV = { anthropic: "Anthropic", openai: "OpenAI", xai: "xAI (Grok)", gemini: "Google Gemini" };
const FIELD_AZ = { key: "Açar", key_id: "Açar ID", secret: "Gizli açar" };
const STAGE = { live: ["ok", "işləyir"], next: ["next", "yeri hazırdır, toplayıcı növbəti mərhələdə"] };
let data = null;

async function call(method, path, body) {
  const r = await fetch(path, { method, credentials: "same-origin", headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined });
  if (r.status === 401) { location.href = "/login"; throw new Error("login"); }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || j.error || ("HTTP " + r.status));
  return j;
}
const when = (ts) => ts ? new Date(ts * 1000).toLocaleString("az") : "";

function keyState(st) {
  if (st.unreadable) return `<span class="pill bad">yenidən daxil edin</span>`;
  if (!st.saved) return `<span class="pill next">açar yoxdur</span>`;
  if (st.check && st.check.ok === null) return `<span class="pill warn">saxlanıb</span>`;
  if (st.check) return st.check.ok ? `<span class="pill ok">işləyir</span>` : `<span class="pill bad">xəta</span>`;
  return `<span class="pill warn">saxlanıb, yoxlanmayıb</span>`;
}

function keySlot(k) {
  const st = k.state, stage = STAGE[k.stage];
  const inputs = k.fields.map((f) => `<label class="note" for="f-${k.id}-${f}">${FIELD_AZ[f] || f}</label>
    <input id="f-${k.id}-${f}" type="password" autocomplete="off" placeholder="${st.saved ? "yenisini yapışdırın" : "yapışdırın"}">`).join("");
  return `<div class="slot"><div class="hd"><b>${esc(k.name)}</b>${keyState(st)}</div>
    <div class="meta"><span>Nə üçün</span><span>${esc(k.purpose)}</span>
      <span>Qiymət</span><span>${esc(k.cost)}</span>
      <span>İstifadə edən</span><span>${esc(k.used_by)}</span>
      <span>Mərhələ</span><span><span class="pill ${stage[0]}">${stage[1]}</span></span>
      <span>Haradan alınır</span><span><a href="${esc(k.url)}" target="_blank" rel="noopener">${esc(k.url.replace("https://", ""))}</a></span>
      ${st.hint ? `<span>Saxlanan</span><span class="num">${esc(st.hint)} · ${when(st.saved_ts)}</span>` : ""}
      ${st.check ? `<span>Açar yoxlaması</span><span>${esc(st.check.message)} · ${when(st.check.ts)}</span>` : ""}
      ${k.id === "fred" ? healthLine(k.health) : ""}</div>
    ${inputs}
    ${k.id === "fred" ? `<div class="btns"><button class="btn" data-feed="macro">Makronu indi yüklə</button></div>` : ""}
    <div class="btns"><button class="btn pri" data-act="save" data-k="${k.id}">Saxla</button>
      <button class="btn" data-act="check" data-k="${k.id}" ${st.saved ? "" : "disabled"}>Yoxla</button>
      <button class="btn dan" data-act="del" data-k="${k.id}" ${st.saved ? "" : "disabled"}>Sil</button></div>
    <div class="msg" id="m-${k.id}"></div></div>`;
}

function healthLine(h) {
  if (!h || !h.checked) return "";
  return `<span>Son yoxlama</span><span>${h.ok ? "<span class='up'>işləyir</span>" : "<span class='down'>alınmadı</span>"} · ${esc(h.message)} · ${when(h.checked)}</span>`;
}

function freeSlot(f) {
  const stage = STAGE[f.stage];
  return `<div class="slot"><div class="hd"><b>${esc(f.name)}</b><span class="pill info">açar lazım deyil</span></div>
    <div class="meta"><span>Nə üçün</span><span>${esc(f.purpose)}</span><span>Qiymət</span><span>${esc(f.cost)}</span>
    <span>Mərhələ</span><span><span class="pill ${stage[0]}">${stage[1]}</span></span>${healthLine(f.health)}</div>
    ${f.id === "rss" ? `<div class="btns"><button class="btn" data-feed="news">İndi yenilə</button></div>` : ""}
    ${f.id === "forexfactory" ? `<div class="btns"><button class="btn" data-feed="calendar">İndi yenilə</button></div>` : ""}</div>`;
}

function brainSlot(b) {
  const c = b.config;
  const opts = (sel, none) => (none ? `<option value="">— yoxdur —</option>` : "") +
    data.brain_providers.map((p) => `<option value="${p}" ${p === sel ? "selected" : ""}>${BRAIN_PROV[p]}</option>`).join("");
  const req = b.requirements.map((r) => `<div><span>${esc(r.name)}</span><span class="num">${r.weight} %</span>
    <div class="bar" style="grid-column:1/3"><i style="width:${r.weight}%"></i></div></div>`).join("");
  const stCls = { "hazırdır": "ok", "açar yoxdur": "next", "yoxlanmayıb": "warn" }[b.state] || "bad";
  return `<div class="slot"><div class="hd"><b>${esc(b.name)}</b><span class="pill ${stCls}">${esc(b.state)}</span></div>
    <div class="meta"><span>İşi</span><span>${esc(b.job)}</span><span>Edə bilməz</span><span>${esc(b.may_not)}</span>
      <span>Niyə bu beyin</span><span>${esc(b.why)}</span>
      <span>Proqnozda</span><span>${b.in_use ? "istifadə olunur" : "hələ qoşulmayıb (növbəti addım)"}</span></div>
    <div class="note">Tələblər və çəkisi</div><div class="req">${req}</div>
    <label class="note" for="bp-${b.id}">Beyin (provayder)</label><select id="bp-${b.id}">${opts(c.provider)}</select>
    <label class="note" for="bm-${b.id}">Model</label><input id="bm-${b.id}" value="${esc(c.model)}">
    <label class="note" for="bf-${b.id}">Ehtiyat beyin</label><select id="bf-${b.id}">${opts(c.fallback, true)}</select>
    <label class="note" for="bfm-${b.id}">Ehtiyat model</label><input id="bfm-${b.id}" value="${esc(c.fallback_model || "")}">
    <label class="note" for="bu-${b.id}">Aylıq xərc limiti, $</label><input id="bu-${b.id}" type="number" min="0" max="1000" step="1" value="${c.month_usd}">
    <div class="btns"><button class="btn pri" data-bsave="${b.id}">Saxla</button><button class="btn" data-bcheck="${b.id}">Beyni yoxla</button>
      <button class="btn" data-breset="${b.id}">Tövsiyəyə qaytar</button></div>
    <div class="msg" id="bm-msg-${b.id}"></div></div>`;
}

function render() {
  $("secretwarn").hidden = data.secret_fixed;
  $("provider").innerHTML = data.providers.map((p) =>
    `<button class="btn ${p === data.price_provider ? "pri" : ""}" data-prov="${p}">${PROV[p]}</button>`).join("");
  $("provnote").textContent = "İndi işləyən: " + (PROV[data.active_provider] || data.active_provider || "—") +
    ". Twelve Data-nın pulsuz planı yalnız qızılı verir; 4 metal üçün gold-api.com və ya pullu plan lazımdır.";
  $("cats").innerHTML = data.categories.map(([id, name]) => {
    const ks = data.keys.filter((k) => k.category === id).map(keySlot).join("");
    const fs = data.free.filter((f) => f.category === id).map(freeSlot).join("");
    return `<h3>${esc(name)}</h3><div class="grid">${ks}${fs}</div>`;
  }).join("");
  $("brains").innerHTML = data.brains.map(brainSlot).join("");
  const h = data.history || {};
  $("histres").innerHTML = h.note ? `<p class="note">${esc(h.note)}</p>` : h.result ?
    `<table><tr><th>Metal</th><th>1 dəq</th><th>1 saat</th><th>1 gün</th><th>1 həftə</th></tr>` +
    Object.entries(h.result).map(([s, r]) => `<tr><td>${s}</td>${["1m", "1h", "1d", "1w"].map((t) => `<td>${esc(r[t] || "—")}</td>`).join("")}</tr>`).join("") +
    `</table><p class="note">Son yükləmə: ${when(h.ts)} (${esc(h.source)})</p>` : "<p class='note'>Hələ yüklənməyib.</p>";
  wire();
}

function wire() {
  document.querySelectorAll("[data-feed]").forEach((b) => b.onclick = async () => {
    b.disabled = true; b.textContent = "Yüklənir…";
    try { await call("POST", `/api/admin/feeds/${b.dataset.feed}`); } catch (e) { alert(e.message); }
    load();
  });
  document.querySelectorAll("[data-prov]").forEach((b) => b.onclick = async () => {
    await call("POST", "/api/admin/provider", { provider: b.dataset.prov }); load();
  });
  document.querySelectorAll("[data-act]").forEach((b) => b.onclick = async () => {
    const k = b.dataset.k, msg = $("m-" + k), slot = data.keys.find((x) => x.id === k);
    try {
      if (b.dataset.act === "save") {
        const v = {}; slot.fields.forEach((f) => v[f] = $(`f-${k}-${f}`).value);
        await call("POST", `/api/admin/keys/${k}`, v);
        const res = await call("POST", `/api/admin/keys/${k}/check`);
        msg.textContent = "Saxlanıldı. Yoxlama: " + res.message;
      } else if (b.dataset.act === "check") {
        const res = await call("POST", `/api/admin/keys/${k}/check`); msg.textContent = res.message;
      } else if (b.dataset.act === "del") {
        await call("DELETE", `/api/admin/keys/${k}`); msg.textContent = "Silindi.";
      }
      setTimeout(load, 600);
    } catch (e) { msg.textContent = "Xəta: " + e.message; }
  });
  document.querySelectorAll("[data-bsave]").forEach((b) => b.onclick = async () => {
    const id = b.dataset.bsave, msg = $("bm-msg-" + id);
    try {
      await call("POST", `/api/admin/brains/${id}`, { provider: $("bp-" + id).value, model: $("bm-" + id).value,
        fallback: $("bf-" + id).value, fallback_model: $("bfm-" + id).value, month_usd: $("bu-" + id).value });
      msg.textContent = "Saxlanıldı."; setTimeout(load, 600);
    } catch (e) { msg.textContent = "Xəta: " + e.message; }
  });
  document.querySelectorAll("[data-breset]").forEach((b) => b.onclick = async () => {
    const id = b.dataset.breset, d = data.brains.find((x) => x.id === id).default, msg = $("bm-msg-" + id);
    try { await call("POST", `/api/admin/brains/${id}`, { ...d, fallback: d.fallback || "" }); msg.textContent = "Tövsiyə olunan beyin qaytarıldı."; setTimeout(load, 600); }
    catch (e) { msg.textContent = "Xəta: " + e.message; }
  });
  document.querySelectorAll("[data-bcheck]").forEach((b) => b.onclick = async () => {
    const id = b.dataset.bcheck, msg = $("bm-msg-" + id);
    msg.textContent = "Yoxlanır…";
    try { const r = await call("POST", `/api/admin/brains/${id}/check`); msg.textContent = r.message; setTimeout(load, 600); }
    catch (e) { msg.textContent = "Xəta: " + e.message; }
  });
}

$("hist").onclick = async () => {
  $("histres").innerHTML = "<p class='note'>Yüklənir… (pulsuz plan dəqiqədə 8 sorğu verir, bir neçə dəqiqə çəkə bilər)</p>";
  try { await call("POST", "/api/admin/history"); } catch (e) { $("histres").textContent = "Xəta: " + e.message; }
  load();
};

$("pw-save").onclick = async () => {
  try {
    await call("POST", "/api/admin/password", { old: $("pw-old").value, new: $("pw-new").value, again: $("pw-again").value });
    $("pw-msg").textContent = "Parol dəyişdi. Növbəti girişdə yeni paroldan istifadə edin.";
    ["pw-old", "pw-new", "pw-again"].forEach((i) => $(i).value = "");
  } catch (e) { $("pw-msg").textContent = "Xəta: " + e.message; }
};

async function load() { data = await call("GET", "/api/admin/overview"); render(); }
load();
