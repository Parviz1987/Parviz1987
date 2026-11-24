# Plan v3: yekun, vahid qərar (2026-11-24)

Bu sənəd nələrə əsaslanır:
- sahibin 22–24 noyabr mesajlarının hamısı (səsli izahlar, yazılar, şəkillər);
- ChatGPT mətni və sxemi;
- PDF #1 «Radar Gold» (8 səhifə);
- PDF #2 «AI Trading Dərin Araşdırma» (43 səhifə; 36–43-cü səhifələr PDF #1-in təkrarıdır);
- serverdəki real ölçmələrimiz;
- internet araşdırması.

## 1. Hədəf (sahibin sözləri ilə)

Metalların qalxacağını və düşəcəyini əvvəlcədən, səbəbi ilə bilmək:
- qısa müddətdə (dəqiqələr, saat);
- uzun müddətdə (gün, həftə, ay).

Hansı müddətdə nə qədər uğurlu olduğumuzu dəqiq bilmək və yalnız orada addım atmaq. Sonra sistem sahibin
qoyduğu limitlə özü alıb-satsın.

Sistem canlı orqanizm kimi işləsin: xəbər gələn kimi analitiklər oyanır, Hakim analitikləri tərəzidə çəkir. Beyinlər
asanlıqla dəyişdirilə bilsin, açarlar Admin-də olsun. Hər şey insan üçün aydın görünsün. Yamaq, artıq şey və
şişirtmə olmasın.

## 2. İstəklər və vəziyyət

| İstək | Vəziyyət |
|---|---|
| 4 metal canlı qiyməti, şamlar, qrafiklər, telefon (PWA) | ✅ |
| Açarlar Admin-də, beyinlər dəyişdirilə bilən yerlərdə | ✅ |
| Analitiklər: texniki, Fibonacci, fundamental, xəbər, makro | ✅ 18+ metod |
| Neft, dollar, faiz, S&P, VIX panelda | ✅ |
| Hakim: hər müddətdə neçə faiz tutduğunu xərcdən sonra göstərir | ✅ |
| Sinir sistemi: xəbər, rəqəm, sıçrayış beyinləri dərhal oyadır | ✅ |
| Gecə öyrənməsi, kalibrasiya, tərəzi (Hedge) | ✅ |
| Risk qapısı, AL/SAT/GÖZLƏ | ✅ yalnız göstərir |
| Agentlər paneli: kürə, kartlar, zaman xətti, x1/x10/x50 təkrar | ✅ |
| Hər 3 saatda nəzarət, həftəlik hesabat | ✅ |
| Agentlərin bir-birinə məlumat daşıması canlı görünsün | ⚠️ yalnız mərkəzdən agentə nöqtələr gedir |
| Proqnoz kartı: əks ssenari, zəifləmə şərti, versiya | ❌ |
| Real birja həcmi, «kim aldı/satdı» | ❌ Capital vermir |
| Sistemin limitlə özü alıb-satması | ❌ sübutdan sonra; əvvəl pozisiya, gündəlik zərər və təcili dayandırma qaydaları lazımdır |

## 3. Bugünkü real nəticə

| Nə | Nəticə |
|---|---|
| Qiymət aralığı | ✅ 50 % və 80 % aralıqları düz tutur. Yeganə sübut olunmuş bacarıqdır |
| İstiqamət | ❌ 516 cütdən heç biri sübut keçmədi |
| AI beyinlər | ❌ hələlik sadə modeldən zəifdir. Az hal var, hökm üçün tezdir |
| İmpuls (qızıl, gümüş) | ❌ 45–53 % |
| İmpuls (platin, palladium) | ⚠️ 67–83 % davam edir, amma Capital spredi qazancı yeyir. Cəmi 2 günlük məlumatla |

## 4. Mənbələr: dürüst müqayisə

