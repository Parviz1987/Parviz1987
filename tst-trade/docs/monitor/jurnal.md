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
