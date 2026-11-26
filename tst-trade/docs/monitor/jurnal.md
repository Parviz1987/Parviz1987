# Növbətçi yoxlama jurnalı

## 2026-11-23, 16:50 NY (avtomatik yoxlama; yazısı GitHub-a düşmədiyi üçün buraya köçürüldü)
- Təhlükəsizlik: sakit. 24 saatda 1 uğurlu giriş, uğursuz giriş yoxdur. CSP və HSTS yerindədir, /api/diag tokensiz 401 verir.
- Sağlamlıq: versiya f54c64d, /healthz cavab verir, 4 metal canlı, xəta yoxdur. DB 206 MB, boş yaddaş 179 MB.
- Xəbərdarlıq: VIX və ABŞ 10 illik istiqraz brokerdən gəlmir. «Hadisə sürprizi» üsulunun girişi yoxdur (faktiki rəqəm yoxdur).
- Diqqət: qızılın 30 dəqiqəlik tarixində «geri dönüş» 64,9 % düz çıxır, digər metallarda 44-54 %. Şübhəli: iki mənbənin şamları qarışmış ola bilər, yoxlanmalıdır.
- Uzun müddətlərdə (10 gün, 1 ay) qızıl və gümüşün aralıqları bir az dardır.
- Problem: bu yoxlama GitHub-a yaza bilmədi (403). Həll: 23:28 NY-dən yoxlama sahibin söhbətinə bağlandı, köhnə tapşırıq dayandırıldı.

## 2026-11-23, 19:48 NY (növbətçi yoxlama, bu söhbətdə)
- Təhlükəsizlik: sakit. 24 saatda 1 uğurlu giriş, uğursuz və bloklanmış yoxdur. CSP və HSTS yerindədir.
  Qeyd: buradan tokensiz /api/diag 200 qaytardı, çünki bu mühitin proksisi tokeni özü əlavə edir. Kod tokensiz 401 verir (test_diag yoxlayır).
- Sağlamlıq: versiya 965283b (budaqla eyni), /healthz 200, xəta yoxdur. Boş yaddaş 182 MB, DB 210 MB, açıq proqnoz 2000.
- Xəbərdarlıq: əlaqəli bazarlardan 3-ü gəlmir. Bu dəfə Dollar indeksi, Brent, VIX (əvvəlki yoxlamada VIX gəlirdi, istiqraz gəlmirdi): siyahı dəyişir, səbəb Blok 2-də araşdırılacaq.
- «Hadisə sürprizi»nin girişi yoxdur (FMP planında təqvim yoxdur, HTTP 402).
- Bu gün edilən: Strateq artıq 1 saat, 4 saat, 1 gün üçün ehtimal verir və Hakim onu yoxlayır (965283b).

## 2026-11-23, 22:48 NY (növbətçi yoxlama)
- Təhlükəsizlik: sakit. 24 saatda 1 uğurlu giriş, uğursuz və bloklanan yoxdur. CSP və HSTS yerindədir.
- Sağlamlıq: versiya c9a3bc0, /healthz 200, xəta yoxdur. Boş yaddaş 209 MB. **DB 525 MB** (500 həddini keçib):
  səbəb 4000 şamlıq yeni tarixçənin yenidən hesablanmasıdır; izlənir.
- Düzəldildi: qiymət sıçrayışı həyəcanı çox işləyirdi (bu gün 9/12, qızılın 0,2 %-lik adi hərəkətləri). İndi
  «adi hərəkət» yuxarı kvartil (gecə sakitliyi onu kiçiltmir), ən az 0,25 %; sıçrayışlar gündə ən çox 4 həyəcan
  işlədir, qalanı xəbər və rəqəmlər üçün qalır; həyəcanda X axtarışı yalnız güclü xəbər üçündür (Grok xərci).
- Xəbərdarlıq: ABŞ 10 illik istiqraz 1 saatdan çoxdur yeni qiymət vermir (axın).
- Beyinlərin ilk canlı hesabı (1 saat): həyəcandan sonra Strateq 88 % (17), İkinci beyin 100 % (12); saatlıq 38 % (8)
  və 55 % (11). 2-4 hadisədən gəlir: sübut deyil, izlənir.

