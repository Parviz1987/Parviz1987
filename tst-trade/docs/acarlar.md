# Açarlar: sahibin işləri (2026-11-24 vəziyyəti)

Açarlar yalnız serverdə saxlanır (Admin səhifəsi → kart → «Saxla» → «Yoxla»). Heç vaxt söhbətə, GitHub-a və ya
brauzer koduna yazılmır.

| Açar | Nə üçün | Vəziyyət | Sizdən lazım olan |
|---|---|---|---|
| Capital.com | 4 metal + 8 əlaqəli bazar canlı, tarixçə (4000 şama qədər) | ✅ işləyir (real hesab) | heç nə |
| Twelve Data | qızılın əlavə tarixçəsi | ✅ işləyir (pulsuz plan: yalnız qızıl) | heç nə |
| Anthropic (Claude) | Strateq (izah + ehtimal), Rəqəm ovçusunun 2-ci beyni | ✅ işləyir | heç nə |
| OpenAI | Oxuyucu, Rəqəm ovçusu, İkinci analitik (yeni) | ✅ işləyir | heç nə |
| xAI (Grok) | Kəşfiyyatçı: X-də axtarış, həyəcanda dərhal | ✅ işləyir | heç nə |
| FRED | real faiz, dollar, VIX, neft (gündəlik) | ✅ işləyir | heç nə |
| Alpaca | Benzinga xəbər lenti | ✅ işləyir | heç nə |
| FMP | ABŞ rəqəmlərinin keçmiş faktları | ⚠️ açar işləyir, amma planda təqvim yoxdur (HTTP 402) | **istəyə görə**: Starter planı (~29 $/ay). Açar dəyişmir: alandan sonra Admin → FMP → «Yoxla» |
| **BLS** | ABŞ rəqəmlərinin rəsmi faktı dərhal (CPI, iş yerləri, işsizlik, PPI) | açarsız da işləyir (gündə 25 sorğu) | **Tövsiyə**: pulsuz açar → https://data.bls.gov/registrationEngine/ → Admin → BLS → «Saxla» → «Yoxla» |
| **Cloudflare R2** | Gecəlik ehtiyat nüsxə serverdən kənarda | kart hazırdır, açar yoxdur | **Tövsiyə**: Cloudflare-də R2 bucket və API token → Admin → R2 kartına 4 sahə (account_id, access_key_id, secret_access_key, bucket) → «Yoxla» |
| Google (Gemini) | yalnız ehtiyat beyin (əsas beyin cavab verməyəndə) | lazım deyil | heç nə |

## Nəticə
- **Məcburi heç bir açar və alış yoxdur.** Qurulan sinir sistemi indiki açarlarla tam işləyir.
- Canlı ABŞ rəqəmlərini FMP-siz Rəqəm ovçusu tapır (iki beyin vebdə, ikisi eyni deyəndə).
- FMP yalnız keçmişi verir: «Hadisə sürprizi» üsulunu 2 illik keçmişdə dərhal yoxlamaq üçün. Almasanız, bu üsul
  canlı rəqəmlər yığıldıqca (ayda ~15-20 mühüm ABŞ rəqəmi) yavaş-yavaş yoxlanır.

## Server
- **DigitalOcean: 512 MB → 1 GB** (ayda ~+2 $). Baza 500 MB-ı keçib, yaddaş dardır. DigitalOcean → Droplets → tst →
  **Resize** → 1 GB (CPU and RAM only) → Resize. Server bir neçə dəqiqə dayanır, sonra özü qalxır.

## Aylıq beyin xərci (hər yuvanın öz limiti var, Admin → Beyinlər)
Kəşfiyyatçı, Rəqəm ovçusu, Oxuyucu, Strateq, İkinci analitik: hər biri ayda 20 $ limit. Limit dolanda yuva dayanır,
sistemin qalanı işləyir. Həyəcan təhlili gündə ən çox 12, həyəcanda X axtarışı gündə ən çox 3 dəfə.
