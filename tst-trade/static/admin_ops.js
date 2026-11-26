// Avtomatik təmirin «Dayandır» düyməsi və kənar nəzarətçinin (Healthchecks.io) vəziyyəti. Ping ünvanları və açar
// heç vaxt brauzerə gəlmir: yalnız «quruldu mu» və hər yoxlamanın son siqnalı.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const NAMES = {
    "app-alive": "Panel və təzə qiymət", "price-feed": "4 metalın qiyməti", "rule-blocks": "Qayda blokları",
    "news-agents": "Xəbər mənbələri", "ai-brains": "AI beyinləri", "unified-forecast": "Vahid proqnoz",
    "judge-scoring": "Hakim", "learning-nightly": "Gecə öyrənməsi", "hypothesis-weekly": "Həftəlik hipotez",
    "duty-check": "Növbətçi Claude", "backup-nightly": "Gecəlik ehtiyat nüsxə", "deploy": "Yeni versiya"
  };
  async function call(method, body) {
    const r = await fetch("/api/admin/ops", { method, credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || "xəta");
    return d;
  }
  const when = (ts) => ts ? new Date(ts * 1000).toLocaleString("az-Latn-AZ", { timeZone: "America/New_York", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) + " (NY)" : "—";
  function render(st) {
    $("ops-state").innerHTML = st.paused ? `<b>⏸ Avtomatik təmir dayandırılıb</b> (${esc(when(st.since))}).` : "<b>▶ Avtomatik təmir işləyir</b> (yalnız icazəli addımlar).";
    $("ops-btn").textContent = st.paused ? "Davam etsin" : "Avtomatik təmiri dayandır";
    $("ops-btn").className = st.paused ? "btn pri" : "btn dan";
    $("ops-btn").onclick = async () => {
      try { render({ ...(await call("POST", { paused: !st.paused })), watcher: st.watcher }); $("ops-msg").textContent = ""; }
      catch (e) { $("ops-msg").textContent = e.message; }
    };
    const w = st.watcher || {};
    const setup = w.setup || {};
    const head = !w.key ? "<p class=\"note\">Healthchecks.io açarı hələ saxlanmayıb (yuxarıda «Nəzarət: kənar izləmə»).</p>" :
      `<p class="note">${setup.ok ? "✅" : "⚠️"} ${esc(setup.note || "qurulur…")}</p>`;
    const rows = (w.checks || []).map((c) => {
      const l = c.last || {};
      const st2 = !l.ts ? "—" : l.state === "fail" ? "❌ xəta" : l.delivered ? "✅" : "⏳ göndərilmədi";
      return `<tr><td>${esc(NAMES[c.id] || c.id)}${c.urgent ? " <b>(təcili)</b>" : ""}</td><td>${st2}</td><td>${esc(when(l.ts))}</td><td>${esc(l.msg || "")}</td></tr>`;
    }).join("");
    $("ops-watch").innerHTML = head + (w.key ? `<table><tr><th>Yoxlama</th><th>Son siqnal</th><th>Vaxt</th><th>Qeyd</th></tr>${rows}</table>` : "");
  }
  async function load() {
    try { render(await call("GET")); } catch (e) { /* the admin page shows other sections anyway */ }
  }
  load();
  setInterval(load, 60000);
})();
