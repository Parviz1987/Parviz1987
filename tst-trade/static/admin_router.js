// Beyinlərin vəziyyəti: söndürülmüş və soyuyan modellər (səbəbi və sizin addımınız), şirkətin təklif etdiyi yeni
// modellər (Təsdiqlə / Rədd et), son 24 saatda hər yuvada ehtiyat beyinin cavab payı.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  async function call(method, body) {
    const r = await fetch("/api/admin/router", { method, credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || "xəta");
    return d;
  }
  async function act(action, provider, model) {
    try { $("rt-msg").textContent = (await call("POST", { action, provider, model })).note; } catch (e) { $("rt-msg").textContent = e.message; }
    load();
  }
  function render(v) {
    const models = (v.models || []).map((m) => `<tr><td>${esc(m.provider)} · ${esc(m.model)}</td><td>${esc(m.state)}</td>
      <td><button class="btn" data-a="reset" data-p="${esc(m.provider)}" data-m="${esc(m.model)}">Yenidən sına</button></td></tr>`).join("");
    const props = Object.values(v.proposals || {}).map((p) => {
      const open = String(p.status || "").startsWith("sahibin");
      return `<tr><td>${esc(p.provider)}: ${esc(p.old)} → <b>${esc(p.new)}</b></td><td>${esc(p.status)}</td><td>${open ?
        `<button class="btn pri" data-a="approve" data-p="${esc(p.provider)}" data-m="${esc(p.old)}">Təsdiqlə</button>
         <button class="btn dan" data-a="reject" data-p="${esc(p.provider)}" data-m="${esc(p.old)}">Rədd et</button>` : ""}</td></tr>`;
    }).join("");
    const slots = Object.entries(v.slots_24h || {}).map(([k, s]) => `<tr><td>${esc(k)}</td><td>${s.ok}</td><td>${s.error}</td>
      <td>${s.fallback_rate == null ? "—" : Math.round(s.fallback_rate * 100) + " %"}${s.alert ? " ⚠️" : ""}</td></tr>`).join("");
    $("rt-box").innerHTML =
      (models ? `<table><tr><th>Model</th><th>Vəziyyət</th><th></th></tr>${models}</table>` : `<p class="note">✅ Bütün modellər işləyir.</p>`) +
      (props ? `<h3>Yeni model təklifləri</h3><table><tr><th>Təklif</th><th>Vəziyyət</th><th></th></tr>${props}</table>` : "") +
      (slots ? `<h3>Son 24 saat</h3><table><tr><th>Yuva</th><th>Cavab</th><th>Xəta</th><th>Ehtiyat payı</th></tr>${slots}</table>` : "");
    $("rt-box").querySelectorAll("button[data-a]").forEach((b) => { b.onclick = () => act(b.dataset.a, b.dataset.p, b.dataset.m); });
  }
  async function load() { try { render(await call("GET")); } catch (e) { /* other sections still work */ } }
  load();
})();
