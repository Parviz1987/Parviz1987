// Kağız ticarət (Radar Gold): a virtual account that acts only on AL / SAT, i.e. only on a strategy that passed the
// Judge, the one-look final test, the independent re-check and the owner's approval. No real money, no broker.
// Shows the account, open positions, statistics, the journal (rejected proposals with the reason), the emergency stop.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const day = (t) => (t ? new Date(t * 1000).toLocaleString("en-GB", { timeZone: "America/New_York" }) : "—");
  const usd = (v) => (v == null ? "—" : (v < 0 ? "−$" : "$") + Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 2 }));
  const px = (v) => (v == null ? "—" : Number(v).toFixed(2));
  let armed = false;
  async function post(body) {
    await fetch("/api/admin/paper", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    load();
  }
  async function load() {
    let d;
    try { const r = await fetch("/api/admin/paper", { credentials: "same-origin" }); if (!r.ok) return; d = await r.json(); } catch (e) { return; }
    const s = d.settings, st = d.stats, orders = d.orders || [];
    $("paper").innerHTML =
      `<p class="note">Yalnız sizin təsdiqlədiyiniz sübutlu strategiya AL / SAT verəndə virtual mövqe açılır. Hazırda belə strategiya ${orders.length ? "var və ya olub" : "yoxdur, ona görə sistem gözləyir"}.
        Hər təklif risk mühərrikindən keçir: köhnə qiymət, eyni masada açıq mövqe, günlük zərər limiti, ümumi açıq risk. Giriş və çıxış xərclə (spred + sürüşmə), gecə haqqı ilə hesablanır.</p>
      <p><b>Hesab:</b> ${usd(d.equity)} (başlanğıc ${usd(s.start_usd)}) · bir əmrə risk ${s.risk_pct}% · günlük zərər limiti ${s.daily_loss_pct}% · ümumi açıq risk ${s.open_risk_pct}%
        · ${s.stopped ? "<b style='color:var(--dn,#c33)'>⛔ Təcili dayanma AÇIQDIR</b>" : "✅ işləyir"}</p>
      <p class="note">Bağlanmış əmr: ${st.trades} · qazanma payı ${st.win_rate == null ? "—" : (st.win_rate * 100).toFixed(0) + "%"} · mənfəət əmsalı ${st.profit_factor == null ? "—" : st.profit_factor.toFixed(2)}
        · bir əmrin orta nəticəsi ${usd(st.expectancy)} · ən böyük geriləmə ${(st.max_drawdown * 100).toFixed(1)}%</p>
      <div class="btns"><button class="btn ${s.stopped ? "pri" : "dan"}" id="p-stop">${s.stopped ? "Təcili dayanmanı söndür" : armed ? "Yenə bas: təcili dayan" : "Təcili dayan"}</button></div>
      ${orders.length ? `<div class="tbl"><table class="sc"><tr><th>Vaxt (NY)</th><th>Masa</th><th>İstiqamət</th><th>Unsiya</th><th>Giriş</th><th>Stop</th><th>Hədəf</th><th>Status</th><th>Nəticə</th><th>Səbəb</th></tr>` +
        orders.map((o) => `<tr><td class="mut">${day(o.ts)}</td><td>${esc(o.symbol)} ${esc(o.horizon)}</td><td>${o.dir > 0 ? "AL" : "SAT"}</td><td>${o.oz || "—"}</td>
          <td>${px(o.entry)}</td><td>${px(o.stop)}</td><td>${px(o.target)}</td><td>${esc(o.status)}</td><td>${usd(o.pnl)}</td><td class="note">${esc(o.reason)}</td></tr>`).join("") + "</table></div>"
        : "<p class='note'>Jurnal boşdur.</p>"}`;
    $("p-stop").onclick = () => {
      if (s.stopped) { post({ stop: false }); return; }
      if (!armed) { armed = true; load(); setTimeout(() => { if (armed) { armed = false; load(); } }, 4000); return; }
      armed = false; post({ stop: true });
    };
  }
  load(); setInterval(load, 60000);
})();
