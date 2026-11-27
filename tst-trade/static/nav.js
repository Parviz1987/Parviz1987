// The same navigation on every page (owner 2026-11-26: fewer buttons, related pages together). Left: the four main
// places; right: the owner's own tools and the admin. The six block pages live under «Bloklar» and get a second row
// with their names, so «Bloklar» stays highlighted on each of them. A guest sees only the pages a guest may open (the
// server refuses the others anyway).
(function () {
  "use strict";
  const el = document.getElementById("mainnav");
  if (!el) return;
  const MAIN = [["/", "Panel"], ["/results", "Nəticələr"], ["/bloklar", "Bloklar"], ["/agents", "Agentlər"]];
  const RIGHT = [["/ehtiyat", "Ehtiyat"], ["/admin", "⚙ Admin"]];      // «Sistem» is the admin's «Sistem» tab now
  const BLOCKS = [["/bloklar", "Ümumi"], ["/ta", "Texniki analiz"], ["/fundamental", "Fundamental"], ["/xeber", "Xəbər"],
    ["/bazarlar", "Bazarlar arası"], ["/vaxt", "Vaxt və təqvim"], ["/bilik", "Bilik kitabı"]];
  const OWNER_ONLY = ["/agents", "/status", "/admin", "/ehtiyat"];
  const here = location.pathname.replace(/\/$/, "") || "/";
  const inBlocks = BLOCKS.some(([h]) => h === here);
  const link = ([href, name], on) => `<a href="${href}"${on ? ' class="on" aria-current="page"' : ""}>${name}</a>`;
  el.innerHTML = MAIN.map((p) => link(p, p[0] === here || (p[0] === "/bloklar" && inBlocks))).join("") +
    '<span class="nsp"></span>' + RIGHT.map((p) => link(p, p[0] === here)).join("") +
    '<form method="post" action="/logout"><button type="submit" title="Hesabdan çıx">Çıxış</button></form>';
  if (inBlocks) {
    const sub = document.createElement("nav");
    sub.className = "subnav"; sub.setAttribute("aria-label", "Bloklar");
    sub.innerHTML = BLOCKS.map((p) => link(p, p[0] === here)).join("");
    const head = el.closest("header");
    if (head) head.after(sub); else el.after(sub);
  }
  fetch("/api/me", { credentials: "same-origin" }).then((r) => r.ok ? r.json() : null).then((m) => {
    if (m && m.role === "guest") el.querySelectorAll("a").forEach((a) => {
      if (OWNER_ONLY.includes(a.getAttribute("href"))) a.hidden = true;
    });
  }).catch(() => {});
})();
