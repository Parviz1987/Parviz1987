# TST Trade — Claude üçün başlanğıc (hər sessiyada əvvəl oxu)

- **Bloklar barədə hər şey:** `tst-trade/docs/BLOKLAR.md` — hansı blok var, içində nə var, vəziyyəti, nə qalıb, necə
  bitirilir, sahibin işləri. «Blokları bitir / gücləndir» tapşırığında əvvəl onu oxu, işi bitirəndə onu yenilə.
- **Köhnə söhbətlərin xülasəsi** (22–27.11; ikinci sessiya 27.11 təhlükəsizlik filtrində ilişdi — bölmə 5a): `tst-trade/docs/SOHBET-TARIXCESI.md` — sahib necə danışır, nə qərar
  verilib, hansı suallara nə cavab verilib, nə açıq qalıb. Yeni sessiyada əvvəl onu oxu.
- Ümumi plan və sahibin qərarları: `tst-trade/docs/IS-PLANI.md` (bölmə 5). Səhvlərim: `tst-trade/docs/monitor/sehvlerim.md`.
- Növbətçi yoxlama: skill `temirci` (`.claude/skills/temirci/SKILL.md`).
- Sahib: Azərbaycan dilində sadə və hörmətli cavab, vaxtlar New York saatı ilə.
- Qaydalar: dostun repo-su `dtxxkxxtq/pj-trade-gold` — yalnız oxumaq; açar/parol çata yazılmır; qiymət LLM-dən heç
  vaxt; pul, nəticəni dəyişən dəyişiklik, ticarət, açar/model, məlumat silmək, blok çıxarmaq — sahibdən izahla soruş;
  qorunan fayllar (`tst-trade/deploy/protected.txt`) yalnız `Sahib-təsdiqi:` commit sətri ilə serverə düşür.
- **Server yalnız `claude/amazing-keller-c4hwfl` budağından yenilənir** (`deploy/update.sh`, 5 dəqiqədən bir). Yeni sessiya
  başqa budaqda işləsə belə, serverə gedən iş bu budağa push olunmalıdır.
- **Sayt dəyişikliyi sahibin brauzerinə özü çatmalıdır (sahib 26.11: «hər dəyişiklik avtomatik brauzerə getsin»):**
  səhifələr və `/static/` faylları `Cache-Control: no-cache` ilə gedir (`app/main.py` guard, test
  `tests/test_cache_headers.py`); service worker (`static/sw.js`) brauzerin köhnə nüsxəsini keçib serverdən soruşur;
  hər səhifə `static/nav.js` ilə `/version`-u izləyir və yeni versiyada özü yenilənir (sahib yazı yazarkən gözləyir).
  Yeni səhifə mütləq `nav.js` yükləsin; `sw.js`-in qaydası dəyişsə `CACHE` adını artır. Deploydan sonra «serverdə
  canlıdır» demək azdır: `curl -I` ilə yeni faylın gəldiyini yoxla. Sayt dəyişikliyini əvvəl sınaq serverində masaüstü
  (1366) və telefon (390) ölçüsündə şəkil + brauzer xətası yoxlaması ilə sına; ana səhifəyə yeni bölmə qoyma — öz
  səhifəsinə qoy (quruluş: `tst-trade/docs/SOHBET-TARIXCESI.md`, qərar 5).
- Testlər: `cd tst-trade && python -m pytest -q`. Server: https://tsttrade.duckdns.org (diag proxy tokeni ilə).