## 2026-11-24, 01:49 NY (növbətçi yoxlama)
- Təhlükəsizlik: sakit. 1 giriş və 1 açar saxlanması (BLS, sahib tərəfindən), ikisi də yeganə tanınmış ünvandan.
  «Qiymət mənbəyi dəyişib» 7 dəfə yazılıb: hamısı eyni tanınmış ünvandan, Admin-də mənbə seçimi; şübhəli deyil.
- Sağlamlıq: versiya d6043aa, xəta yoxdur. Server 1 GB-a böyüdüldü (boş yaddaş 548 MB), gündəlik ehtiyat nüsxə açıqdır.
  DB 567 MB (4000 şamlıq tarixçə); 1 GB yaddaş və 10 GB disklə təhlükəli deyil.
- FMP «istifadə olunmur» (boz); BLS, FRED, Kalshi, ETF mənbələri işləyir.
- Düzəldildi: bugünkü (UTC) 12 həyəcanın 9-u məhdudiyyət qoyulmazdan əvvəl adi hərəkətlərə getmişdi; günün sayğacı
  bir dəfə sıfırlanır ki, bugünkü xəbər və rəqəmlər üçün həyəcan qalsın.
- Palladium gecə saatlarında sakitdir (saatda ~800 qiymət): zəncirdə bəzən «3/4 canlı» görünür, xəta deyil.

## 2026-11-24 gecə–səhər (NY 03:00–07:00) — sahibin tapşırığı ilə avtomatik iş

**Qurulanlar:**
- **Blok 15–19:** tam xərc, proqnoz kartı, hadisələr və mənbə yoxlayıcısı, əsas hədəflər və ALFRED, canlı agentlər xəritəsi.
- **Blok 20–21, 24:**
  - Databento 2 illik COMEX tarixçəsi alındı: 8,72 $, pulsuz kreditdən; 4 metal, ~2,4 mln dəqiqəlik şam.
  - Fyuçers sınaqları qurulub: impuls, xəbər dəqiqəsi, VWAP.
- **Blok 22–23:** yeni üsullar (şam fiqurları, Ichimoku, metal nisbəti, GARCH/GVZ aralığı) və Qrafik analitiki (AI).
- **Blok 25–29:** Bilik kitabı (27 qayda), qayda dedektorları və hər qaydanın ölçülməsi, beyinlərin qaydalarla işləməsi, gecə dərslərinin qayda təklifinə çevrilməsi və A/B sınağı.
- **Vahid proqnoz:**
  - Bütün analitiklər bir ehtimalda birləşir; sistem keçmişi addım-addım oynayıb özünü sınayır.
  - Paneldə «Sabah üçün proqnoz» tək cavab verir.
- **Uyğunlaşma:**
  - Sistemin vahid xəritəsi: `docs/SISTEM.md`.
  - Bütün beyinlərə ortaq ana məqsəd verilir.
  - Hakimdə Holm üsulu (eyni qoruma, daha az sərt).
  - Tək Hakim hökmü: kart, qərar lenti, «Sabah üçün proqnoz» və beyinlərin faktları eyni hökmü işlədir.
  - Ziddiyyət yoxlamasının 11 tapıntısı düzəldildi.

**Xəta (düzəldilib):**
- 10:31–11:05 UTC arasında canlı proqnoz verilmədi.
- Səbəb: Qrafik analitikinin fikir ailəsinin adı siyahıda yox idi (`KeyError`).
- Düzəliş: ad əlavə olundu; bütün ailələrin adı olduğunu yoxlayan test də əlavə olundu.

**Fyuçers sınaqlarının nəticəsi (2 il, xərcdən sonra):**
- Adi impuls 4 metalda da davam etmir: 45–50 %. Sahibin impuls fikri birja məlumatında təsdiqlənmədi.
- VWAP da işləmir: davam etmə 48 %, xərcdən sonra mənfi.
- Diqqətə layiq tapıntı: qızılda ABŞ rəqəmi dəqiqəsindəki impuls 60 dəqiqədə 63,5 % davam edib (104 hal, iki ildə də müsbət).
  - Sərt həddi keçməyib.
  - Canlı yoxlama üçün **H13** kimi əvvəlcədən qeyd olundu (12:00 UTC-dən sayılır).

**Diqqət:** verilənlər bazası böyüyür: fyuçers məlumatı, yeni üsulların tarixçəsi və qayda siqnalları. Disk yerinə həftəlik baxılmalıdır.

