/* Candlestick chart on a canvas, no library. drawChart(canvas, candles, overlay, tip) */
(function () {
  function css(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }
  function fmt(x) { return x >= 100 ? x.toFixed(2) : x.toFixed(3); }
  function tlabel(t, tf) {
    const d = new Date(t * 1000);
    const p = (n) => String(n).padStart(2, "0");
    if (tf === "1d" || tf === "1w") return p(d.getUTCDate()) + "." + p(d.getUTCMonth() + 1);
    return p(d.getUTCHours()) + ":" + p(d.getUTCMinutes());
  }
  const state = { cs: [], ov: null, tf: "1m", hover: -1 };

  function draw(cv, tip) {
    const dpr = window.devicePixelRatio || 1;
    const W = cv.clientWidth, H = cv.clientHeight;
    cv.width = W * dpr; cv.height = H * dpr;
    const g = cv.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, W, H);
    const cs = state.cs;
    const fg = css("--muted"), line = css("--line"), up = css("--up"), down = css("--down"), gold = css("--gold");
    g.font = "11px " + css("--mono");
    if (!cs.length) { g.fillStyle = fg; g.fillText("Şam hələ yoxdur: qiymətlər yığılır.", 16, 30); tip.textContent = ""; return; }
    const padR = 64, padB = 22, padT = 24, extra = state.ov ? 3 : 0;
    const n = cs.length, slots = n + extra, cw = (W - padR) / slots;
    let lo = Math.min(...cs.map(c => c.l)), hi = Math.max(...cs.map(c => c.h));
    if (state.ov) { lo = Math.min(lo, state.ov.lo80); hi = Math.max(hi, state.ov.hi80); }
    if (hi === lo) { hi += 1; lo -= 1; }
    const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
    const y = (v) => padT + (hi - v) / (hi - lo) * (H - padT - padB);
    g.strokeStyle = line; g.fillStyle = fg; g.lineWidth = 1;
    for (let i = 0; i <= 5; i++) {
      const v = lo + (hi - lo) * i / 5, yy = Math.round(y(v)) + .5;
      g.beginPath(); g.moveTo(0, yy); g.lineTo(W - padR, yy); g.stroke();
      g.fillText(fmt(v), W - padR + 6, yy + 4);
    }
    const step = Math.max(1, Math.ceil(n / 7));
    for (let i = 0; i < n; i += step) g.fillText(tlabel(cs[i].t, state.tf), i * cw + 2, H - 6);
    const bw = Math.max(1, cw * 0.7);
    cs.forEach((c, i) => {
      const x = i * cw + cw / 2, col = c.c >= c.o ? up : down;
      g.strokeStyle = col; g.fillStyle = col;
      g.beginPath(); g.moveTo(Math.round(x) + .5, y(c.h)); g.lineTo(Math.round(x) + .5, y(c.l)); g.stroke();
      const top = y(Math.max(c.o, c.c)), bh = Math.max(1, y(Math.min(c.o, c.c)) - top);
      g.fillRect(x - bw / 2, top, bw, bh);
    });
    if (state.ov) {
      const x0 = n * cw + cw * 0.2, w = cw * 2.6, o = state.ov;
      g.globalAlpha = .22; g.fillStyle = gold; g.fillRect(x0, y(o.hi80), w, y(o.lo80) - y(o.hi80));
      g.globalAlpha = .45; g.fillRect(x0, y(o.hi50), w, y(o.lo50) - y(o.hi50));
      g.globalAlpha = 1; g.strokeStyle = gold; g.setLineDash([4, 3]);
      g.beginPath(); g.moveTo(0, y(o.price0)); g.lineTo(x0 + w, y(o.price0)); g.stroke(); g.setLineDash([]);
    }
    const last = cs[n - 1];
    g.fillStyle = gold; g.fillRect(W - padR, y(last.c) - 8, padR, 16);
    g.fillStyle = "#1b1505"; g.fillText(fmt(last.c), W - padR + 6, y(last.c) + 4);
    const hcan = state.hover >= 0 && state.hover < n ? cs[state.hover] : last;
    if (state.hover >= 0 && state.hover < n) {
      g.strokeStyle = fg; g.globalAlpha = .4;
      const x = state.hover * cw + cw / 2;
      g.beginPath(); g.moveTo(x, padT); g.lineTo(x, H - padB); g.stroke(); g.globalAlpha = 1;
    }
    tip.textContent = tlabel(hcan.t, "1m") + " UTC  Açılış " + fmt(hcan.o) + "  Max " + fmt(hcan.h) + "  Min " + fmt(hcan.l) +
      "  Bağlanış " + fmt(hcan.c);
    state.cw = cw;
  }

  window.drawChart = function (cv, tip, candles, overlay, tf) {
    state.cs = candles; state.ov = overlay; state.tf = tf; draw(cv, tip);
    if (!cv._wired) {
      cv._wired = true;
      cv.addEventListener("mousemove", (e) => {
        const r = cv.getBoundingClientRect();
        state.hover = Math.floor((e.clientX - r.left) / (state.cw || 1)); draw(cv, tip);
      });
      cv.addEventListener("mouseleave", () => { state.hover = -1; draw(cv, tip); });
      window.addEventListener("resize", () => draw(cv, tip));
    }
  };
})();
