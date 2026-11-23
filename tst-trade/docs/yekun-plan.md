# Yekun plan — 23.11.2026

## Hədəf
Bazardakı hadisəni dərhal bilmək; qızıl, gümüş, platin və palladiumun qalxıb-düşəcəyini (1 dəqiqədən 1 aya qədər)
əvvəlcədən demək; bunun düz olduğunu Hakimin xərcdən sonra sübut etməsi. Ticarət yalnız bundan sonra, sizin qərarınızla.

## Qayda: yamaq yoxdur
Sistemə qoyulan hər hissənin **pasportu** olur və bu pasport sistemin özündə görünür:
1. **Niyə:** hansı səbəbə görə qızıla təsir edir.
2. **Nə gözləyirik:** hansı üfüqdə, hansı nəticə.
3. **Necə ölçülür:** Hakimin rəqəmi.
4. **Nəticə vermirsə:** nə ilə əvəz olunur, harası inkişaf etdirilir.

Kifayət qədər yoxlamadan sonra "sübut yoxdur" çıxan hissə konsensusdan çıxarılır (silinmir, izi qalır).

## Mövcud vəziyyət

| Qat | Var | Çatmır |
|---|---|---|
| Qiymət | 4 metal canlı (Capital.com, saniyə-saniyə), tarixçə | Neft, dollar, səhm indeksi, faiz **canlı** yoxdur (eyni Capital axınında var, istifadə olunmur) |
| Makro | FRED gündəlik: real faiz, nominal faiz, inflyasiya gözləntisi, dollar indeksi, VIX, S&P 500 | Gün içi faiz və dollar hərəkəti yoxdur; neft heç yoxdur |
| Mövqe | CFTC COT (həftəlik) | — |
| Hadisə | Forex Factory: vaxt + gözlənti | **Fakt rəqəmi yoxdur** (FMP planı vermir, Forex Factory vermir) |
| Xəbər | Google News, Fed, Benzinga (Alpaca), Grok X/veb | Xəbərlər proqnoza qoşulmayıb (yalnız göstərilir) |
| Beyinlər | Grok (Kəşfiyyatçı), OpenAI (Oxuyucu), Claude (Strateq) | Heç biri proqnozçu kimi Hakimdə yoxlanmır; Claude və OpenAI veb axtarışı işlədilmir |
| Analiz | 12 üsul, 8 üfüq | Bazarlar arası əlaqə (dollar → qızıl, neft → qızıl) yoxdur |
| Hakim | Statistik yoxlama, xərc, çoxlu yoxlama düzəlişi, aralıqlar düzdür | Seans üzrə ayrıca hökm yoxdur; pasport yoxdur |
| Nəticə | Aralıqlar düzdür (≈50 / 80 %) | **İstiqamət hələ sübut olunmayıb** |

## Quruluş: 3 qat

**1. Məlumat agentləri (kod, beyin deyil: pulsuz, daim işləyir)**
- **Capital axını** genişlənir: metallarla yanaşı dollar (EUR/USD, USD/JPY, dollar indeksi əgər brokerdə varsa),
  neft (WTI, Brent), S&P 500, ABŞ faizi (əgər brokerdə varsa). Bazar adları brokerin öz axtarışı ilə tapılır, uydurulmur.
- FRED, COT, təqvim, RSS və Benzinga olduğu kimi qalır.

**2. Beyin agentləri (dar iş, yalnız lazım olanda çağırılır)**
Beyinlər daim işləmir. Kiçik agent hadisəni gözləyir, beyni yalnız lazım olanda çağırır, nəticəni bazaya yazır.

| Agent | Beyin | Nə vaxt | Nə gətirir | Necə yoxlanır |
|---|---|---|---|---|
| Rəqəm ovçusu | OpenAI + Claude (veb axtarışı) | ABŞ rəqəmi çıxandan 2–3 dəq sonra | Fakt rəqəmi + mənbə linki | İki beyin eyni rəqəmi deməlidir; FMP gəlsə, FMP əsas olur |
| Kəşfiyyatçı | Grok (yalnız X) | 4 saatda bir; hadisə ərəfəsində 30 dəq | X-dəki vacib xəbərlər | Oxuyucunun qiymətləndirməsi Hakimdə |
| Oxuyucu | OpenAI (ucuz) | Yeni başlıq gələndə | Başlığın təsiri: metal, istiqamət, güc | "Xəbər əhvalı" üsulu Hakimdə |
| Strateq | Claude | Gündə 1 dəfə + saatlıq izah | Günün istiqaməti (rəqəmsiz) və səbəbi | "Strateqin fikri" üsulu Hakimdə |