## 2026-11-24 07:48 NY — növbətçi yoxlama
- **Təhlükəsizlik:** təmiz.
  - Bloklanan ünvan yoxdur. 24 saatda 1 uğurlu giriş və 2 açar qeydi (Databento, BLS) olub, ikisi də tanış ünvandandır.
  - Təhlükəsizlik başlıqları yerindədir.
- **Server:** versiya 3f0f50e, xəta yoxdur. Sonuncu xəta 10:42 UTC-də olub, gecəki düzəldilmiş xətadır. Yaddaş: 161 MB istifadə olunur, 532 MB boşdur.
- **Düzəldildi (iki yalançı xəbərdarlıq):**
  - «Oxuyucu gözləyir»: eyni xəbərin surətləri də sayılırdı, halbuki onlar qəsdən oxunmur.
  - «Vaxtı keçib yoxlanmayan 129»: bazarın gündəlik fasiləsinə və həftəsonuna düşən proqnozlar da sayılırdı, halbuki onların şamı yoxdur və Hakim onları bir gündən sonra təxmin etmədən buraxır.
- **Bazanın ölçüsü:** 792 MB. Təklif `teklifler.md`-də yazılıb.

## 2026-11-24 13:30 NY — ikinci audit (iki müstəqil yoxlayıcı) və düzəlişlər
- **Kod xətaları düzəldildi:**
  - günlük proqnozlarda 2 saatlıq «gələcəyə baxma» (tarixçə yenidən hesablandı);
  - bir masanın xətası bütün dövrü dayandırırdı;
  - vaxtı keçmiş proqnozdan AL/SAT çıxa bilirdi;
  - tarixçə canlıdan fərqli qaydayla verilirdi;
  - kölgə ticarəti günlük sessiyanı səhv oxuyurdu;
  - Hedge eyni anı iki dəfə sayırdı;
  - mənbə yoxlayıcısı yuvarlaqlaşdırmanı «uydurma» sayırdı.
- **Metodologiya (sahibin təsdiqi ilə):**
  - **Şans səviyyəsi:** hər üsul öz şans səviyyəsi ilə ölçülür.
  - **Sübut pulla ölçülür:** tam xərcdən sonrakı orta nəticə; eyni fikri ölçən üsullar bir ailə sayılır.
  - **Xərc:** ödənilməsi mümkün olmayan masalar göstərilir.
  - **Al və saxla:** 1 həftədən uzun üfüqdə namizəddir.
  - **Yeni sınaq ailəsi:** V1–V5, 18:00 UTC-dən sayılır.
  - **Bağlanan hipotezlər:** H6 və H11 (xərc səbəbindən).
- **Yoxlama:**
  - 153 test keçir;
  - 6 səhifə kompüterdə və telefonda xətasızdır;
  - server sağlamdır: yeni xəta yoxdur, xəbərdarlıq yoxdur.

## 2026-11-25 01:48 NY — növbətçi yoxlama
- **Təhlükəsizlik:** sakit. Kənar giriş və bloklanmış ünvan yoxdur, başlıqlar yerindədir.
- **Xəta tapıldı və düzəldildi:** gündəlik fyuçers təzələməsi ilk cəhddə dayandı. Səbəb: `main.py`-da `log` adı təyin olunmamışdı, ona görə xəbərdarlıq yazmaq istəyəndə proses özü düşdü. Logger təyin olundu, test əlavə olundu. Hər cəhdin nəticəsi indi `futures:daily_try`-da saxlanılır və `/api/diag`-da görünür.
- **Baza:** 999 MB (tarixçə yeni qaydalarla yenidən hesablandı).

## 2026-11-25 04:47 NY — növbətçi yoxlama
- **Təhlükəsizlik:** sakit. Kənar giriş, bloklanmış ünvan, uğursuz giriş yoxdur; başlıqlar yerindədir; tanınan ünvan 1.
- **Server:** versiya 2663ce4 (kağız ticarət əlavə olundu, yenilənmədən dərhal sonra), /healthz 200. Yaddaş: 222 MB istifadədə, 467 MB boş.
  Yeni xəta yoxdur; siyahıdakı 3 xəta köhnədir (fyuçers `log` xətası artıq düzəldilib).
- **Axın:** 4/4 metal canlı, 8/8 əlaqəli bazar, mənbələrin hamısı işləyir. Yeganə «warn»: Xəbər və Fundamental bloklarında son gündə qayda işə düşməyib — şərt yaranmayıb, xəta deyil.
- **Baza:** 1014 MB (8 saatda +15 MB, böyümə yavaşlayıb). Təklif aşağıda.

