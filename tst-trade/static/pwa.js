/* Install the panel as an app on the phone or computer (PWA) and show when the connection is lost. */
(function () {
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
  const btn = document.getElementById("install");
  const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone;
  let ev = null;
  window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); ev = e; if (btn) btn.hidden = false; });
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  if (btn && ios && !standalone) btn.hidden = false;
  if (btn) btn.onclick = async () => {
    if (ev) { ev.prompt(); await ev.userChoice; ev = null; btn.hidden = true; return; }
    alert("iPhone / iPad: Safari-də aşağıdakı «Paylaş» düyməsini (kvadrat və ox) basın, sonra «Ana ekrana əlavə et» " +
      "(На экран «Домой» / Add to Home Screen) seçin.");
  };
  window.addEventListener("appinstalled", () => { if (btn) btn.hidden = true; });
  const off = document.getElementById("offline");
  const upd = () => { if (off) off.hidden = navigator.onLine; };
  addEventListener("online", upd); addEventListener("offline", upd); upd();
})();
