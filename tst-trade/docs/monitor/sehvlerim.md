# Səhvlərim siyahısı (Claude, plan addımı 2/8): hər yoxlamadan əvvəl oxunur

| Tarix | Nə dedim / etdim | Düzü | Bir daha necə yoxlayıram |
|---|---|---|---|
| 2026-11-26 | Uğursuz girişlər «sizin ünvanınızdandır» dedim | Çindən (Pekin) idi | Ünvanı geo-IP ilə yoxlayıb sonra deyirəm |
| 2026-11-26 | «Backup yoxdur» dedim | DigitalOcean gündəlik backup var | Xidmətin öz API-sindən yoxlayıram |
| 2026-11-26 | «Heartbeat bizdə var» dedim | Dostun repo-sunda idi, bizdə yox | Faktı bizim repo-da `grep` ilə tapıram |
| 2026-11-26 | Gemini dəqiqəlik 429-u «ödəniş yoxdur» saydım (koda yazdım) | Google hər 429-a «billing» sözü yazır | Real xəta mətnləri ilə test yazıram |
| 2026-11-26 | Ehtiyat mənbəyə keçid sonrası qayıdışı «təkrar nasazlıq» saydım | Qayıdış nasazlıq deyil | «İkinci dəfə də işləyirmi?» testini yazıram |
| 2026-11-26 | FRED release/dates cavabını hazır obyekt kimi oxudum, tarixlər yazılmadı | `_get` xam mətn qaytarır | Yeni mənbədə əvvəl saxta cavabla test yazıram |
| 2026-11-26 | Testlər qırmızı ikən «;» ilə commit və push etdim | Test yalnız mənim yeni testim idi, kod düzgün idi | `set -o pipefail` + `&&`: testin xəta kodu `tail`-dən keçəndə itirdi; indi push yalnız yaşıl testdən sonra |
| 2026-11-27 | Diaqnostika açarını yeniləməyi dedim, amma yeni açarın hara yazılacağını eyni anda tam demədim | Açar Admin-də dəyişəndə köhnəsi dərhal işləmir, yenisi mühitin «Network secrets» bölməsinə yazılmalıdır | Açar/parol addımını həmişə bütöv verirəm: harada yaradılır, hara yazılır, nə vaxt işə düşür |
| 2026-11-26 | Bloklar xəritəsində «gecəlik R2 nüsxə ✅» yazılmışdı | R2 açarı heç saxlanmayıb, nüsxə getmir (yalnız DigitalOcean nüsxəsi var) | «Hazır» yazmazdan əvvəl serverin öz statusunu (diag `learning.backup`, `keys`) oxuyuram |
| 2026-11-26 | Dizayn yeniləməsindən sonra «serverdə canlıdır» dedim | Sahibin brauzeri köhnə saytı göstərirdi: səhifə və statik fayllarda Cache-Control yox idi, brauzer köhnə nüsxəni saatlarla işlədirdi | Deploydan sonra `curl -I` ilə başlıqları və yeni faylı yoxlayıram; səhifələr no-cache, `nav.js` yeni versiyada özü yeniləyir (test `test_cache_headers.py`) |
| 2026-11-26 | Fundamental səhifəsini yalnız masaüstündə və DEMO məlumatla sınadım | Telefonda sürüşdürmə «resize» verir; səhifə hər dəfə 16 qrafiki yenidən qururdu (sahibdə səhifə bağlanırdı — ehtimal) | Telefon ölçüsündə hündürlük dəyişməsini də sınayıram; qrafik yalnız en dəyişəndə yenidən qurulur |
| 2026-11-27 | Xəbər bloku «ardıcıl səhv, şansdan 10–22 bənd pis» dedim | Şansı dövrün ümumi meyli ilə hesablamışdım; Hakimin ölçüsü (eyni anlar, eyni yuxarı/aşağı qarışığı) ilə şansdan fərqi yoxdur — o danışanda qızıl adi vaxtdan çox qalxıb | Sistemdə «şans» yalnız Hakimin düsturu ilədir (scoreboard da ona keçdi); yeni müqayisədə əvvəl Hakimin ölçüsü ilə yoxlayıram |
