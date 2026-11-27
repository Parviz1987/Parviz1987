# TST Trade — Claude üçün başlanğıc (hər sessiyada əvvəl oxu)

- **Bloklar barədə hər şey:** `tst-trade/docs/BLOKLAR.md` — hansı blok var, içində nə var, vəziyyəti, nə qalıb, necə
  bitirilir, sahibin işləri. «Blokları bitir / gücləndir» tapşırığında əvvəl onu oxu, işi bitirəndə onu yenilə.
- Ümumi plan və sahibin qərarları: `tst-trade/docs/IS-PLANI.md` (bölmə 5). Səhvlərim: `tst-trade/docs/monitor/sehvlerim.md`.
- Növbətçi yoxlama: skill `temirci` (`.claude/skills/temirci/SKILL.md`).
- Sahib: Azərbaycan dilində sadə və hörmətli cavab, vaxtlar New York saatı ilə.
- Qaydalar: dostun repo-su `dtxxkxxtq/pj-trade-gold` — yalnız oxumaq; açar/parol çata yazılmır; qiymət LLM-dən heç
  vaxt; pul, nəticəni dəyişən dəyişiklik, ticarət, açar/model, məlumat silmək, blok çıxarmaq — sahibdən izahla soruş;
  qorunan fayllar (`tst-trade/deploy/protected.txt`) yalnız `Sahib-təsdiqi:` commit sətri ilə serverə düşür.
- **Server yalnız `claude/amazing-keller-c4hwfl` budağından yenilənir** (`deploy/update.sh`, 5 dəqiqədən bir). Yeni sessiya
  başqa budaqda işləsə belə, serverə gedən iş bu budağa push olunmalıdır.
- Testlər: `cd tst-trade && python -m pytest -q`. Server: https://tsttrade.duckdns.org (diag proxy tokeni ilə).
