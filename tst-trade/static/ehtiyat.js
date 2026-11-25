// Fiziki ehtiyat: the owner's lots valued at the live price, totals with price scenarios, the sales journal.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const usd = (v) => (v == null ? "—" : (v < 0 ? "−" : "") + "$" + Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 2 }));
  const cls = (v) => (v == null ? "" : v > 0 ? "up" : v < 0 ? "down" : "");
  const NAMES = { XAU: "Qızıl", XAG: "Gümüş", XPT: "Platin", XPD: "Palladium" };
  let data = null, armed = null;
  async function post(action, body) {
    const r = await fetch("/api/stock/" + action, { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || "xəta");
    return j;
  }
  function render() {
    const d = data;
    $("totals").innerHTML = d.totals.length ? `<div class="tanow">` + d.totals.map((t) => `<div>
        <p><b>${esc(t.name)}</b> <span class="note">qiymət ${t.price ? usd(t.price) + "/unsiya" : "yoxdur"}</span></p>
        <div class="big">${t.net_g.toLocaleString("en-US")} q təmiz · ${t.net_oz} oz</div>
        <p>Dəyər: <b>${usd(t.spot_value)}</b> · rafineri ödəyər: <b>${usd(t.refiner_value)}</b></p>
        <p>Alış dəyəri: ${usd(t.cost)} · nəticə: <b class="${cls(t.result)}">${usd(t.result)}</b></p>
        <p class="note">Qiymət 1 $/unsiya dəyişəndə: ${usd(t.per_usd)} · ssenarilər: ${Object.entries(t.scenarios).map(([k, v]) => `${k}: <span class="${cls(v)}">${usd(v)}</span>`).join(" · ")}</p></div>`).join("") + "</div>" +
      `<p>Satışlardan reallaşmış nəticə: <b class="${cls(d.realised)}">${usd(d.realised)}</b></p>`
      : "<p class='note'>Hələ lot yoxdur: aşağıdan əlavə edin.</p>";
    $("lots").innerHTML = d.lots.length ? `<table class="sc"><tr><th>Lot</th><th>Metal</th><th>Qram</th><th>Əyar</th><th>Təmiz q</th><th>Alış</th><th>Dəyər</th><th>Rafineri</th><th>Nəticə</th><th></th></tr>` +
      d.lots.map((l) => `<tr><td>${esc(l.name)}<div class="note">${esc(l.bought || "")} ${esc(l.note || "")}</div></td><td>${NAMES[l.metal]}</td>
        <td class="c">${l.grams}</td><td class="c">${l.assay}</td><td class="c">${l.net_g}</td><td class="c">${usd(l.cost)}</td>
        <td class="c">${usd(l.spot_value)}</td><td class="c">${usd(l.refiner_value)}</td><td class="c ${cls(l.result)}">${usd(l.result)}</td>
        <td><button class="tabtn" data-del="${l.id}">${armed === l.id ? "Yenə bas: sil" : "Sil"}</button></td></tr>`).join("") + "</table>"
      : "<p class='note'>Açıq lot yoxdur.</p>";
    $("s_lot").innerHTML = d.lots.map((l) => `<option value="${l.id}">${esc(l.name)} (${l.grams} q)</option>`).join("");
    $("sales").innerHTML = d.sales.length ? `<table class="sc"><tr><th>Vaxt</th><th>Lot</th><th>Qram</th><th>Əyar</th><th>Alınan</th><th>Alış payı</th><th>Nəticə</th></tr>` +
      d.sales.map((s) => `<tr><td class="mut">${new Date(s.ts * 1000).toLocaleDateString("en-GB", { timeZone: "America/New_York" })}</td><td>${esc(s.lot)}</td>
        <td class="c">${s.grams}</td><td class="c">${s.assay}</td><td class="c">${usd(s.received)}</td><td class="c">${usd(s.cost)}</td><td class="c ${cls(s.result)}">${usd(s.result)}</td></tr>`).join("") + "</table>" : "";
    $("r_fee").value = d.settings.refiner_fee_pct; $("r_loss").value = d.settings.melt_loss_pct;
    document.querySelectorAll("[data-del]").forEach((b) => b.onclick = async () => {
      const id = +b.dataset.del;
      if (armed !== id) { armed = id; render(); setTimeout(() => { if (armed === id) { armed = null; render(); } }, 4000); return; }
      armed = null;
      try { await post("delete", { lot_id: id }); } catch (e) { alert(e.message); }
      load();
    });
  }
  $("f_add").onclick = async () => {
    try {
      await post("lot", { name: $("f_name").value, metal: $("f_metal").value, grams: +$("f_grams").value.replace(",", "."),
        assay: +$("f_assay").value.replace(",", "."), cost: +$("f_cost").value.replace(",", "."), bought: $("f_date").value, note: $("f_note").value });
      $("f_msg").textContent = "əlavə olundu"; ["f_name", "f_grams", "f_assay", "f_cost", "f_note"].forEach((k) => { $(k).value = ""; });
      load();
    } catch (e) { $("f_msg").textContent = e.message; }
  };
  $("csvb").onclick = async () => {
    try { const r = await post("csv", { text: $("csv").value }); $("csvm").textContent = `${r.added} lot əlavə olundu` + (r.errors.length ? "; " + r.errors.join("; ") : ""); load(); }
    catch (e) { $("csvm").textContent = e.message; }
  };
  $("s_go").onclick = async () => {
    try {
      await post("sell", { lot_id: +$("s_lot").value, grams: +$("s_grams").value.replace(",", "."), assay: +$("s_assay").value.replace(",", "."),
        received: +$("s_recv").value.replace(",", "."), note: $("s_note").value });
      $("s_msg").textContent = "satış yazıldı"; load();
    } catch (e) { $("s_msg").textContent = e.message; }
  };
  $("r_save").onclick = async () => {
    try { await post("settings", { refiner_fee_pct: +$("r_fee").value.replace(",", "."), melt_loss_pct: +$("r_loss").value.replace(",", ".") }); $("r_msg").textContent = "saxlandı"; load(); }
    catch (e) { $("r_msg").textContent = e.message; }
  };
  async function load() {
    try { const r = await fetch("/api/stock", { credentials: "same-origin" }); if (!r.ok) return; data = await r.json(); } catch (e) { return; }
    $("upd").textContent = "yeniləndi " + new Date().toLocaleTimeString("en-GB", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" }) + " NY";
    render();
  }
  load(); setInterval(load, 60000);
})();
