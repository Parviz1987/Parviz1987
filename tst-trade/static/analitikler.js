// The record book (owner 2026-11-27: «Əhməd qızılda düz deyir, gümüşdə səhv — Əhmədin qızılını gətirmək olar,
// gümüşünü yox; jurnalda kim harada nə deyib, düz deyib, düz ardıcıllığı»). Rows: the analysts; columns: the four
// metals; a cell: right / checked, the latest ten results and the current run. A click opens the journal of that
// analyst in that metal: what it said, when, why, the price then and after, and whether it came true.
// Plain counts only (the owner: «sadəcə qeydlər apar»); proof with cost and many tests stays on «Nəticələr».
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const METALS = [["XAU", "Qızıl"], ["XAG", "Gümüş"], ["XPT", "Platin"], ["XPD", "Palladium"]];
  const MNAME = Object.fromEntries(METALS);
  const HS = { all: "Hamısı", "15m": "15 dəq", "30m": "30 dəq", "1h": "1 saat", "4h": "4 saat", "1d": "1 gün", "3d": "3 gün",
    "1w": "1 həftə", "10d": "10 gün", "1mo": "1 ay" };
  const DAYS = [["", "Bu günə kimi"], ["30", "30 gün"], ["7", "7 gün"], ["1", "24 saat"]];
  const ENOUGH = 20;                  // fewer checked calls than this: the cell is grey («hələ az»)
  const GOOD = 0.55, BAD = 0.45;      // the colour of a cell with enough calls: right at least 55 % green, at most 45 % red
  const OWN = { consensus: "sistemin ümumi fikri", vahid: "sistemin ümumi fikri", terazi: "sistemin ümumi fikri",
    garch: "dəyişkənlik", gvz: "dəyişkənlik", up: "müqayisə üçün" };
  const NY = { timeZone: "America/New_York" };
  const dt = (ts) => new Date(ts * 1000).toLocaleString("az", { ...NY, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  const pc = (x) => Math.round(x * 100) + " %";
  const price = (x) => x == null ? "—" : x >= 100 ? x.toFixed(2) : x.toFixed(3);
  let hz = "all", days = "", sortBy = "XAU", data = null, open = null;
  try { hz = localStorage.getItem("tst_anl_h") || hz; days = localStorage.getItem("tst_anl_d") ?? days; sortBy = localStorage.getItem("tst_anl_s") || sortBy; } catch (e) {}
  const keep = () => { try { localStorage.setItem("tst_anl_h", hz); localStorage.setItem("tst_anl_d", days); localStorage.setItem("tst_anl_s", sortBy); } catch (e) {} };

  async function api(path) {
    const r = await fetch(path, { credentials: "same-origin" });
    if (r.status === 401) { location.href = "/login"; throw new Error("login"); }
    if (!r.ok) throw new Error(path + " " + r.status);
    return r.json();
  }
  const dots = (last) => `<span class="dots" aria-label="son nəticələr">${[...(last || "")].map((x) => `<i class="${x === "1" ? "y" : "n"}"></i>`).join("")}</span>`;
  const run = (k) => k >= 2 ? `<span class="up">son ${k} düz</span>` : k <= -2 ? `<span class="down">son ${-k} səhv</span>` : "";
  const full = (m) => m === "up" ? "Həmişə «qalxacaq» desən" : (data.names[m] || m);
  const short = (m) => full(m).split(" (")[0];
  const sub = (m) => { const x = full(m).split(" (")[1]; return x ? x.replace(/\)$/, "") : OWN[m] || data.families[data.family[m]] || ""; };
  const cellOf = (m, s) => ((data.methods[m] || {})[s] || {})[hz];
  const share = (c) => c && c.n ? c.right / c.n : null;
  const tone = (c) => !c || !c.n ? "" : c.n < ENOUGH ? "few" : share(c) >= GOOD ? "good" : share(c) <= BAD ? "bad" : "";

  function segs() {
    const have = new Set(["all"]);
    Object.values(data.methods).forEach((per) => Object.values(per).forEach((cells) => Object.keys(cells).forEach((h) => have.add(h))));
    if (!have.has(hz)) hz = "all";
    const draw = (id, items, cur, set) => {
      $(id).innerHTML = items.map(([k, n]) => `<button type="button" data-k="${k}" class="${k === cur ? "on" : ""}">${n}</button>`).join("");
      $(id).querySelectorAll("button").forEach((b) => b.onclick = () => { set(b.dataset.k); keep(); load(); });
    };
    draw("ah", Object.keys(HS).filter((h) => have.has(h)).map((h) => [h, HS[h]]), hz, (k) => { hz = k; });
    draw("ad", DAYS, days, (k) => { days = k; });
    $("am").innerHTML = METALS.map(([k, n]) => `<button type="button" data-k="${k}" class="${k === sortBy ? "on" : ""}">${n}</button>`).join("");
    $("am").querySelectorAll("button").forEach((b) => b.onclick = () => { sortBy = b.dataset.k; keep(); render(); });
  }

  function cell(m, s) {
    const c = cellOf(m, s);
    const col = s === sortBy ? " sel" : "";
    if (!c || !c.n) return `<td class="ac mut${col}">·</td>`;
    const t = tone(c);
    return `<td class="ac ${t}${col}" data-m="${m}" data-s="${s}" tabindex="0" role="button"
      title="${esc(full(m))} · ${MNAME[s]}: ${c.n} fikirdən ${c.right} düz, ${c.n - c.right} səhv${c.n < ENOUGH ? " (hələ az)" : ""}">
      <b>${pc(share(c))}</b><span class="cnt">${c.right} / ${c.n}</span>${dots(c.last)}<span class="run">${run(c.streak)}</span></td>`;
  }

  function table(ms) {
    if (!ms.length) return "<p class='note'>Bu dövrdə yoxlanmış fikir yoxdur.</p>";
    return `<table class="sc anl-t"><tr><th>Analitik</th>${METALS.map(([s, n]) =>
      `<th class="c${s === sortBy ? " sel" : ""}"><button type="button" class="srt${s === sortBy ? " on" : ""}" data-s="${s}">${n}${s === sortBy ? " ▾" : ""}</button></th>`).join("")}</tr>` +
      ms.map((m) => `<tr${m === "up" ? ' class="base"' : ""}><td class="an" title="${esc(full(m))}"><b>${esc(short(m))}</b>
        <span class="note">${esc(sub(m))}</span></td>${METALS.map(([s]) => cell(m, s)).join("")}</tr>`).join("") + "</table>";
  }

  function order(ms) {
    const key = (m) => { const c = cellOf(m, sortBy); return c && c.n >= ENOUGH ? [0, -share(c), -c.n] : [1, 0, -(c ? c.n : 0)]; };
    return ms.sort((a, b) => { const x = key(a), y = key(b); return x[0] - y[0] || x[1] - y[1] || x[2] - y[2]; });
  }

  // per metal: who has been right most often with enough calls, and who has been wrong most often, in plain words
  function best() {
    const ms = Object.keys(data.methods).filter((m) => m !== "up" && !data.retired.includes(m));
    const line = ([s, n]) => {
      const rows = ms.map((m) => [m, cellOf(m, s)]).filter(([, c]) => c && c.n >= ENOUGH);
      const good = rows.filter(([, c]) => share(c) >= GOOD).sort((a, b) => share(b[1]) - share(a[1])).slice(0, 3);
      const bad = rows.filter(([, c]) => share(c) <= BAD).sort((a, b) => share(a[1]) - share(b[1])).slice(0, 2);
      const up = cellOf("up", s);
      const nm = ([m, c]) => `<b title="${esc(full(m))}">${esc(short(m))}</b> ${c.right}/${c.n} (${pc(share(c))})`;
      return `<div class="bl"><span class="bm">${n}</span><div class="bw"><span>${good.length ? "<span class='up'>dinlə:</span> " + good.map(nm).join(" · ") : "<span class='mut'>hələ heç kim 55 %-dən yuxarı deyil</span>"}</span>` +
        (bad.length ? `<span><span class="down">tərsinə çıxır:</span> ${bad.map(nm).join(" · ")}</span>` : "") +
        (up && up.n ? `<span class="note">müqayisə: həmişə «qalxacaq» desən ${pc(share(up))}</span>` : "") + "</div></div>";
    };
    $("best").innerHTML = `<h3 class="sub">Hansı metalda kimi dinləmək olar <span class="note">(ən az ${ENOUGH} yoxlanmış fikir, ${HS[hz].toLowerCase()})</span></h3>` +
      METALS.map(line).join("");
  }

  function render() {
    segs();
    const all = Object.keys(data.methods);
    const old = new Set(data.retired || []);
    const live = order(all.filter((m) => !old.has(m) && m !== "up"));
    if (all.includes("up")) live.push("up");
    $("grid").innerHTML = table(live);
    $("oldgrid").innerHTML = table(order(all.filter((m) => old.has(m))));
    $("oldbox").hidden = !old.size;
    best();
    document.querySelectorAll(".srt").forEach((b) => b.onclick = () => { sortBy = b.dataset.s; keep(); render(); });
    document.querySelectorAll("td.ac[data-m]").forEach((td) => {
      const go = () => journal(td.dataset.m, td.dataset.s);
      td.onclick = go; td.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } };
    });
  }

  async function journal(m, s, quiet) {
    open = [m, s];
    const box = $("sec-j"); box.hidden = false;
    const name = short(m);
    $("jtitle").textContent = `${name} · ${MNAME[s]}${hz === "all" ? "" : " · " + HS[hz]}`;
    const c = cellOf(m, s);
    $("jsum").innerHTML = c ? `${c.n} fikir yoxlanıb: <b class="up">${c.right} düz</b>, <b class="down">${c.n - c.right} səhv</b> (${pc(share(c))}) · son 10: ${dots(c.last)} ${run(c.streak)}` : "";
    if (!quiet) { $("jlist").innerHTML = "<p class='note'>Yüklənir…</p>"; box.scrollIntoView({ behavior: "smooth", block: "start" }); }
    const q = `/api/calls?method=${encodeURIComponent(m)}&symbol=${s}&limit=100` + (hz === "all" ? "" : `&horizon=${hz}`);
    const d = await api(q);
    if (!d.calls.length) { $("jlist").innerHTML = "<p class='note'>Fikir yoxdur.</p>"; return; }
    $("jlist").innerHTML = `<table class="sc jr"><tr><th>Nə vaxt dedi</th><th>Müddət</th><th>Nə dedi</th><th>Nəyə əsasən</th><th class="c">Qiymət: o vaxt → sonra</th><th class="c">Nəticə</th></tr>` +
      d.calls.map((x) => {
        const said = x.said === "yuxarı" ? `<span class="up">▲ qalxacaq</span>` : `<span class="down">▼ düşəcək</span>`;
        const res = !x.checked ? `<span class="mut">⏳ ${dt(x.target_t)}</span>` : x.right ? `<span class="up">✅ düz</span>` : `<span class="down">❌ səhv</span>`;
        const mv = x.move_pct == null ? "" : ` <span class="note">(${x.move_pct >= 0 ? "dediyi tərəfə" : "əks tərəfə"} ${Math.abs(x.move_pct).toFixed(2)} %)</span>`;
        const basis = String(x.basis || "");
        return `<tr><td>${dt(x.issued_t)}</td><td class="mut">${HS[x.horizon] || x.horizon}</td><td>${said}</td>
          <td class="bs" title="${esc(basis)}">${esc(basis.length > 120 ? basis.slice(0, 118) + "…" : basis) || "<span class='mut'>—</span>"}</td>
          <td class="c">${price(x.price0)} → ${price(x.price1)}${mv}</td><td class="c">${res}</td></tr>`;
      }).join("") + "</table><p class='note'>Vaxtlar Nyu-York saatı ilə. «Dediyi tərəfə 0.12 %» — qiymət dediyi istiqamətdə bu qədər getdi.</p>";
  }

  async function load() {
    try {
      data = await api("/api/record" + (days ? `?days=${days}` : ""));
      render();
      if (open && !$("sec-j").hidden) journal(open[0], open[1], true).catch(() => {});
    } catch (e) {
      $("grid").innerHTML = `<p class="note">Məlumat alınmadı: ${esc(e.message)}</p>`;
    }
  }
  $("jclose").onclick = () => { $("sec-j").hidden = true; open = null; };
  setInterval(() => { $("clock").textContent = "Nyu-York " + new Date().toLocaleTimeString("az", { ...NY, hour: "2-digit", minute: "2-digit" }); }, 1000);
  load(); setInterval(load, 300000);
})();