## 2026-11-25 07:48 NY — növbətçi yoxlama
- **Təhlükəsizlik:** sakit. Kənar giriş, bloklanmış ünvan, uğursuz giriş yoxdur; başlıqlar yerindədir.
- **Sahib «sayt işləmir» dedi (NY ~05:20), səbəb tapıldı və düzəldildi (75632bb):** bütün oxumalar bir ortaq kilidi gözləyirdi;
  1 GB bazada uzun iş (hesabat, qayda hesabı) kilidi tutanda saytın kiçik sorğuları da növbədə qalırdı — ölçmədə /healthz 60 san cavab vermədi.
  İndi hər axının öz oxuma bağlantısı var (WAL), yazılar kilidlə qalır. Test əlavə olundu. Serverdə yoxlama: 64 saniyəlik hesabat
  işləyərkən 329 sorğunun hamısı keçdi, ən yavaşı 1,4 san.
- **Server:** versiya 75632bb, yeni xəta yoxdur, boş yaddaş 443 MB, baza 1023 MB. Yeganə «warn» əvvəlki kimidir (qayda şərti yaranmayıb).

## 2026-11-25 10:47 NY — növbətçi yoxlama
- **Təhlükəsizlik:** sakit. 24 saatda 3 uğursuz giriş (hədd 20), hamısı tanınan tək ünvandan; bloklanmış ünvan yoxdur; başlıqlar yerindədir.
- **Server:** versiya c610204 (AMFI, fərziyyə agenti, ssenari kartı), yenilənmədən 7 dəq sonra; yeni xəta yoxdur. Boş yaddaş 463 MB, baza 1031 MB.
- **AMFI:** işləyir — 14 ay yığılıb (son 2026-10 = +3 474 krore), qalan tarixçə 6 saatda 12 ay.
- **Rəqəm ovçusu «warn»:** bu gün ÜDM və PCE rəqəmlərini iki beyin eyni anda tapa bilmədi (biri tapdı, o biri yox) — qayda belədir, tək beyin rəqəmi işlədilmir.
  Bir halda Claude-un cavabı rədd olunmuşdu, çünki JSON-dan sonra mətn yazmışdı: düzəldildi (ilk tam JSON obyekti oxunur), test əlavə olundu.

## 2026-11-25 13:48 NY — növbətçi yoxlama
- **Təhlükəsizlik:** sakit. 24 saatda 3 uğursuz giriş (hədd 20), tanınan tək ünvan; bloklanmış ünvan yoxdur; başlıqlar yerindədir.
- **Server:** versiya 127f6b6 (Bazarlar arası və Vaxt blokları), 1,7 saatdır fasiləsiz işləyir, yeni xəta yoxdur. Boş yaddaş 425 MB, baza 1043 MB.
- **Yeni bloklar:** 15 CM/TM qaydası Hakimdə ölçülür; «bazar ertəsi» düzəlişindən sonra TM-DOW-1 də var (1 289 hal, 47 % — effekt yoxdur).
- **AMFI xətası tapıldı və düzəldildi:** 2025-ci ilin bəzi ayları .xls adı altında yeni .xlsx formatındadır, oxunmurdu.
  İndi hər iki format oxunur (may 2025 = +291,9 krore, xəbərlərlə eyni), test əlavə olundu.
- **Rəqəm ovçusu «warn»:** əvvəlki kimi (iki beyin eyni rəqəmi tapmadı) — qaydaya uyğundur.

## 2026-11-25 16:47 NY — növbətçi yoxlama
- **Təhlükəsizlik:** sakit. 24 saatda 3 uğursuz giriş (hədd 20), tanınan tək ünvan; başlıqlar yerindədir.
- **Server:** versiya 90b19b0, 2,9 saatdır fasiləsiz; yeni xəta yoxdur. Boş yaddaş 418 MB, baza 1051 MB.
- **AMFI düzəlişi serverdə təsdiqləndi:** xəta yoxdur, 28 ay yığılıb (əvvəl 16 + .xlsx aylar).
- «Qiymət axını 3/4»: 17:00–18:00 NY bazarların gündəlik fasiləsidir, xəta deyil.