**3. Analiz + Hakim**
- **Yeni üsullar yalnız mövcud məlumatdan:**
  - dollar impulsu (dollar hərəkət edib, qızıl hələ reaksiya verməyib);
  - neft impulsu;
  - qızıl/gümüş nisbəti;
  - xəbər əhvalı;
  - Strateqin fikri;
  - hadisə sürprizi (fakt rəqəm ovçusundan gəlir).
- **Hakim seans üzrə** (Asiya, London, Nyu-York) ayrıca hökm verir; sərt qaydalar qalır.
- **Pasport və təmizlik qaydası.**

## Yeni bölmə: "Bazarlar və əlaqələr"
- Bir ekranda: qızıl, gümüş, neft, dollar, S&P 500, faiz, VIX — hər birinin canlı qiyməti, günlük dəyişməsi, kiçik qrafiki.
- Hər biri üçün: **niyə qızılla əlaqəlidir** (bir cümlə), **əlaqə indi nə qədərdir** (son 30 gün və son gün içi
  korrelyasiya), **qabaqlayırmı** (hərəkəti qızıldan əvvəl olurmu: Hakimin rəqəmi).
- Əlaqə iddia edilmir, ölçülür: zəifləyəndə ekranda görünür.

## İş sırası və uğur ölçüsü

| # | İş | Uğur ölçüsü | Nəticə verməsə |
|---|---|---|---|
| 1 | Pasport sistemi + seans üzrə Hakim | Hər hissənin pasportu var; seans hökmü görünür | — (bu, ölçmə qatıdır) |
| 2 | Capital axınına əlaqəli bazarlar + "Bazarlar və əlaqələr" bölməsi | Neft, dollar, S&P canlı; korrelyasiya hesablanır | Brokerdə olmayan bazar FRED-in gündəlik rəqəmi ilə göstərilir |
| 3 | Dollar / neft impulsu, qızıl/gümüş nisbəti | Hakimdə 1 dəq, 1 saat, 4 saat üzrə yoxlanır | Seansa görə daralır; yenə yoxdursa, konsensusdan çıxır |
| 4 | Rəqəm ovçusu → hadisə sürprizi işə düşür | Hər rəqəm 5 dəqiqə ərzində, iki beynin razılığı ilə | FMP planı (axşam qərarınız) |
| 5 | Xəbər əhvalı + Strateqin fikri Hakimdə | Beyinlərin faydası rəqəmlə görünür | Faydasız beyin işi azaldılır, xərc qənaət olunur |
| 6 | Grok yalnız X-ə; veb axtarışı ucuz beyinlərə | Aylıq limit ay sonuna çatır | — |

**Etmirik:** yeni pullu mənbə (FMP — sizin qərarınız), yeni indikator yığını, ticarət.

**Dürüst gözlənti:** ən böyük şans 3-cü və 4-cü bənddədir (dollar və hadisə sürprizi qızılı qısa müddətdə ən çox
hərəkət etdirir). Zəmanət yoxdur; amma hər hissənin işləyib-işləmədiyi rəqəmlə görünəcək.

## İcra vəziyyəti — 23.11, axşam (serverdə yoxlanıb, versiya bb69a41)

| # | İş | Vəziyyət |
|---|---|---|
| 0 | Üfüqlər: 1 dəqiqə çıxarıldı; 15 və 30 dəqiqə əlavə olundu | ✅ |
| 1 | Pasportlar + seans və bazar əhvalı üzrə şərtli sübut | ✅ |
| 2 | Bazarlar və əlaqələr: Capital-da 8 bazar tapıldı və canlıdır (dollar indeksi, EUR/USD, USD/JPY, WTI, Brent, S&P 500, VIX, 10 illik istiqraz), hər biri ~800–1000 şam tarixçə | ✅ |
| 3 | Dollar və neft impulsu | ✅ işləyir; tarixçədə nəticə ~50 % (sübut yoxdur, 200–350 yoxlama) |
| 4 | Rəqəm ovçusu (OpenAI + Claude, ikisi razı olmalı) | ✅ hazırdır; ilk mühüm ABŞ rəqəmini gözləyir |
| 5 | Xəbər əhvalı və Strateqin fikri Hakimdə | ✅ canlı yığılır (tarixçə yoxdur) |
| 6 | Grok yalnız X | ✅ |

**Dürüst nəticə:** heç bir üsul, şərtli olanlar da daxil, hələ sübut almayıb. Dollar və neft impulsu tarixçədə
(qızıl üçün 15 dəqiqədən 1 günə qədər) ~49–55 % düz çıxır — bazisdən fərqlənmir. Hakim, rəqəm ovçusu və beyin üsulları
indi canlı yoxlama yığır; növbətçi gündə bir dəfə səbəbləri araşdırıb `docs/monitor/teklifler.md` faylına yazır.
