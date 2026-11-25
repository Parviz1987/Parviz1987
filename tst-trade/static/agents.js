// Agents panel: reads only the central activity hub (snapshot + live WebSocket + 24h events). Never talks to agents.
// The stage is a nervous system drawn on one canvas, left to right: Gözlər -> Sinirlər -> Beyin -> Hakim -> Qərar
// (top to bottom on a phone). Fibres follow the real data flow (node.src -> node). Every light that moves is a REAL
// event from the hub: a courier travels from the event's source to its task; the brain's neurons fire only while the
// brain agents really work. Nothing is invented: a quiet system shows dim fibres and a slowly breathing brain.
"use strict";
const $ = (id) => document.getElementById(id);
const WORD = { waiting: "Gözləyir", working: "İşləyir", done: "Bitdi", error: "Xəta" };
const COLOR = { waiting: "#6b7a99", working: "#38c8ff", done: "#3ee08f", error: "#ff5d6c" };
const SIDX = { waiting: 0, working: 1, done: 2, error: 3 };
const FRESH = 12;                       // seconds a just-finished task keeps its green dot
// the five lanes of the nervous system; a task that is not listed goes one lane after its data source
const LANES = [
  { key: "eyes", name: "Gözlər", ids: ["news", "events", "scout", "calendar", "macro", "archivist", "reporter", "history", "prices", "liquidity"] },
  { key: "nerves", name: "Sinirlər", ids: ["reader", "signals", "hunter"] },
  { key: "brain", name: "Beyin", ids: ["strateq", "debate", "ta", "chartist", "cards", "checker"] },
  { key: "judge", name: "Hakim", ids: ["forecast", "judge"] },
  { key: "act", name: "Qərar", ids: ["risk", "decision"] },
];
const LANE_W = [1.25, 0.85, 1.7, 0.85, 0.85];          // relative lane widths on a wide screen
const BRAIN_IDS = ["strateq", "debate", "reader", "cards", "checker", "ta", "chartist"];   // their work makes the brain's neurons fire
let NODES = [], live = {}, shown = {}, skew = 0, events = [], mode = "live";
let nerveState = "SAKİT";
let winH = 1, speed = 10, playT = null, lastPulse = 0, frozenT = 0;
let paused = matchMedia("(prefers-reduced-motion: reduce)").matches;   // the user asked the system for less motion
const cards = {};                       // id -> invisible button over the agent (keyboard, click, screen reader)
const now = () => Date.now() / 1000 + skew;
const ny = (t, sec) => new Date(t * 1000).toLocaleTimeString("en-GB",
  { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", second: sec ? "2-digit" : undefined });
function ago(t) {
  if (!t) return "—";
  const s = Math.max(0, now() - t);
  return s < 60 ? `${Math.round(s)} san əvvəl` : s < 3600 ? `${Math.round(s / 60)} dəq əvvəl` : `${(s / 3600).toFixed(1)} saat əvvəl`;
}
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const curState = () => (mode === "live" ? live : shown);
const phone = () => matchMedia("(max-width:760px)").matches;

// ---------- the agents ("bots") ----------
let BOTS = [], BY = {}, CORE = null;   // BY: id -> bot; CORE: the orchestrator, drawn as the brain
let FIB = [];                          // fibres: {a: source bot or null (outside world), b: target bot, s: bend sign}
function laneOf(n, byId) {
  for (let i = 0; i < LANES.length; i++) if (LANES[i].ids.includes(n.id)) return i;
  const src = n.src && byId[n.src];
  if (src && src.id !== "orch") return Math.min(LANES.length - 1, laneOf(src, byId) + 1);
  return 1;
}
function hash(s) { let h = 7; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return Math.abs(h); }
function build(nodes) {
  NODES = nodes;
  const stage = $("stage");
  Object.values(cards).forEach((c) => c.remove());
  for (const k in cards) delete cards[k];
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  BOTS = []; BY = {};
  for (const n of nodes) {
    const b = { id: n.id, n, lane: n.id === "orch" ? 2 : laneOf(n, byId), x: 0, y: 0, cx: 0, cy: 0, r: 13,
      ph: (hash(n.id) % 628) / 100, flashT: -1e9, flashC: 1, l1: [n.name], l2: "", l2c: COLOR.waiting };
    BOTS.push(b); BY[n.id] = b;
    const el = document.createElement("button");
    el.type = "button";
    el.className = "hit" + (n.id === "orch" ? " core" : "");
    el.addEventListener("click", () => openDetail(n.id));
    el.addEventListener("mouseenter", () => showTip(n.id));
    el.addEventListener("mouseleave", hideTip);
    el.addEventListener("focus", () => showTip(n.id));
    el.addEventListener("blur", hideTip);
    stage.appendChild(el);
    cards[n.id] = el;
  }
  CORE = BY.orch || null;
  FIB = [];
  for (const b of BOTS) {
    if (b === CORE) continue;
    const src = b.n.src ? BY[b.n.src] : null;
    if (b.n.src && !src) continue;
    FIB.push({ a: src, b, s: hash(b.id) % 2 ? 1 : -1, glowT: -1e9, glowC: 1 });
  }
  layoutKey = "";
}

// lane geometry: computed from the lanes, so any number of agents fits
let layoutKey = "", W = 0, H = 0, R = 60, lanesGeo = [];
function layout(w, h) {
  const ph = phone();
  lanesGeo = [];
  const groups = LANES.map(() => []);
  for (const b of BOTS) if (b !== CORE) groups[b.lane].push(b);
  groups.forEach((g, i) => g.sort((p, q) => {
    const ip = LANES[i].ids.indexOf(p.id), iq = LANES[i].ids.indexOf(q.id);
    return (ip < 0 ? 99 : ip) - (iq < 0 ? 99 : iq) || p.n.num - q.n.num;
  }));
  if (!ph) {
    const top = 62, bot = 14, sum = LANE_W.reduce((a, b) => a + b, 0);
    let x0 = 0;
    LANES.forEach((L, i) => {
      const lw = w * LANE_W[i] / sum, cx = x0 + lw / 2;
      lanesGeo.push({ name: L.name, x: cx, y: 44, x0, w: lw });
      const g = groups[i];
      if (L.key === "brain") {
        R = Math.max(40, Math.min(lw * 0.3, (h - top - bot) * 0.2));
        const cy = top + (h - top - bot) / 2;
        if (CORE) { CORE.x = cx; CORE.y = cy; CORE.r = R * 0.62; }
        const angs = g.length === 4 ? [-2.36, -0.785, 2.36, 0.785] : g.map((_, k) => -Math.PI / 2 + (k + 0.5) * 2 * Math.PI / g.length);
        g.forEach((b, k) => {
          b.x = cx + Math.cos(angs[k]) * R * 1.4;
          b.y = cy + Math.sin(angs[k]) * R * 1.95;
          b.r = 13; b.maxW = Math.min(lw * 0.48, 118);
        });
      } else {
        const avail = h - top - bot, per = Math.max(1, Math.floor(avail / 70));
        const zig = g.length > per;
        g.forEach((b, k) => {
          b.x = zig ? cx + (k % 2 ? 1 : -1) * lw * 0.21 : cx;
          b.y = top + (k + 0.5) * avail / g.length - 8;
          b.r = 13; b.maxW = Math.min(zig ? lw * 0.58 : lw * 0.92, 118);
        });
      }
      x0 += lw;
    });
    H = h;
  } else {
    // phone: lanes top to bottom, three agents per row
    let y = 6;
    const cols = w < 430 ? 3 : 4;
    LANES.forEach((L, i) => {
      const g = groups[i];
      lanesGeo.push({ name: L.name, x: 4, y: y + 12, y0: y, w });
      y += 22;
      if (L.key === "brain") {
        R = Math.min(w * 0.19, 72);
        const cy = y + R * 0.85, cx = w / 2;
        if (CORE) { CORE.x = cx; CORE.y = cy; CORE.r = R * 0.62; }
        g.forEach((b, k) => {
          const left = k % 2 === 0, row = Math.floor(k / 2);
          b.maxW = Math.max(70, Math.min(w / 2 - R * 0.9 - 8, 104)); b.r = 12;
          b.x = left ? b.maxW / 2 + 4 : w - b.maxW / 2 - 4;
          b.y = cy - R * 0.55 + row * R * 1.25;
        });
        y = cy + R * 1.15 + 34;
      } else {
        const rows = Math.ceil(g.length / cols);
        g.forEach((b, k) => {
          const row = Math.floor(k / cols), col = k % cols, inRow = Math.min(cols, g.length - row * cols);
          b.x = w * (col + 0.5) / inRow;
          b.y = y + 16 + row * 74;
          b.r = 12; b.maxW = Math.min(w / inRow - 8, 116);
        });
        y += rows * 74 + 6;
      }
    });
    H = Math.ceil(y + 4);
  }
  W = w;
  makeBrain(ph ? 380 : 720);
  placeHits();
  render();
}
function placeHits() {
  const offX = cv.offsetLeft, offY = cv.offsetTop;
  for (const b of BOTS) {
    const el = cards[b.id];
    if (!el) continue;
    const s = b === CORE ? Math.round(R * 1.5) : 44;
    el.style.width = el.style.height = s + "px";
    el.style.left = Math.round(offX + b.x - s / 2) + "px";
    el.style.top = Math.round(offY + b.y - s / 2) + "px";
  }
}

// labels (built once a second and on every event, so the frame loop only draws text)
const cv = $("net"), cx = cv.getContext("2d");
const FONT_NAME = "700 10.5px Inter,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif";
const FONT_SUB = "500 9.5px ui-monospace,IBM Plex Mono,Menlo,Consolas,monospace";
function fit(text, maxW) {
  if (cx.measureText(text).width <= maxW) return text;
  let s = text;
  while (s.length > 1 && cx.measureText(s + "…").width > maxW) s = s.slice(0, -1);
  return s + "…";
}
function wrap2(text, maxW) {
  if (cx.measureText(text).width <= maxW) return [text];
  const words = text.split(" ");
  let a = words[0], i = 1;
  while (i < words.length && cx.measureText(a + " " + words[i]).width <= maxW) a += " " + words[i++];
  return i < words.length ? [fit(a, maxW), fit(words.slice(i).join(" "), maxW)] : [fit(a, maxW)];
}
function render() {
  const st = curState();
  cx.save();
  for (const b of BOTS) {
    const n = b.n, s = st[n.id] || { status: "waiting" }, el = cards[n.id];
    const maxW = b === CORE ? 140 : b.maxW || 110;
    cx.font = FONT_NAME; b.l1 = wrap2(n.name, maxW);
    let sub = WORD[s.status];
    if (s.status === "working") {
      sub = s.stage || (s.note && s.note !== "başladı" ? s.note : WORD.working);
      if (s.progress != null) sub += " " + Math.round(s.progress * 100) + "%";
    } else if (s.status !== "waiting" && s.ts) sub += " · " + ago(s.ts);
    cx.font = FONT_SUB; b.l2 = fit(sub, maxW); b.l2c = COLOR[s.status] || COLOR.waiting;
    b.fresh = s.status === "done" && s.done_ts && now() - s.done_ts < FRESH;
    if (el) el.setAttribute("aria-label", `${n.num}. ${n.name}: ${WORD[s.status]}${s.stage ? ", " + s.stage : ""}${s.note ? ", " + s.note : ""}`);
  }
  cx.restore();
  if (tipId) showTip(tipId);
}

// hover / focus card: name, what it does, status, stage, last note and its time (New York)
let tipId = null;
function showTip(id) {
  const b = BY[id], tip = $("agtip");
  if (!b || !tip) return;
  tipId = id;
  const n = b.n, s = curState()[id] || { status: "waiting" };
  const src = n.src ? (BY[n.src] ? BY[n.src].n.name : n.src) : "xarici mənbə";
  tip.innerHTML = `<b>${String(n.num).padStart(2, "0")} · ${esc(n.name)}</b><p>${esc(n.what)}</p>
    <p><span style="color:${COLOR[s.status]}">● ${WORD[s.status]}</span>${s.stage ? " · " + esc(s.stage) : ""}${s.progress != null && s.status === "working" ? " · " + Math.round(s.progress * 100) + "%" : ""}</p>
    ${s.note ? `<p>Son qeyd: ${esc(s.note)}</p>` : ""}
    <p class="m">Son hadisə: ${s.ts ? ny(s.ts, true) + " NY · " + ago(s.ts) : "—"}</p>
    <p class="m">Məlumat haradan: ${esc(src)}</p>`;
  tip.classList.add("open");
  const stg = $("stage"), sw = stg.clientWidth, sh = stg.clientHeight;
  const tw = tip.offsetWidth, th = tip.offsetHeight;
  const bx = cv.offsetLeft + b.x, by = cv.offsetTop + b.y;
  let lx = bx + (b === CORE ? R : 24), ly = by - th / 2;
  if (lx + tw > sw - 6) lx = bx - (b === CORE ? R : 24) - tw;
  lx = Math.max(6, Math.min(sw - tw - 6, lx));
  ly = Math.max(6, Math.min((phone() ? stg.scrollHeight : sh) - th - 6, ly));
  tip.style.left = lx + "px"; tip.style.top = ly + "px";
}
function hideTip() { tipId = null; const t = $("agtip"); if (t) t.classList.remove("open"); }

function openDetail(id) {
  hideTip();
  const n = NODES.find((x) => x.id === id);
  const s = curState()[id] || {};
  const evs = events.filter((e) => e.task === id).slice(-12).reverse();
  const d = $("detail");
  const srcName = n.src ? (NODES.find((x) => x.id === n.src) || { name: n.src }).name : "xarici mənbə";
  d.innerHTML = `<button class="x" aria-label="Bağla">✕</button><h3>${String(n.num).padStart(2, "0")} · ${esc(n.name)}</h3>
    <p>${esc(n.what)}</p>
    <p>Asılıdır: <b>${esc(n.parent ? NODES.find((x) => x.id === n.parent).name : "— (kök)")}</b> · Məlumat: <b>${esc(srcName)}</b></p>
    <p>İndi: <b style="color:${COLOR[s.status || "waiting"]}">${WORD[s.status || "waiting"]}</b> ${esc(s.stage || "")} ${esc(s.note || "")}</p>
    ${s.ts ? `<p>Son hadisə: ${ny(s.ts, true)} NY · ${ago(s.ts)}</p>` : ""}
    ${n.stages.length ? `<p>Mərhələlər: ${n.stages.map(esc).join(" → ")}</p>` : ""}
    ${id === "ta" || id === "chartist" ? `<p><a href="/ta">Texniki analiz blokunu aç →</a></p>` : ""}
    <ul>${evs.map((e) => `<li><span style="color:${COLOR[e.status]}">●</span> ${ny(e.ts, true)} ${WORD[e.status]} ${esc(e.stage || "")} ${esc(e.note || "")}</li>`).join("") || "<li>Son saatlarda hadisə yoxdur</li>"}</ul>`;
  d.classList.add("open");
  const x = d.querySelector(".x");
  x.onclick = () => { d.classList.remove("open"); if (cards[id]) cards[id].focus(); };
}
addEventListener("keydown", (ev) => { if (ev.key === "Escape") { $("detail").classList.remove("open"); hideTip(); } });

// ---------- light sprites (made once: no gradients per frame) ----------
const RGB = [[107, 122, 153], [56, 200, 255], [62, 224, 143], [255, 93, 108]];
const SPRITE = RGB.map(([r, g, b]) => {
  const c = document.createElement("canvas"); c.width = c.height = 64;
  const x = c.getContext("2d"), gr = x.createRadialGradient(32, 32, 0, 32, 32, 32);
  gr.addColorStop(0, "rgba(255,255,255,1)"); gr.addColorStop(0.18, `rgba(${r},${g},${b},.95)`);
  gr.addColorStop(0.5, `rgba(${r},${g},${b},.28)`); gr.addColorStop(1, `rgba(${r},${g},${b},0)`);
  x.fillStyle = gr; x.fillRect(0, 0, 64, 64);
  return c;
});
function glow(i, x, y, size, a) {
  if (a <= 0.01) return;
  cx.globalAlpha = Math.min(1, a);
  cx.drawImage(SPRITE[i], x - size / 2, y - size / 2, size, size);
}

// ---------- couriers: one light per REAL event, from the event's source to its task ----------
const MAXP = 60, DUR = 800;
const P = { on: new Uint8Array(MAXP), a: new Array(MAXP).fill(null), b: new Array(MAXP).fill(null),
  s: new Int8Array(MAXP), t0: new Float64Array(MAXP), c: new Uint8Array(MAXP) };
const Q = new Float64Array(2);
function fibreFor(a, b) { for (const f of FIB) if (f.a === a && f.b === b) return f; return null; }
function anchorOut(b) { return [0, b.cy]; }          // data from outside enters at the left edge
function spawn(e) {
  const b = BY[e.task];
  if (!b || document.hidden) return;
  const ci = SIDX[e.status] ?? 1;
  if (b === CORE) { b.flashT = performance.now(); b.flashC = ci; return; }   // the main loop's beat: the brain glows
  const a = e.src && BY[e.src] ? BY[e.src] : null;
  const f = fibreFor(a, b);
  const t = performance.now();
  if (paused) {                       // less motion: the fibre lights up and the agent glows, nothing travels
    if (f) { f.glowT = t; f.glowC = ci; }
    b.flashT = t; b.flashC = ci;
    if (BRAIN_IDS.includes(b.id) || b === CORE) fireBurst(4);
    return;
  }
  for (let i = 0; i < MAXP; i++) {
    if (P.on[i]) continue;
    P.on[i] = 1; P.a[i] = a; P.b[i] = b; P.s[i] = f ? f.s : 1; P.t0[i] = t; P.c[i] = ci;
    if (f) { f.glowT = t; f.glowC = ci; }
    return;
  }
  b.flashT = t; b.flashC = ci;       // too many lights at once: the agent still glows
}
function ctrl(ax, ay, bx, by, s) {
  const k = 0.16 * s;
  Q[0] = (ax + bx) / 2 - (by - ay) * k; Q[1] = (ay + by) / 2 + (bx - ax) * k;
}
function ends(a, b) {          // [ax, ay] of a fibre's source (the outside world when it has none)
  if (a) return [a.cx, a.cy];
  return anchorOut(b);
}
function drawPulses(tm) {
  cx.globalCompositeOperation = "lighter";
  for (let i = 0; i < MAXP; i++) {
    if (!P.on[i]) continue;
    const u = (tm - P.t0[i]) / DUR, b = P.b[i];
    if (u >= 1) {
      P.on[i] = 0; b.flashT = tm; b.flashC = P.c[i];
      if (BRAIN_IDS.includes(b.id)) fireBurst(6);
      continue;
    }
    const [ax, ay] = ends(P.a[i], b);
    ctrl(ax, ay, b.cx, b.cy, P.s[i]);
    const qx = Q[0], qy = Q[1];
    for (let j = 7; j >= 0; j--) {     // a short fading tail behind the head
      const v = u - j * 0.035;
      if (v < 0) continue;
      const m = 1 - v, x = m * m * ax + 2 * m * v * qx + v * v * b.cx, y = m * m * ay + 2 * m * v * qy + v * v * b.cy;
      glow(P.c[i], x, y, j ? 14 - j : 22, j ? 0.55 * (1 - j / 8) : 1);
    }
  }
  cx.globalCompositeOperation = "source-over"; cx.globalAlpha = 1;
}

// ---------- the brain: a 3D point cloud of two hemispheres ----------
let BN = 0, BX, BYp, BZ, BIN, FIRE, NB, SX, SY, SZ;
function rng(seed) { return () => { seed = (seed + 0x6D2B79F5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
function makeBrain(n) {
  if (n === BN) return;
  BN = n; BX = new Float32Array(n); BYp = new Float32Array(n); BZ = new Float32Array(n); BIN = new Uint8Array(n);
  FIRE = new Float32Array(n); NB = new Int16Array(n * 3); SX = new Float32Array(n); SY = new Float32Array(n); SZ = new Float32Array(n);
  const r = rng(1987);
  for (let i = 0; i < n; i++) {
    const side = i % 2 ? 1 : -1;
    const uz = r() * 2 - 1, a = r() * Math.PI * 2, q = Math.sqrt(1 - uz * uz);
    let ux = Math.cos(a) * q, uy = Math.sin(a) * q;
    const inner = r() < 0.2 ? 0.35 + r() * 0.5 : 1;          // a fifth are neurons inside the brain
    BIN[i] = inner < 1 ? 1 : 0;
    // folds (sulci): a gentle ripple over the surface
    const fold = 1 + 0.07 * Math.sin(9 * ux + 5 * uz) * Math.cos(8 * uy + 3 * uz) + 0.03 * Math.sin(17 * uz + 4 * uy);
    let x = 0.22 * ux * fold * inner, y = 0.4 * uy * fold * inner, z = 0.58 * uz * fold * inner;
    if (side * ux < 0) x *= 0.8;                  // flat inner face: a narrow gap between the hemispheres
    if (uy < 0) y *= 0.72;                        // flatter underside
    if (uz > 0.3 && uy < 0) y -= 0.08 * (uz - 0.3); // temporal lobe hangs a little
    BX[i] = side * 0.205 + x; BYp[i] = y + 0.04; BZ[i] = z;
  }
  for (let i = 0; i < n; i++) {                    // the three nearest neighbours: synapses when a neuron fires
    let d0 = 9, d1 = 9, d2 = 9, j0 = i, j1 = i, j2 = i;
    for (let j = 0; j < n; j++) {
      if (j === i) continue;
      const dx = BX[i] - BX[j], dy = BYp[i] - BYp[j], dz = BZ[i] - BZ[j], d = dx * dx + dy * dy + dz * dz;
      if (d < d2) {
        if (d < d0) { d2 = d1; j2 = j1; d1 = d0; j1 = j0; d0 = d; j0 = j; }
        else if (d < d1) { d2 = d1; j2 = j1; d1 = d; j1 = j; }
        else { d2 = d; j2 = j; }
      }
    }
    NB[i * 3] = j0; NB[i * 3 + 1] = j1; NB[i * 3 + 2] = j2;
  }
}
let fireRand = rng(42);
function fireBurst(k) {
  if (paused || !BN) return;
  for (let m = 0; m < k; m++) { const i = (fireRand() * BN) | 0; FIRE[i] = 1; for (let q = 0; q < 3; q++) FIRE[NB[i * 3 + q]] = Math.max(FIRE[NB[i * 3 + q]], 0.6); }
}
function drawBrain(t, dt, tm, st, base) {
  if (!CORE) return;
  const ox = CORE.x, oy = CORE.y;
  let brainBusy = 0;
  for (const id of BRAIN_IDS) if ((st[id] || {}).status === "working") brainBusy++;
  const coreFlash = Math.max(0, 1 - (tm - CORE.flashT) / 900);
  const pulse = Math.max(0, 1 - (tm - lastPulse) / 900);
  const breath = paused ? 1 : 1 + 0.018 * Math.sin(t * 1.1);
  const S = R / (phone() ? 0.64 : 0.56) * breath * (1 + pulse * 0.03);
  // a soft halo in the nervous state's colour
  const g = cx.createRadialGradient(ox, oy, R * 0.1, ox, oy, R * 1.7);
  g.addColorStop(0, `rgba(${base},${0.16 + pulse * 0.12 + coreFlash * 0.12 + brainBusy * 0.04})`); g.addColorStop(1, "rgba(0,0,0,0)");
  cx.fillStyle = g; cx.beginPath(); cx.arc(ox, oy, R * 1.7, 0, 7); cx.fill();
  // random firing only in proportion to the brain agents that really work right now
  if (!paused && brainBusy) {
    let want = brainBusy * 7 * dt;
    while (want > 0) { if (fireRand() < want) fireBurst(1); want -= 1; }
  }
  const decay = Math.exp(-dt / 0.38);
  const rot = t * (0.16 + brainBusy * 0.05), cr = Math.cos(rot), sr = Math.sin(rot);
  const tl = -0.32, ct = Math.cos(tl), stl = Math.sin(tl), f = 2.6;
  cx.fillStyle = `rgb(${base})`;
  for (let i = 0; i < BN; i++) {
    const x0 = BX[i] * cr + BZ[i] * sr, z0 = -BX[i] * sr + BZ[i] * cr;
    const y = BYp[i] * ct - z0 * stl, z = BYp[i] * stl + z0 * ct;
    const k = f / (f + z);
    SX[i] = ox + x0 * S * k; SY[i] = oy - y * S * k; SZ[i] = z;
    const a = (BIN[i] ? 0.22 : 0.2 + 0.62 * (0.6 - z) / 1.2) * (0.85 + coreFlash * 0.3);
    const sz = (BIN[i] ? 1.1 : 1.0 + 1.1 * (0.6 - z) / 1.2) * k;
    cx.globalAlpha = Math.min(1, a);
    cx.fillRect(SX[i] - sz / 2, SY[i] - sz / 2, sz, sz);
    FIRE[i] *= decay;
  }
  // fired neurons: bright points and short synapses to their neighbours
  cx.globalCompositeOperation = "lighter";
  cx.strokeStyle = "rgb(190,235,255)"; cx.lineWidth = 0.8;
  for (let i = 0; i < BN; i++) {
    const fr = FIRE[i];
    if (fr < 0.05) continue;
    cx.globalAlpha = fr * 0.7;
    cx.beginPath();
    for (let q = 0; q < 3; q++) { const j = NB[i * 3 + q]; cx.moveTo(SX[i], SY[i]); cx.lineTo(SX[j], SY[j]); }
    cx.stroke();
    glow(1, SX[i], SY[i], 6 + fr * 10, fr);
  }
  cx.globalCompositeOperation = "source-over"; cx.globalAlpha = 1;
  // the orchestrator's name under the brain
  const so = st.orch || { status: "waiting" };
  cx.textAlign = "center"; cx.font = FONT_NAME; cx.fillStyle = "#e8eefc";
  cx.fillText(CORE.l1[0], ox, oy + R * 1.12);
  cx.font = FONT_SUB; cx.fillStyle = CORE.l2c; cx.fillText(CORE.l2, ox, oy + R * 1.12 + 13);
  if (so.status === "error") { cx.fillStyle = COLOR.error; cx.beginPath(); cx.arc(ox + R * 0.9, oy - R * 0.8, 5, 0, 7); cx.fill(); }
}

// ---------- the bots ----------
const TAU = Math.PI * 2;
function glyph(kind, x, y, r) {
  cx.beginPath();
  if (kind === "eyes") {              // an eye
    cx.moveTo(x - r, y); cx.quadraticCurveTo(x, y - r * 0.95, x + r, y); cx.quadraticCurveTo(x, y + r * 0.95, x - r, y);
    cx.stroke(); cx.beginPath(); cx.arc(x, y, r * 0.32, 0, TAU); cx.fill();
  } else if (kind === "nerves") {     // a bolt
    cx.moveTo(x + r * 0.25, y - r); cx.lineTo(x - r * 0.45, y + r * 0.1); cx.lineTo(x + r * 0.05, y + r * 0.1);
    cx.lineTo(x - r * 0.25, y + r); cx.lineTo(x + r * 0.5, y - r * 0.15); cx.lineTo(x, y - r * 0.15); cx.closePath(); cx.fill();
  } else if (kind === "brain") {      // two hemispheres with a fold
    cx.arc(x - r * 0.38, y, r * 0.55, Math.PI * 0.5, Math.PI * 1.5); cx.lineTo(x - r * 0.05, y - r * 0.55);
    cx.moveTo(x + r * 0.05, y - r * 0.55); cx.arc(x + r * 0.38, y, r * 0.55, -Math.PI * 0.5, Math.PI * 0.5); cx.lineTo(x + r * 0.05, y + r * 0.55);
    cx.moveTo(x - r * 0.05, y + r * 0.55); cx.lineTo(x - r * 0.38, y + r * 0.55);
    cx.moveTo(x, y - r * 0.6); cx.lineTo(x, y + r * 0.6);
    cx.moveTo(x - r * 0.6, y - r * 0.05); cx.quadraticCurveTo(x - r * 0.35, y + r * 0.2, x - r * 0.15, y - r * 0.1);
    cx.moveTo(x + r * 0.6, y + r * 0.05); cx.quadraticCurveTo(x + r * 0.35, y - r * 0.2, x + r * 0.15, y + r * 0.1);
    cx.stroke();
  } else if (kind === "judge") {      // scales
    cx.moveTo(x, y - r * 0.85); cx.lineTo(x, y + r * 0.75); cx.moveTo(x - r * 0.45, y + r * 0.75); cx.lineTo(x + r * 0.45, y + r * 0.75);
    cx.moveTo(x - r * 0.85, y - r * 0.55); cx.lineTo(x + r * 0.85, y - r * 0.55);
    cx.moveTo(x - r * 0.85, y - r * 0.55); cx.lineTo(x - r * 1.0, y + r * 0.1); cx.lineTo(x - r * 0.6, y + r * 0.1); cx.closePath();
    cx.moveTo(x + r * 0.85, y - r * 0.55); cx.lineTo(x + r * 1.0, y + r * 0.1); cx.lineTo(x + r * 0.6, y + r * 0.1); cx.closePath();
    cx.stroke();
  } else {                            // a shield with a check
    cx.moveTo(x, y - r); cx.lineTo(x + r * 0.8, y - r * 0.6); cx.quadraticCurveTo(x + r * 0.75, y + r * 0.55, x, y + r);
    cx.quadraticCurveTo(x - r * 0.75, y + r * 0.55, x - r * 0.8, y - r * 0.6); cx.closePath(); cx.stroke();
    cx.beginPath(); cx.moveTo(x - r * 0.35, y); cx.lineTo(x - r * 0.05, y + r * 0.32); cx.lineTo(x + r * 0.4, y - r * 0.3); cx.stroke();
  }
}
function drawBot(b, s, t, tm) {
  const x = b.cx, y = b.cy, r = b.r, ci = SIDX[s.status] ?? 0, col = COLOR[s.status] || COLOR.waiting;
  const flash = Math.max(0, 1 - (tm - b.flashT) / 850);
  cx.globalCompositeOperation = "lighter";
  if (s.status === "working") glow(1, x, y, r * 4.2 * (paused ? 1 : 0.92 + 0.12 * Math.sin(t * 4 + b.ph)), 0.32);
  if (s.status === "error") glow(3, x, y, r * 3.6, 0.3);
  if (flash) glow(b.flashC, x, y, r * (3 + 3 * flash), flash * 0.9);
  cx.globalCompositeOperation = "source-over"; cx.globalAlpha = 1;
  cx.fillStyle = "rgba(9,16,32,.94)"; cx.beginPath(); cx.arc(x, y, r, 0, TAU); cx.fill();
  cx.lineWidth = 1.4; cx.strokeStyle = col; cx.globalAlpha = s.status === "waiting" ? 0.45 : 0.9;
  cx.beginPath(); cx.arc(x, y, r, 0, TAU); cx.stroke();
  cx.globalAlpha = 1;
  if (s.status === "working") {       // progress arc when the agent says how far it is; else a spinning segment
    cx.lineWidth = 2.4; cx.strokeStyle = COLOR.working; cx.lineCap = "round"; cx.beginPath();
    if (s.progress != null) cx.arc(x, y, r + 3.5, -Math.PI / 2, -Math.PI / 2 + TAU * Math.max(0.02, s.progress));
    else { const a = paused ? 0 : t * 3.2 + b.ph; cx.arc(x, y, r + 3.5, a, a + 1.4); }
    cx.stroke(); cx.lineCap = "butt";
  } else if (b.fresh) {
    cx.lineWidth = 1.6; cx.strokeStyle = COLOR.done; cx.globalAlpha = 0.7; cx.beginPath(); cx.arc(x, y, r + 3.5, 0, TAU); cx.stroke(); cx.globalAlpha = 1;
  }
  cx.strokeStyle = cx.fillStyle = s.status === "waiting" ? "#8a97b4" : col;
  cx.lineWidth = 1.3; cx.lineJoin = "round";
  glyph(LANES[b.lane].key, x, y, r * 0.52);
  if (s.status === "error") {         // a steady red badge (no blinking)
    cx.fillStyle = COLOR.error; cx.beginPath(); cx.arc(x + r * 0.78, y - r * 0.78, 5, 0, TAU); cx.fill();
    cx.fillStyle = "#fff"; cx.font = "800 8px Inter,system-ui,sans-serif"; cx.textAlign = "center"; cx.fillText("!", x + r * 0.78, y - r * 0.78 + 3);
  }
  // name and the current line
  cx.textAlign = "center"; cx.font = FONT_NAME; cx.fillStyle = s.status === "waiting" ? "#c3cde3" : "#e8eefc";
  let ly = y + r + 14;
  for (const line of b.l1) { cx.fillText(line, x, ly); ly += 12; }
  cx.font = FONT_SUB; cx.fillStyle = b.l2c; cx.globalAlpha = s.status === "waiting" ? 0.7 : 1;
  cx.fillText(b.l2, x, ly); cx.globalAlpha = 1;
  void ci;
}

// ---------- the frame loop (one requestAnimationFrame for the stage and the timeline) ----------
let prevTm = 0;
function draw(tms) {
  const ph = phone();
  const w = cv.clientWidth, h0 = cv.clientHeight, dpr = devicePixelRatio || 1;
  const key = `${w}x${ph ? "p" : h0}x${BOTS.length}`;
  if (BOTS.length && key !== layoutKey) {
    layoutKey = key;
    layout(w, h0);
    if (ph) cv.style.height = H + "px"; else cv.style.height = "";
    placeHits();
  }
  const h = ph ? H : h0;
  if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
  cx.setTransform(dpr, 0, 0, dpr, 0, 0);
  cx.clearRect(0, 0, w, h);
  const dt = Math.min(0.1, Math.max(0, (tms - prevTm) / 1000)); prevTm = tms;
  if (!paused) frozenT = tms;
  const t = frozenT / 1000, st = curState();
  const err = (st.orch || {}).status === "error";     // red only when the main loop itself fails; others show on their cards
  const base = err || nerveState === "HƏYƏCAN" ? "255,93,108" : nerveState === "DİQQƏT" ? "232,185,74" : "56,200,255";
  // gentle idle float: agents look alive even when calm (frozen under reduced motion / pause)
  for (const b of BOTS) {
    if (b === CORE || paused) { b.cx = b.x; b.cy = b.y; continue; }
    b.cx = b.x + Math.sin(t * 0.55 + b.ph) * 2.2; b.cy = b.y + Math.cos(t * 0.43 + b.ph * 1.3) * 2.6;
  }
  // lanes: subtle names and separators
  cx.textAlign = ph ? "left" : "center"; cx.font = "700 10px Inter,system-ui,sans-serif";
  for (let i = 0; i < lanesGeo.length; i++) {
    const L = lanesGeo[i];
    cx.fillStyle = "rgba(138,151,180,.55)";
    cx.fillText(L.name.toUpperCase().split("").join(" "), L.x, L.y);
    cx.fillStyle = "rgba(120,170,255,.06)";
    if (!ph && i) cx.fillRect(L.x0, 56, 1, h - 70);
    if (ph && i) cx.fillRect(0, L.y0, w, 1);
  }
  // fibres along the data flow: very dim when idle, brighter while the task works or a light just passed
  for (const f of FIB) {
    const b = f.b, s = (st[b.id] || {}).status || "waiting";
    const [ax, ay] = ends(f.a, b);
    ctrl(ax, ay, b.cx, b.cy, f.s);
    const g = Math.max(0, 1 - (tms - f.glowT) / 1400);
    let a = f.a ? 0.07 : 0.04, ci = 0;
    if (s === "working") { a = 0.2; ci = 1; }
    else if (s === "error") { a = 0.16; ci = 3; }
    if (g > 0) { a = Math.max(a, 0.12 + 0.5 * g); ci = f.glowC; }
    const [r0, g0, b0] = ci ? RGB[ci] : [120, 170, 255];
    cx.strokeStyle = `rgba(${r0},${g0},${b0},${a})`; cx.lineWidth = g > 0 ? 1 + g * 1.2 : 1;
    cx.beginPath(); cx.moveTo(ax, ay); cx.quadraticCurveTo(Q[0], Q[1], b.cx, b.cy); cx.stroke();
  }
  drawBrain(t, paused ? 0 : dt, tms, st, base);
  drawPulses(tms);
  for (const b of BOTS) if (b !== CORE) drawBot(b, st[b.id] || { status: "waiting" }, t, tms);
  if (mode === "replay") stepReplay();
  drawTimeline();
  requestAnimationFrame(draw);
}
document.addEventListener("visibilitychange", () => {
  if (document.hidden) return;
  P.on.fill(0); lastFrame = performance.now();     // lights that would have passed while hidden are not replayed late
});
addEventListener("resize", () => { layoutKey = ""; });

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
  while (idx < events.length && events[idx].ts <= playT) { const e = events[idx++]; apply(shown, e); spawn(e); changed = true; }
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

// ---------- side panels: market, risk gate, decision, event log ----------
const NAME = (id) => (NODES.find((n) => n.id === id) || { name: id }).name;
function logEvent(e) {
  const ul = $("log");
  if (!ul || e.task === "orch") return;            // the main loop beats every 15 s: not news
  const li = document.createElement("li");
  li.innerHTML = `<span style="color:${COLOR[e.status]}">●</span> ${ny(e.ts, true)} <b>${esc(NAME(e.task))}</b> ${WORD[e.status]}` +
    (e.stage || e.note ? ` · ${esc(e.stage || e.note)}` : "");
  ul.prepend(li);
  while (ul.children.length > 40) ul.lastChild.remove();
}
const MKT_SHOW = ["XAU", "XAG", "XPT", "XPD", "DXY", "US10Y", "OIL", "VIX"];
async function loadMarkets() {
  try {
    const r = await fetch("/api/markets?metal=XAU", { credentials: "same-origin" });
    if (!r.ok) return;
    const d = await r.json();
    $("mkts").innerHTML = d.markets.filter((m) => MKT_SHOW.includes(m.code)).map((m) => {
      const ch = m.price && m.day_open ? (m.price / m.day_open - 1) * 100 : null;
      const col = ch == null ? "var(--muted)" : ch >= 0 ? "var(--done)" : "var(--err)";
      return `<div class="mk"><b>${esc(m.name)}</b><span class="v">${m.price != null ? m.price.toFixed(m.price > 100 ? 2 : 3) : "—"}</span>
        <span class="s">${esc(m.status || "")} · <span style="color:${col}">${ch == null ? "—" : (ch >= 0 ? "+" : "") + ch.toFixed(2) + " %"}</span> gün</span></div>`;
    }).join("");
    showMetals(d.markets, Date.now() / 1000 + skew);
  } catch (e) { /* keep the last view */ }
}
// the four metals on the stage, next to the eyes: price from the market data provider only, its status when not
// LIVE, a short up/down colour tick when the price changed since the last check, and the check time (New York)
const METAL_CODES = ["XAU", "XAG", "XPT", "XPD"], lastPx = {}, tickT = {};
function showMetals(rows, ts) {
  const box = $("metals");
  if (!box) return;
  const by = Object.fromEntries(rows.map((m) => [m.code, m]));
  box.innerHTML = METAL_CODES.map((c) => {
    const m = by[c] || {}, p = m.price;
    let tick = "";
    if (p != null && lastPx[c] != null && p !== lastPx[c]) tickT[c] = [p > lastPx[c] ? "up" : "down", ts];
    if (p != null) lastPx[c] = p;
    if (tickT[c] && ts - tickT[c][1] < 15) tick = tickT[c][0];
    const stc = m.status || "OFFLINE";
    return `<span class="mt ${tick}" title="${esc(m.name || c)} · ${esc(stc)}"><b>${c}</b> <span class="v">${p != null ? p.toFixed(p > 100 ? 2 : 3) : "—"}</span>` +
      `<i aria-hidden="true">${tick === "up" ? "▲" : tick === "down" ? "▼" : ""}</i>` +
      `${stc !== "LIVE" ? `<span class="ms ${esc(stc)}">${esc(stc)}</span>` : ""}</span>`;
  }).join("") + `<span class="mtime">yoxlandı ${ny(ts, true)} NY</span>`;
  clearTimeout(showMetals.t);
  showMetals.t = setTimeout(() => box.querySelectorAll(".mt.up,.mt.down").forEach((x) => x.classList.add("fade")), 2500);
}
const DESK_SHOW = ["15m", "1h", "4h", "1d", "1w", "1mo"];
const SHORT = { "15m": "15d", "1h": "1s", "4h": "4s", "1d": "1g", "1w": "1h", "1mo": "1a" };
async function loadDecision() {
  try {
    const r = await fetch("/api/decision", { credentials: "same-origin" });
    if (!r.ok) return;
    const d = await r.json(), ms = d.metals || {};
    if (d.state) {
      nerveState = d.state.state || "SAKİT";
      const m = d.state.mod || {};
      $("nstate").className = "nstate " + nerveState;
      $("nstate").textContent = nerveState;
      $("nstate").title = `${d.state.why || ""} · oyanıqlıq ${m.arousal == null ? "—" : Math.round(m.arousal * 100) + " %"}` +
        ` · beyinlərin fikir ayrılığı ${m.uncertainty == null ? "—" : Math.round(m.uncertainty * 100) + " bənd"}`;
      if (nerveState === "HƏYƏCAN") lastPulse = performance.now();
    }
    const syms = Object.keys(ms);
    if (!syms.length) { $("decision").innerHTML = "<p class='note'>Hesablanır (dəqiqədə bir)…</p>"; return; }
    $("gates").innerHTML = syms.map((s) => {
      const g = ms[s].gate;
      return `<div class="gate ${g.open ? "open" : "shut"}" title="${esc((g.reasons || []).join("; "))}">${s}: ${g.open ? "açıq" : "bağlı — " + esc(g.reasons[0])}</div>`;
    }).join("");
    $("decision").innerHTML = `<table class="dec"><tr><th></th>${DESK_SHOW.map((h) => `<th title="${h}">${SHORT[h]}</th>`).join("")}</tr>` +
      syms.map((s) => `<tr><th>${s}</th>${DESK_SHOW.map((h) => {
        const x = ms[s].desks.find((k) => k.horizon === h) || {};
        return `<td class="${x.call || ""}" title="${esc(x.name || h)}: ${esc(x.why || "")}">${x.call === "GÖZLƏ" ? "·" : esc(x.call || "·")}</td>`;
      }).join("")}</tr>`).join("") + "</table><p class='note'>· = GÖZLƏ (sübut yoxdur və ya risk qapısı bağlıdır). Xanaya toxun: səbəb.</p>";
  } catch (e) { /* keep the last view */ }
}
$("pause").onclick = () => { paused = !paused; $("pause").textContent = paused ? "▶ Animasiya" : "⏸ Animasiya"; };
$("reset").onclick = () => {
  $("detail").classList.remove("open"); winH = 1;
  [...$("win").children].forEach((x) => x.classList.toggle("on", x.dataset.h === "1"));
  goLive();
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
      apply(live, d.event); events.push(d.event); logEvent(d.event);
      if (mode === "live") { lastPulse = performance.now(); spawn(d.event); render(); }
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
    events.slice(-30).forEach(logEvent);
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
setInterval(loadMarkets, 20000); setInterval(loadDecision, 30000);
loadMarkets(); loadDecision();
loadEvents().then(connect);
loadTop();
requestAnimationFrame(draw);
