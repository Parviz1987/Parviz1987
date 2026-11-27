// Panel additions (owner's request 2026-11-24, Radar Gold look): the strip of every market our analysis reads, the
// live flow of the whole system (eyes -> nerves -> brains -> judge -> decision), and fold-able sections so the page
// stays short without losing anything (a folded section keeps its content; its state is remembered on this device).
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const get = (url) => fetch(url, { credentials: "same-origin" }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  const fmt = (v) => (v == null ? "—" : v >= 1000 ? v.toFixed(1) : v >= 100 ? v.toFixed(2) : v.toFixed(3));

  // ---------- 1. markets strip ----------
  async function loadTicker() {
    const d = await get("/api/ticker");
    if (!d || !$("ticker")) return;
    const chips = d.markets.map((m) => {
      const ch = m.price != null && m.day_open ? (m.price / m.day_open - 1) * 100 : null;
      const cls = ch == null ? "mut" : ch >= 0 ? "up" : "down";
      return `<a class="tk" href="/bazarlar" title="${esc(m.name)} · ${esc(m.status)}${m.kind === "ETF" ? " · ETF (yalnız ABŞ saatları)" : ""}">
        <span class="n">${esc(m.name)}</span><span class="v">${fmt(m.price)}</span>
        <span class="${cls}">${ch == null ? "—" : (ch >= 0 ? "+" : "") + ch.toFixed(2) + "%"}</span></a>`;
    });
    if (d.fed && d.fed.length) {
      const f = d.fed[0];
      chips.push(`<span class="tk fed" title="${esc(d.fed.map((x) => x.title + ": " + Math.round(x.prob * 100) + " %").join("\n"))}">
        <span class="n">Fed (Kalshi)</span><span class="v">${Math.round(f.prob * 100)} %</span><span class="mut">${esc((f.title || "").slice(0, 28))}</span></span>`);
    }
    $("ticker").innerHTML = chips.join("");
  }

  // ---------- 2. live system flow ----------
  const STAGES = [
    { name: "Gözlər", what: "qiymət, bazarlar, xəbər, təqvim, makro, X", ids: ["prices", "liquidity", "news", "calendar", "macro", "scout", "history"] },
    { name: "Sinirlər", what: "güclü xəbər, rəqəm, sıçrayış, proqnoz xətası", ids: ["signals"] },
    { name: "Beyinlər", what: "Oxuyucu, Strateq, müzakirə, rəqəm ovçusu", ids: ["reader", "strateq", "debate", "hunter"] },
    { name: "Hakim", what: "proqnozlar və yoxlama", ids: ["forecast", "judge"] },
    { name: "Qərar", what: "risk qapısı, AL / SAT / GÖZLƏ", ids: ["risk", "decision"] },
  ];
  const WORD = { waiting: "gözləyir", working: "işləyir", done: "bitdi", error: "xəta" };
  async function loadFlow() {
    const d = await get("/api/agents/state");
    const el = $("flow");
    if (!el) return;
    if (!d) { el.hidden = true; return; }               // a guest does not see the system's inside
    el.hidden = false;
    const now = d.now, st = d.state;
    el.innerHTML = STAGES.map((s, i) => {
      const xs = s.ids.map((id) => st[id]).filter(Boolean);
      const status = xs.some((x) => x.status === "error") ? "error" : xs.some((x) => x.status === "working") ? "working"
        : xs.some((x) => x.status === "done") ? "done" : "waiting";
      const last = xs.filter((x) => x.ts).sort((a, b) => b.ts - a.ts)[0];
      const fresh = last && now - last.ts < 20;
      const ago = last ? Math.round((now - last.ts) / 60) : null;
      const note = last ? (last.stage || last.note || "") : s.what;
      return `${i ? `<span class="fl-link${fresh ? " on" : ""}" aria-hidden="true"></span>` : ""}
        <a class="fl ${status}${fresh ? " fresh" : ""}" href="/agents" title="${esc(s.what)}">
          <span class="fl-h"><i></i>${esc(s.name)}<em>${WORD[status]}</em></span>
          <span class="fl-n">${esc(note).slice(0, 60)}${ago != null ? ` · ${ago ? ago + " dəq əvvəl" : "indi"}` : ""}</span></a>`;
    }).join("");
  }

  // ---------- 3. fold-able sections ----------
  const KEY = "tst_fold";
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { saved = {}; }
  function setFold(box, folded) {
    box.classList.toggle("folded", folded);
    const b = box.querySelector(".foldbtn");
    if (b) { b.textContent = folded ? "Göstər ▾" : "Gizlət ▴"; b.setAttribute("aria-expanded", String(!folded)); }
    saved[box.dataset.fold] = folded;
    try { localStorage.setItem(KEY, JSON.stringify(saved)); } catch (e) { /* private window: fine */ }
    if (!folded) window.dispatchEvent(new Event("resize"));       // charts inside redraw at their real size
  }
  document.querySelectorAll(".box[data-fold]").forEach((box) => {
    const h = box.querySelector("h2");
    if (!h) return;
    const b = document.createElement("button");
    b.type = "button"; b.className = "foldbtn";
    b.onclick = () => setFold(box, !box.classList.contains("folded"));
    h.appendChild(b);
    const def = box.dataset.foldDefault === "closed";
    setFold(box, saved[box.dataset.fold] ?? def);
  });
  // a jump link (phone) or a strip chip opens its folded section
  document.addEventListener("click", (ev) => {
    const a = ev.target.closest('a[href^="#"]');
    if (!a) return;
    const box = document.querySelector(a.getAttribute("href"));
    const holder = box && (box.matches(".box[data-fold]") ? box : box.closest(".box[data-fold]"));
    if (holder && holder.classList.contains("folded")) setFold(holder, false);
  });

  loadTicker(); loadFlow();
  setInterval(loadTicker, 20000);
  setInterval(loadFlow, 5000);
})();
