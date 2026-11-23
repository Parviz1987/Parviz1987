# Gecə hesabatı — 2026-11-23

Plan: [`gece-plani.md`](gece-plani.md). Hər hissə ayrıca commit olub, server özü yenilənib, yoxlama canlı diaqnostika ilə aparılıb.

## Nə edildi

| # | İş | Vəziyyət | Necə yoxlanıb |
|---|---|---|---|
| 1 | Gümüş, platin, palladium tarixçəsi Capital.com-dan | ✅ Serverdə: hər metal üçün ~860 gün, ~900 saat, ~1000 dəqiqə, ~570–600 həftə şamı | `/api/diag` → history |
| 1 | Forex Factory "404" | ✅ Gələn həftənin faylı hələ dərc olunmayanda xəta sayılmır | diaq: "75 hadisə", xəta yoxdur |
| 1 | Palladium 900.0 | ✅ Problem yox idi: qiymət hərəkət edir (903.65 → 905.15), alış/satış fərqi 5 $ | diaq: son 8 tik |
| 2 | Yeni üfüqlər: 3 gün, 10 gün, 1 ay | ✅ | testlər + serverdə tarixçə yoxlaması |
| 2 | Yeni üsullar: Trend, Sıçrayış, RSI, Fibonacci, Makro | ✅ Hamısı Hakimdə | testlər |
| 3 | Qrafik alətləri: EMA, Bollinger, Fibonacci, pivot, dəstək/müqavimət, dəyirmi səviyyələr, RSI/MACD, Texniki xülasə | ✅ | ekran şəkilləri (kompüter + telefon), konsolda xəta yoxdur |
| 4 | Hakimin ümumi cədvəli və dəqiqlik qrafikləri | ✅ | ekran şəkli |
| 5 | Telefon proqramı (PWA) | ✅ «Telefona yüklə» düyməsi | manifest və service worker cavab verir |
| 6 | Fundamental: VIX, S&P 500, CFTC COT | ✅ FRED yüklənir; COT düzəlişi göndərilib, ilk yükləmə yoxlanır | diaq → sources.cot |
| 7 | Oxuyucu beyninin yoxlanması (1 saat sonra) | ✅ | test |
| 8 | Sistem vəziyyəti səhifəsi `/status` | ✅ yalnız sahib üçün | ekran şəkli |
| 9 | Grok Kəşfiyyatçı (X və vebdə canlı axtarış) | ✅ kod hazırdır, real çağırış hələ görünməyib | test (sınaq cavabı ilə) |
| 10 | Növbətçi yoxlama hər 3 saatdan bir | ✅ | planlaşdırılıb |

## İlk real nəticələr (tarixçə üzrə, Hakim)
Qızıl, 1 gün, ~2000 gün: heç bir üsul hələ «sübut» almayıb. Məsələn: momentum 51 %, trend 53 %, Fibonacci 55 %,
makro 50 %, RSI 42 %. Keçməli hədd «Həmişə yuxarı» üsulunun 53 %-dir.
Bu o deməkdir ki, sadə alətlər təkbaşına qızılın gündəlik istiqamətini bazisdən yaxşı demir. Bu, dürüst nəticədir.
Canlı yoxlama yığıldıqca rəqəmlər dəyişə bilər.

## Audit (ikinci təlimat): tapılan və düzəldilən

**Kod rəyçisi (ayrıca agent) 8 xəta tapdı, hamısı düzəldildi və testlə qorunur:**
1. Həftə sonu gündəlik proqnozlar eyni hədəf üçün 3 dəfə yazılırdı: Hakimin canlı sayı şişirdi.
2. Makro üsul tarixçədə hələ dərc olunmamış FRED rəqəmlərini görürdü (real faiz 1 gün, dollar indeksi 9 günə qədər tez):
   tarixçə nəticəsi süni yaxşı çıxırdı. İndi dərc olunma gecikməsi nəzərə alınır, köhnə nəticələr silinib yenidən hesablandı.
3. Köhnə bazar günü "qırıq" gündəlik şamları silindi; mənbədən gələn həftə sonu şamları qəbul edilmir.
4. Hakimin qrafik sorğusu hər 20 saniyədə yüz minlərlə sətri oxuyurdu: indi son dövr + 2 dəqiqəlik yaddaş.
5. Saat effekti üsulu tarixçədə bəzən səhv saatı götürürdü.
6. Gündəlik hədəfə 5–25 günlük artıq tolerantlıq var idi: indi dəqiq iş günü (+2 gün bayram üçün).
7. Grok gözlənilməz cavab yazsa, dövrə dayanırdı: indi dözümlüdür.
8. Capital.com tarixçə girişi uğursuz olsa, canlı axının girişini də dayandıra bilərdi: ayrıldı.

**Hədəfə görə audit (öz yoxlamam):**
- **Təsadüfi "sübut" riski:** hər kartda 9 üsul eyni anda yoxlanır; 20-dən biri təsadüfən p < 0.05 keçir.
  İndi hədd üsulların sayına bölünür (Bonferroni). Qızılın 1 saatlıq Fibonacci "sübutu" (p = 0.04) bu səbəbdən götürüldü.
- **Xərc nəzərə alınmırdı:** qızılın 1 dəqiqəlik "Qısa dönüş"ü 70 % düz çıxır, amma bu kotirovka səs-küyüdür:
  orta hərəkət alış-satış fərqindən (spread) kiçikdir, pul qazandırmaz. İndi belə hallar «Spreaddən kiçik» göstərilir,
  "sübut" sayılmır. Cədvəldə "Orta qazanc / spread" sütunu var.
- **Aralıqlar düzgün deyildi:** "50 % aralıq" qızılın saatlığında 68 % tuturdu (çox geniş). Səbəb: metal hərəkətlərində
  "qalın quyruq" var. İndi aralığın eni keçmiş hərəkətlərdən ölçülür (yalnız keçmiş məlumat). Sınaqda 49 % / 76 %.
- **Alpaca açarı saxlanmışdı, amma işə qoşulmamışdı:** Benzinga xəbərləri (metal fondları və mədən şirkətləri) dəqiqədə bir.
- **Konsensus üsulu:** bütün alətlərin birgə fikri, Hakim yoxlayır.
- **Sürət:** Hakimin statistikası yaddaşda saxlanır, jurnal üçün indeks; serverin yaddaşı 100 MB civarı, 200+ MB boş.
- **Telefon:** yuxarıda bölmə zolağı (Qrafik · Proqnoz · Fundamental · Hakim · Xəbər).

## Qalanlar və sizin qərarınız lazım olanlar
1. **Grok xərci:** bir axtarış ~0.9 $ (ehtiyatla hesablanır). 4 saatda bir → aylıq 20 $ limit təxminən 5–7 günə çatır.
   Limit: Admin → Beyin yuvaları → Kəşfiyyatçı. Real xərci xAI konsolunda yoxlamaq olar.
2. **Canlı sübut vaxt tələb edir:** 1 gün üçün 250, 1 saat üçün 200 canlı yoxlama lazımdır (həftələr, aylar).
   O vaxta qədər kartlar tarixçəyə əsaslanır və "tarixçə" yazılır.
3. **Twelve Data pulsuz planı:** gümüş, platin, palladium yoxdur — artıq Capital.com əvəz edir, alış lazım deyil.
4. **Dürüst nəticə:** indiyə qədər heç bir üsul xərcdən sonra sübut almayıb. Növbəti addım üçün təklif: hadisə
   (CPI, FOMC, NFP) sürprizinə əsaslanan üsul — FMP açarı (pullu) və ya Forex Factory-nin "fakt" sütunu ilə.
