// Fold-able sections (one mechanism for every page; it lived in flow.js, the panel's and results' script, 27.11 moved
// here so the block pages can fold their long technical parts too — owner 2026-11-27: «texniki şeylər arxa planda»).
// A section with data-fold="key" gets a «Göstər / Gizlət» button in its heading; data-fold-default="closed" starts it
// folded. A folded section keeps its content; its state is remembered on this device.
(function () {
  "use strict";
  const KEY = "tst_fold";
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { saved = {}; }
  function setFold(box, folded) {
    box.classList.toggle("folded", folded);
    const b = box.querySelector(".foldbtn");
    if (b) { b.textContent = folded ? "Göstər ▾" : "Gizlət ▴"; b.setAttribute("aria-expanded", String(!folded)); }
    saved[box.dataset.fold] = folded;
    try { localStorage.setItem(KEY, JSON.stringify(saved)); } catch (e) { /* private window: fine */ }
    // charts inside redraw at their real size: «resize» for the charts that follow it, and «tst:unfold» for the pages
    // that redraw only on a real change of width (a phone fires «resize» while scrolling)
    if (!folded) { window.dispatchEvent(new Event("resize")); window.dispatchEvent(new Event("tst:unfold")); }
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

  // an opened <details> (the results page's technical group, «Ətraflı» inside a section) does the same
  document.querySelectorAll("details").forEach((d) => d.addEventListener("toggle", () => {
    if (d.open) { window.dispatchEvent(new Event("resize")); window.dispatchEvent(new Event("tst:unfold")); }
  }));
})();
