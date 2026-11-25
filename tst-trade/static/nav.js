// The same navigation on every page, in the same order; the page you are on is highlighted. A guest sees only the
// pages a guest may open (the server refuses the others anyway).
(function () {
  "use strict";
  const el = document.getElementById("mainnav");
  if (!el) return;
  const PAGES = [["/", "Panel"], ["/results", "Nəticələr"], ["/bloklar", "Bloklar"], ["/ta", "Texniki analiz"], ["/fundamental", "Fundamental"], ["/bilik", "Bilik"], ["/agents", "Agentlər"], ["/status", "Sistem"], ["/admin", "Admin"]];
  const OWNER_ONLY = ["/agents", "/status", "/admin"];
  const here = location.pathname.replace(/\/$/, "") || "/";
  el.innerHTML = PAGES.map(([href, name]) =>
    `<a href="${href}"${href === here ? ' class="on" aria-current="page"' : ""}>${name}</a>`).join("") +
    '<form method="post" action="/logout"><button type="submit" title="Hesabdan çıx">Çıxış</button></form>';
  fetch("/api/me", { credentials: "same-origin" }).then((r) => r.ok ? r.json() : null).then((m) => {
    if (m && m.role === "guest") el.querySelectorAll("a").forEach((a) => {
      if (OWNER_ONLY.includes(a.getAttribute("href"))) a.hidden = true;
    });
  }).catch(() => {});
})();
