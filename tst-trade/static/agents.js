// Agents panel: reads only the central activity hub (snapshot + live WebSocket + 24h events). Never talks to agents.
"use strict";
const $ = (id) => document.getElementById(id);
const WORD = { waiting: "Gözləyir", working: "İşləyir", done: "Bitdi", error: "Xəta" };
const COLOR = { waiting: "#6b7a99", working: "#38c8ff", done: "#3ee08f", error: "#ff5d6c" };
const FRESH = 12;                       // seconds a just-finished task keeps its green dot
// where each card sits on the stage (percent of width, height); the orchestrator is the centre
const POS = {
  orch: [50, 50], history: [50, 8], macro: [32, 8], scout: [68, 8],
  prices: [19, 22], liquidity: [8, 41], risk: [8, 62], forecast: [24, 44], judge: [24, 70], decision: [36, 91],
  news: [81, 22], reader: [92, 41], signals: [75, 47], strateq: [92, 62], debate: [75, 71],
  calendar: [58, 91], hunter: [79, 92],
};
let NODES = [], live = {}, shown = {}, skew = 0, events = [], mode = "live";
let winH = 1, speed = 10, playT = null, lastPulse = 0;
const cards = {};
const now = () => Date.now() / 1000 + skew;
const ny = (t, sec) => new Date(t * 1000).toLocaleTimeString("en-GB",
  { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", second: sec ? "2-digit" : undefined });
function ago(t) {
  if (!t) return "—";
  const s = Math.max(0, now() - t);
  return s < 60 ? `${Math.round(s)} san əvvəl` : s < 3600 ? `${Math.round(s / 60)} dəq əvvəl` : `${(s / 3600).toFixed(1)} saat əvvəl`;
}
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// ---------- cards ----------
function build(nodes) {
  NODES = nodes;
  const stage = $("stage");
  Object.values(cards).forEach((c) => c.remove());
  const order = [];
  const walk = (id, depth) => { order.push([id, depth]); nodes.filter((n) => n.parent === id).forEach((n) => walk(n.id, depth + 1)); };
  nodes.filter((n) => !n.parent).forEach((n) => walk(n.id, 0));
  for (const [id, depth] of order) {
    const n = nodes.find((x) => x.id === id);
    const el = document.createElement("button");
    el.type = "button";
    el.className = "node" + (id === "orch" ? " orch" : "") + (depth > 1 ? " child" : "");
    const [x, y] = id === "orch" ? [50, 71] : POS[id] || [50, 50];   // the orchestrator's label sits under its sphere
    el.style.left = x + "%"; el.style.top = y + "%";
    el.title = n.what;
    el.addEventListener("click", () => openDetail(id));
    stage.appendChild(el);
    cards[id] = el;
  }
}
function render() {
  const st = mode === "live" ? live : shown;
  for (const n of NODES) {
    const s = st[n.id] || { status: "waiting" };
    const el = cards[n.id];
    if (!el) continue;
    el.classList.remove("waiting", "working", "done", "error");
    el.classList.add(s.status);
    const cur = s.status === "working" ? s.stage : null;
    const idx = n.stages.indexOf(cur);
    const ws = n.stages.map((w, i) => {
      const cls = s.status === "done" || (idx >= 0 && i < idx) ? "ok" : i === idx ? "now" : "";
      return `<span class="w ${cls}">${esc(w.split(" ")[0])}${cls === "ok" ? " ✓" : ""}</span>`;
    }).join("");
    const prog = s.status === "working" && s.progress != null ? s.progress : null;
    const fresh = s.status === "done" && s.done_ts && now() - s.done_ts < FRESH;
    el.innerHTML = `${fresh ? '<i class="fresh" title="İndicə bitdi"></i>' : ""}
      <div class="h"><span class="n">${String(n.num).padStart(2, "0")}</span><span class="t">${esc(n.name)}</span>
      <span class="st">${WORD[s.status]}</span></div>
      <div class="sub">${esc(cur || s.note || n.what)}${s.ts ? " · " + ago(s.ts) : ""}</div>
      ${n.stages.length ? `<div class="ws">${ws}</div>` : ""}
      ${prog != null ? `<div class="bar"><b style="width:${Math.round(prog * 100)}%"></b></div>` : ""}`;
    el.setAttribute("aria-label", `${n.num}. ${n.name}: ${WORD[s.status]}${cur ? ", " + cur : ""}`);
  }
}
function openDetail(id) {
  const n = NODES.find((x) => x.id === id);
  const s = (mode === "live" ? live : shown)[id] || {};
  const evs = events.filter((e) => e.task === id).slice(-12).reverse();
  const d = $("detail");
  d.innerHTML = `<button class="x" aria-label="Bağla">✕</button><h3>${String(n.num).padStart(2, "0")} · ${esc(n.name)}</h3>
    <p>${esc(n.what)}</p>
    <p>Asılıdır: <b>${esc(n.parent ? NODES.find((x) => x.id === n.parent).name : "— (kök)")}</b></p>
    <p>İndi: <b style="color:${COLOR[s.status || "waiting"]}">${WORD[s.status || "waiting"]}</b> ${esc(s.stage || "")} ${esc(s.note || "")}</p>
    ${n.stages.length ? `<p>Mərhələlər: ${n.stages.map(esc).join(" → ")}</p>` : ""}
    <ul>${evs.map((e) => `<li><span style="color:${COLOR[e.status]}">●</span> ${ny(e.ts, true)} ${WORD[e.status]} ${esc(e.stage || "")} ${esc(e.note || "")}</li>`).join("") || "<li>Son saatlarda hadisə yoxdur</li>"}</ul>`;
  d.classList.add("open");
  d.querySelector(".x").onclick = () => d.classList.remove("open");
}

// ---------- the sphere and the links (canvas) ----------
const cv = $("net"), cx = cv.getContext("2d");
const PTS = Array.from({ length: 420 }, (_, i) => {          // points evenly on a sphere (golden spiral)
  const y = 1 - (i / 419) * 2, r = Math.sqrt(1 - y * y), a = i * 2.399963;
  return [Math.cos(a) * r, y, Math.sin(a) * r];
});
const phone = () => matchMedia("(max-width:760px)").matches;
function draw(tms) {
  const w = cv.clientWidth, h = cv.clientHeight, dpr = devicePixelRatio || 1;
  if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = w * dpr; cv.height = h * dpr; }
  cx.setTransform(dpr, 0, 0, dpr, 0, 0);
  cx.clearRect(0, 0, w, h);
  const t = tms / 1000, st = mode === "live" ? live : shown;
  const busy = Object.values(st).filter((s) => s.status === "working").length;
  const err = (st.orch || {}).status === "error";     // red only when the main loop itself fails; others show on their cards
  const ox = w / 2, oy = h / 2;
  // links: parent -> child, glowing and carrying a moving dot while the child works
  if (!phone()) {
    for (const n of NODES) {
      if (!n.parent || !POS[n.id] || !POS[n.parent]) continue;
      const [x1, y1] = POS[n.parent], [x2, y2] = POS[n.id];
      const ax = x1 / 100 * w, ay = y1 / 100 * h, bx = x2 / 100 * w, by = y2 / 100 * h;
      const s = (st[n.id] || {}).status || "waiting";
      cx.strokeStyle = COLOR[s] + (s === "waiting" ? "55" : "bb");
      cx.lineWidth = s === "working" ? 2 : 1.2;
      cx.shadowColor = COLOR[s]; cx.shadowBlur = s === "waiting" ? 0 : 10;
      cx.setLineDash(s === "waiting" ? [4, 6] : []);
      cx.beginPath(); cx.moveTo(ax, ay); cx.lineTo(bx, by); cx.stroke();
      cx.setLineDash([]);
      if (s === "working") {
        for (let k = 0; k < 3; k++) {
          const f = ((t * 0.6 + k / 3) % 1);
          cx.fillStyle = COLOR.working;
          cx.beginPath(); cx.arc(ax + (bx - ax) * f, ay + (by - ay) * f, 2.6, 0, 7); cx.fill();
        }
      }
      cx.shadowBlur = 0;
    }
  }
  // the orchestrator sphere: rotating points, faster and brighter the more agents work; red tint on any error
  const R = phone() ? 44 : Math.min(w, h) * 0.13;
  const spin = t * (0.15 + busy * 0.08), tilt = 0.35;
  const pulse = Math.max(0, 1 - (performance.now() - lastPulse) / 900);
  const base = err ? [255, 93, 108] : [56, 200, 255];
  const g = cx.createRadialGradient(ox, oy, R * 0.1, ox, oy, R * 1.6);
  g.addColorStop(0, `rgba(${base},${0.18 + pulse * 0.25})`); g.addColorStop(1, "rgba(0,0,0,0)");
  cx.fillStyle = g; cx.beginPath(); cx.arc(ox, oy, R * 1.6, 0, 7); cx.fill();
  for (const [px, py, pz] of PTS) {
    const x = px * Math.cos(spin) - pz * Math.sin(spin), z0 = px * Math.sin(spin) + pz * Math.cos(spin);
    const y = py * Math.cos(tilt) - z0 * Math.sin(tilt), z = py * Math.sin(tilt) + z0 * Math.cos(tilt);
    const a = 0.15 + 0.85 * (z + 1) / 2;
    cx.fillStyle = `rgba(${base},${a})`;
    cx.beginPath(); cx.arc(ox + x * R * (1 + pulse * 0.06), oy + y * R * (1 + pulse * 0.06), 0.6 + a * 1.4, 0, 7); cx.fill();
  }
  // orbit ring
  cx.strokeStyle = `rgba(${base},0.25)`; cx.lineWidth = 1;
  cx.beginPath(); cx.ellipse(ox, oy, R * 1.35, R * 0.38, -0.2, 0, 7); cx.stroke();
  const oa = t * 1.2;
  cx.fillStyle = `rgb(${base})`; cx.beginPath();
  cx.arc(ox + Math.cos(oa) * R * 1.35 * Math.cos(-0.2) - Math.sin(oa) * R * 0.38 * Math.sin(-0.2),
         oy + Math.cos(oa) * R * 1.35 * Math.sin(-0.2) + Math.sin(oa) * R * 0.38 * Math.cos(-0.2), 3, 0, 7); cx.fill();
  if (mode === "replay") stepReplay();
  drawTimeline();
  requestAnimationFrame(draw);
}

// ---------- timeline and replay ----------
const tc = $("tlc"), tx = tc.getContext("2d");
let tlFrom = 0, tlTo = 0;
function drawTimeline() {
  const w = tc.clientWidth, h = tc.clientHeight, dpr = devicePixelRatio || 1;
  if (tc.width !== Math.round(w * dpr) || tc.height !== Math.round(h * dpr)) { tc.width = w * dpr; tc.height = h * dpr; }
  tx.setTransform(dpr, 0, 0, dpr, 0, 0);
  tx.clearRect(0, 0, w, h);
  tlTo = mode === "live" ? now() : Math.max(tlTo, now());
  tlFrom = tlTo - winH * 3600;
  const rows = NODES.length || 1, rh = (h - 12) / rows;
  const X = (ts) => (ts - tlFrom) / (tlTo - tlFrom) * w;
  // hour ticks in New York time
  tx.fillStyle = "rgba(138,151,180,.6)"; tx.font = "10px ui-monospace,monospace";
  const step = winH <= 1 ? 600 : winH <= 6 ? 3600 : 3 * 3600;
  for (let s = Math.ceil(tlFrom / step) * step; s < tlTo; s += step) {
    tx.fillRect(X(s), 0, 1, h - 12); tx.fillText(ny(s), X(s) + 3, h - 2);
  }
  NODES.forEach((n, i) => {
    tx.fillStyle = "rgba(255,255,255,.03)"; tx.fillRect(0, i * rh, w, rh - 1);
  });
  const row = Object.fromEntries(NODES.map((n, i) => [n.id, i]));
  for (const e of events) {
    if (e.ts < tlFrom || !(e.task in row)) continue;
    tx.fillStyle = COLOR[e.status];
    tx.fillRect(X(e.ts), row[e.task] * rh, e.status === "working" ? 1.5 : 2.5, rh - 1);
  }
  if (mode === "replay" && playT) {
    tx.fillStyle = "#e8b94a"; tx.fillRect(X(playT) - 1, 0, 2, h - 12);
  }
  $("tltime").textContent = mode === "replay" && playT ? `Təkrar: ${ny(playT, true)} NY · x${speed}` : `Canlı · ${events.length} hadisə`;
}
let lastFrame = 0, idx = 0;
function startReplay(from) {
  mode = "replay"; playT = from; idx = 0; lastFrame = performance.now();
  shown = Object.fromEntries(NODES.map((n) => [n.id, { status: "waiting" }]));
  while (idx < events.length && events[idx].ts <= playT) apply(shown, events[idx++]);
  $("conn").className = "conn replay"; $("conn").textContent = "Təkrar";
  render();
}
function stepReplay() {
  const p = performance.now(), dt = (p - lastFrame) / 1000; lastFrame = p;
  playT += dt * speed;
  let changed = false;
  while (idx < events.length && events[idx].ts <= playT) { apply(shown, events[idx++]); changed = true; }
  if (changed) { lastPulse = p; render(); }
  if (playT >= now()) goLive();
}
function goLive() {
  mode = "live"; playT = null;
  setConn(ws && ws.readyState === 1);
  render();
}
function apply(st, e) {
  const s = st[e.task] || (st[e.task] = {});
  Object.assign(s, { status: e.status, stage: e.stage, progress: e.progress, note: e.note, ts: e.ts });
  if (e.status === "done") s.done_ts = e.ts;
}
tc.addEventListener("click", (ev) => {
  const r = tc.getBoundingClientRect();
  startReplay(tlFrom + (ev.clientX - r.left) / r.width * (tlTo - tlFrom));
});
$("play").onclick = () => startReplay(now() - winH * 3600);
$("live").onclick = goLive;
$("win").onclick = (ev) => {
  const b = ev.target.closest("button"); if (!b) return;
  winH = +b.dataset.h; [...$("win").children].forEach((x) => x.classList.toggle("on", x === b));
  if (winH > 1) loadEvents();
};
$("speed").onclick = (ev) => {
  const b = ev.target.closest("button"); if (!b) return;
  speed = +b.dataset.x; [...$("speed").children].forEach((x) => x.classList.toggle("on", x === b));
};

// ---------- data: live WebSocket + history ----------
let ws = null, retry = 1;
function setConn(on) {
  if (mode !== "live") return;
  $("conn").className = "conn" + (on ? " on" : "");
  $("conn").textContent = on ? "Canlı" : "Bağlantı yoxdur";
}
function connect() {
  ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws/agents");
  ws.onopen = () => { retry = 1; setConn(true); };
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data);
    if (d.type === "snapshot") {
      skew = d.now - Date.now() / 1000;
      if (!NODES.length) build(d.nodes);
      live = d.state; render();
    } else if (d.type === "event") {
      apply(live, d.event); events.push(d.event);
      if (mode === "live") { lastPulse = performance.now(); render(); }
    }
  };
  ws.onclose = (ev) => {
    setConn(false);
    if (ev.code === 4403) { location.href = "/login"; return; }
    setTimeout(connect, Math.min(30, retry *= 2) * 1000);   // back off, never hammer the server
  };
}
async function loadEvents() {
  try {
    const r = await fetch(`/api/agents/events?hours=24`, { credentials: "same-origin" });
    if (!r.ok) return;
    const d = await r.json();
    if (!NODES.length) build(d.nodes);
    events = d.events;
  } catch (e) { /* the live stream still works */ }
}
async function loadTop() {
  try {
    const r = await fetch("/api/agents/top", { credentials: "same-origin" });
    if (!r.ok) return;
    const d = await r.json();
    $("limits").innerHTML = d.limits.map((l) => {
      const f = l.cap > 0 ? Math.min(1, l.spent / l.cap) : 0;
      return `<span class="lim${f > 0.8 ? " hot" : ""}" title="${esc(l.name)}: $${l.spent.toFixed(2)} / $${l.cap.toFixed(0)}">
        <span>${esc(l.name)} $${l.spent.toFixed(2)}/${l.cap.toFixed(0)}</span><i><b style="width:${Math.round(f * 100)}%"></b></i></span>`;
    }).join("") || '<span class="chip">Beyin qoşulmayıb</span>';
    $("sync").innerHTML = Object.entries(d.sync).map(([k, t]) => {
      const age = t ? now() - t : Infinity;
      const cls = !t ? "bad" : (k === "Qiymət" ? age < 60 : age < 6 * 3600) ? "ok" : "old";
      return `<span class="chip ${cls}" title="${t ? ny(t, true) + " NY" : "heç vaxt"}">${esc(k)} ${t ? ago(t) : "—"}</span>`;
    }).join("");
  } catch (e) { /* keep the last values */ }
}
setInterval(() => { $("clock").textContent = ny(now(), true) + " NY"; if (mode === "live") render(); }, 1000);
setInterval(loadTop, 15000);
loadEvents().then(connect);
loadTop();
requestAnimationFrame(draw);
