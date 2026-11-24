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
