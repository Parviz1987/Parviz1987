// Admin in five tabs (owner 2026-11-26: one panel instead of a long page). The tab is in the address (#sistem) so a
// link can open it, and remembered on this device.
(function () {
  "use strict";
  const tabs = [...document.querySelectorAll("#atabs [data-tab]")], panes = [...document.querySelectorAll(".atab")];
  const names = tabs.map((b) => b.dataset.tab);
  function show(t, push) {
    if (!names.includes(t)) t = names[0];
    tabs.forEach((b) => { const on = b.dataset.tab === t; b.classList.toggle("on", on); b.setAttribute("aria-selected", String(on)); });
    panes.forEach((p) => { p.hidden = p.dataset.tab !== t; });
    try { localStorage.setItem("tst_admin_tab", t); } catch (e) { /* fine */ }
    if (push && location.hash !== "#" + t) history.replaceState(null, "", "#" + t);
    window.dispatchEvent(new Event("resize"));      // charts in a tab that was hidden draw at their real size
  }
  tabs.forEach((b) => b.onclick = () => show(b.dataset.tab, true));
  window.addEventListener("hashchange", () => show(location.hash.slice(1), false));
  let start = location.hash.slice(1);
  if (!names.includes(start)) { try { start = localStorage.getItem("tst_admin_tab") || ""; } catch (e) { start = ""; } }
  show(start, false);
})();