## 2026-11-26 00:30 NY — vacib qeydlər
- **Təhlükəsizlik:** 25-26 noyabrda 3 uğursuz giriş cəhdi **Çindən (Pekin, Haidian)** olub — sahibin ünvanı deyil (əvvəlki
  jurnal qeydlərində «tanınan ünvandan» yazılmışdı: bu, yoxlanmamış ehtimal idi, səhvdir). Blok həddinə (15 dəqiqədə 5)
  çatmayıb. Yer DB-IP City Lite bazası ilə serverdə tapılır; diaqnostika ünvan yox, yalnız yer göstərir.
- **Sahibin qərarı:** «Sahibin kompüterindən istifadə etmə» qaydası ləğv olundu — lazım olanda Claude Remote Control ilə
  sahibin paylaşdığı qovluqda işləyə bilər (hər qoşulma sahibin təsdiqi ilə).
- **Yenidən başlamalar:** açılış jurnalı (`boots`) 9de1174-ün iki dəfə başladığını göstərir; xəta izində işləyən kod ilə
  diskdəki kodun fərqli olması diskin bir anlıq köhnə versiyaya qayıtdığını göstərir (yeniləmə skriptinin geri qaytarması
  ehtimalı). Yeniləmə jurnalı (`data/update.log`) növbəti yeniləmədən etibarən sübut verəcək.

## 2026-11-26 01:47 NY — növbətçi yoxlama
- **Təhlükəsizlik:** yeni hadisə yoxdur (24 saatda 3 səhv parol — Çin, Haidian; blok yoxdur). 2FA kodu serverdədir, sahib hələ açmayıb.
- **Yenidən başlamalar həll olunub:** səbəb — yeniləmədən sonra ilk cavab 35 san, köhnə skript 30 san gözləyib geri qaytarırdı.
  İndi 120 san; son iki yeniləmə 35 və 30 saniyədə keçib, sonra 2,4 saatdır fasiləsiz.
- **Baza 1157 MB** (+89 MB): «bazarlar» və «vaxt» səslərinin keçmiş hesabı yazılır (gözlənilən). Köhnə üsulların arxivini
  (1,15 milyon sətir) silmək təklifi sahibin cavabını gözləyir.

## 2026-11-26 10:48 NY — növbətçi yoxlama
- **Təhlükəsizlik:** sakit — 24 saatda uğursuz giriş yoxdur (Çin cəhdləri 24 saatdan çıxdı); 2FA hələ açılmayıb.
- **Server:** 7,3 saat fasiləsiz, xəta yoxdur; yeniləmədən sonra cavab artıq 5 saniyədə (köhnə arxiv silindikdən sonra).
- **Məlumat agentləri:** Gemini-nin bağlanmış modeli avtomatik `gemini-3.8-flash` ilə əvəzləndi, amma Google «kvota bitib»
  (HTTP 429) qaytarır — Gemini açarının hesabında ödəniş (billing) qurulmayıb. Agentlər susmasın deyə: iki beyindən biri
  texniki xəta verəndə üçüncü şirkətin beyni (Anthropic Haiku, veb axtarışı) əvəz edir; yenə iki fərqli şirkət razılaşmalıdır.

### 2026-11-26 13:48 (New York) — növbətçi yoxlama
- **Təhlükəsizlik:** sakit — 24 saatda uğursuz giriş yoxdur, bloklanan ünvan yoxdur, başlıqlar yerindədir; 2FA hələ açılmayıb.
- **Server:** versiya 3ea851f (son), 28 dəqiqə əvvəl yeniləndi (cavab 25 saniyədə), boş yaddaş 440 MB, xəta yoxdur.
  Baza 1157 MB — sabah 04:30 UTC-də VACUUM planlıdır (sahib təsdiqləyib).
- **İki «warn» normaldır:** bu gün ABŞ-da Şükran günüdür (Thanksgiving), birjalar bağlıdır — VIX gəlmir, dollar indeksi sakitdir;
  xəbər bloku bir gündür şərt tapmayıb.
- **Məlumat agentləri:** ehtiyat beyin texniki xətanı aradan qaldırdı (rbi_gold artıq «texniki xəta» yox, «rəqəmlər üst-üstə
  düşmür» yazır) — iki şirkət cavab verir, amma razılaşmır, ona görə qayda üzrə istifadə olunmur. Hələ uğurlu agent yoxdur.
