// İkiqat yoxlama (2FA) for the owner's login: set up (secret shown once, first code confirms, recovery codes shown
// once) and switch off (needs a current code or a recovery code). The secret never leaves the server otherwise.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  let armed = false;
  async function call(method, url, body) {
    const r = await fetch(url, { method, credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || "xəta");
    return d;
  }
  async function load() {
    let st;
    try { st = await call("GET", "/api/admin/2fa"); } catch (e) { return; }
    $("tfa-state").innerHTML = st.on ? `<b>✅ 2FA açıqdır.</b> Qalan ehtiyat kod: ${st.recovery_left}.` : "<b>⚠️ 2FA bağlıdır:</b> giriş yalnız parolla olur.";
    if (st.on) {
      $("tfa-box").innerHTML = `<label class="note" for="tfa-off-code">Söndürmək üçün indiki kod və ya ehtiyat kod</label>
        <input id="tfa-off-code" class="inp" inputmode="numeric" maxlength="9" autocomplete="one-time-code">
        <div class="btns"><button class="btn dan" id="tfa-off">${armed ? "Yenə bas: 2FA-nı söndür" : "2FA-nı söndür"}</button></div>`;
      $("tfa-off").onclick = async () => {
        if (!armed) { armed = true; load(); setTimeout(() => { armed = false; load(); }, 4000); return; }
        armed = false;
        try { await call("POST", "/api/admin/2fa/off", { code: $("tfa-off-code").value }); $("tfa-msg").textContent = "2FA söndürüldü."; } catch (e) { $("tfa-msg").textContent = e.message; }
        load();
      };
    } else {
      $("tfa-box").innerHTML = `<div class="btns"><button class="btn pri" id="tfa-start">2FA qur</button></div>`;
      $("tfa-start").onclick = start;
    }
  }
  async function start() {
    let d;
    try { d = await call("POST", "/api/admin/2fa/start"); } catch (e) { $("tfa-msg").textContent = e.message; return; }
    const grouped = d.secret.match(/.{1,4}/g).join(" ");
    $("tfa-box").innerHTML = `<p class="note"><b>1.</b> Telefonda və ya iPad-də autentifikator proqramını açın → «+» → <b>«Enter a setup key»</b> (açarı əl ilə yaz).
        Ad: <b>TST Trade</b>, açar aşağıdakıdır, növ: <b>Time based</b>.</p>
      <p class="mono" style="font-size:1.15em;letter-spacing:.05em;user-select:all">${esc(grouped)}</p>
      <p class="note">Proqram bu cihazdadırsa: <a href="${esc(d.uri)}">proqrama birbaşa əlavə et</a>. Bu açarı heç kimə göstərməyin və heç yerə yazmayın — yalnız proqrama.</p>
      <p class="note"><b>2.</b> Proqramın göstərdiyi 6 rəqəmi yazın:</p>
      <input id="tfa-code" class="inp" inputmode="numeric" maxlength="6" autocomplete="one-time-code">
      <div class="btns"><button class="btn pri" id="tfa-ok">Təsdiqlə və aç</button></div>`;
    $("tfa-ok").onclick = async () => {
      let r;
      try { r = await call("POST", "/api/admin/2fa/confirm", { code: $("tfa-code").value }); } catch (e) { $("tfa-msg").textContent = e.message; return; }
      $("tfa-msg").textContent = "";
      $("tfa-box").innerHTML = `<p><b>✅ 2FA açıldı.</b></p><p class="note"><b>Ehtiyat kodlar</b> — telefon itsə, bunlarla girəcəksiniz. Hər biri bir dəfə işləyir.
        İndi kağıza yazın və ya çap edin; bu səhifə bağlananda bir daha göstərilməyəcək.</p>
        <p class="mono" style="font-size:1.1em;line-height:1.8">${r.recovery.map(esc).join("<br>")}</p>
        <div class="btns"><button class="btn" id="tfa-done">Yazdım</button></div>`;
      $("tfa-done").onclick = load;
      $("tfa-state").innerHTML = "<b>✅ 2FA açıqdır.</b>";
    };
  }
  load();
})();