| Mənbə | Nə verdi | Şişirtmə və ya zəif tərəfi |
|---|---|---|
| Sahibin fikirləri | Sinir sistemi (quruldu); impuls (sınandı, platinə yönəltdi); zərgərlik düzəlişi (doğrudur) | Saniyə yarışında biz uduzuruq |
| ChatGPT mətni | Düzgün metod, təxminən 70 %-i bizdə var. Yeni: proqnoz kartı, «fokuslan», ALFRED, eyni xəbəri bir saymaq | Qazanc mənbəyi vermir |
| PDF #1 | Görünüş (quruldu); hadisə formatı; deterministik risk qaydaları | Təxminən 70 %-i görünüşdür; özü də deyir: «effekt AI-ni sübut etmir». React, Postgres, Redis bizim qaydalara ziddir |
| PDF #2 | «Yoxlanmış canlı qızıl qazancı tapılmadı»; sübut pilləkəni; versiya manifesti; swap xərci; sınaq protokolu | Səhmlərdəki +26 %, +85 % nəticələri qızıl üçün sübut deyil; PDF özü də bunu deyir |
| İnternet araşdırması | Qızıl xəbərə 90 saniyədə reaksiya verir; sifariş axınının təsiri 1 saniyədə sönür | — |

## 5. Nəticə niyə yoxdur: real səbəblər

1. Qısa müddətdə qiymət demək olar ki, təsadüfi hərəkət edir. Böyük oyunçular xəbəri saniyələr ərzində qiymətə salır.
2. Eyni anda çox şey yoxlayırıq (4 metal × 6 müddət × onlarla metod). Ona görə həqiqi, amma kiçik üstünlük sübut
   həddini keçə bilmir.
3. Capital-da real həcm və alıcı/satıcı tərəfi yoxdur, platin və palladiumda isə spred böyükdür.
4. Xərc tam hesablanmır: gecəlik saxlama haqqı (swap) çıxılmır. Bu, 1 gün və daha uzun nəticələri olduğundan yaxşı
   göstərir.
5. Beyinlər az yoxlanıb; dürüst ölçmə yenicə başlayıb.

Karkas səhv deyil. Ölçmə dürüstdür, sadəcə hələ üstünlük göstərmir.

## 6. Yekun qərar

**Götürürük** (fayda sırası ilə):
1. Fokus: XAU 1 gün və 1 həftə, üstəlik platin və palladiumda impuls. Qalanlar ölçülməyə davam edir.
2. Databento tarixi məlumatı: COMEX GC, MGC, PL, PA, 1–2 il. Yeni hesaba verilən $125 pulsuz kredit, çox güman,
   bəs edər.
3. Tam xərc: swap və sürüşmə (slippage) xərcdən sonra hesablanan nəticəyə daxil edilir.
4. Proqnoz kartı və manifest: hər proqnozla commit, model, prompt izi, əks ssenari, zəifləmə şərti və məlumat
   keyfiyyəti saxlanılır.
5. Hadisə nömrəsi: eyni xəbər bir hadisə sayılır; agent hadisələri ardıcıl nömrələnir.
6. Mənbə yoxlayıcısı: beyin cavablarındakı uydurma və ya vaxtı səhv faktları sayır.
7. Dizayn: agentlər öz yerlərində durur, real hadisə gələndə işıqlı kuryer zəncir boyu qaçır.
8. Parametr dayanıqlığı və tam hesabat: Sharpe, ekspozisiya, müqayisə modeli.
9. ALFRED: makro sınaqlar üçün.
10. Ticarətdən əvvəl: pozisiya limiti, gündəlik zərər limiti, təcili dayandırma. Hamısı kodda olur, beyin dəyişə
    bilməz.

**Rədd edirik:** React, Three.js, Postgres, Redis, LEAN, Nautilus, zərgərlik məlumatı, sübutsuz aylıq abunə, yeni AI
beyinlər (mövcud beyinlər sadə modeli keçənə qədər).

**Mərhələlər:**

| Mərhələ | Nə | Xərc | Keçid şərti |
|---|---|---|---|
| 1 | 1, 3, 4, 5, 6, 7 | pulsuz | testlər keçir, serverdə işləyir |
| 2 | 2, 8 və əvvəlcədən qeydə alınmış sınaqlar (H9+) | $125 kredit daxilində | xərcdən sonra sübut |
| 3 | canlı fyuçers məlumatı, Axın ovçusu, 10, kağız üzərində ticarət | $199/ay + lisenziya (və ya IBKR) | kağız nəticə sübutu |
| 4 | real ticarət, sahibin limiti ilə | sahibin qərarı | — |
