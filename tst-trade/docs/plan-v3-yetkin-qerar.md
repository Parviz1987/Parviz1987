# Plan v3 — yetkin qərar (2026-11-24)

Mənbələr: sahibin fikirləri (impuls, «öz gücümüz», zərgərlik təsirsizdir, festivallar agentlərin işidir),
PDF #1 (Radar Gold dizaynı), PDF #2 (AI_Trading_Derin_Arasdirma_AZ), sahibin göndərdiyi iş ardıcıllığı sxemi və
cədvəllər, öz ölçmələrimiz (Hakim, impuls araşdırması), internet araşdırması.

## 1. Əsas nəticə

Sistemimizin güclü tərəfi **sürət deyil, intizamdır**: hər proqnozu vaxtı ilə yazmaq, xərcdən sonra dürüst ölçmək və
çoxlu mənbəni birləşdirmək. Sürətdə böyük oyunçulara uduzuruq:
- elmi işlər: qızıl fyuçersi makro xəbərə reaksiyanın çoxunu **90 saniyədə** bitirir (Smales və Yang, 2015);
  fyuçerslərdə qiymət dəyişməsinin çoxu xəbərdən sonrakı **ilk dəqiqədə** baş verir (Ederington və Lee, 1993);
- E-mini fyuçersində sifariş axınının təsiri **bir saniyədə** sönür (Takahashi, 2025);
- bizim ölçmə: qızılda 1 dəqiqə gecikmə ilə impulsun arxasınca getmək 45–50 % tutur, yəni pul qazandırmır.

Deməli, üstünlüyü 3 yerdə axtarırıq:
1. **Saatlar və günlər**: məlumatın yavaş yayıldığı yer (Fed gözləntisi, real faiz, dollar, ETF axını, mövqelər).
2. **Platin və palladium**: bazar dayazdır, impuls davam edir (67–83 %), amma Capital spredi qazancı yeyir.
   Spredi kiçik bir alətdə yoxlanmalıdır.
3. **Risk və diapazon**: diapazonlarımız artıq kalibrlidir (50 / 80 %). Bu, artıq sübut olunmuş bacarıqdır.

## 2. Sxem ilə sistemimiz: nə var, nə çatmır

| Sxemdəki qutu | Bizdə | Çatmayan |
|---|---|---|
| Rəsmi və bazar məlumatları | Gözlər: Capital, FRED, BLS, Kalshi, ETF, xəbər, X | real birja həcmi və «kim aldı/satdı» (fyuçers) |
| Vaxt, mənbə, keyfiyyət yoxlaması | köhnə qiymət yoxlaması, known_ts | ilk dərc olunmuş rəqəm (ALFRED), eyni xəbərin bir hadisə sayılması |
| Fayldakı metodlar | Hakimin metodları | — |
| Hesab və sınaq modeli | Hakim: xərc, Bonferroni, üst-üstə düşən proqnozlar n/k sayılır | — |
| Mənim təhlilim | Strateq, müzakirə, oxuyucu | — |
| Ehtimal, interval, ssenarilər | kalibrasiya, diapazon | əks ssenari, zəifləmə şərti |
| Proqnoz və ya gözlə | risk qapısı, AL/SAT/GÖZLƏ | «gözlə» payının açıq göstərilməsi |
| Dəyişməz proqnoz jurnalı | proqnozlar cədvəli | dondurulmuş kart: məlumat, model, prompt versiyası, ssenarilər, keyfiyyət |
| Sonrakı faktiki nəticə | dürüst hesablama | — |
| Dəqiqlik və səhv təhlili | Hakim, gecə yuxusu | səhvin 6 səbəb üzrə növü |
| Dəyişiklik təklifi və ayrıca sınaq | H1–H8 əvvəlcədən qeydə alınıb | yeni təkliflərin H9+ kimi avtomatik qeydi |

## 3. Proqnoz kartı (sahibin cədvəli əsasında)

Hər əsas proqnoz bu sahələrlə dondurulur və silinmir:
alət və an · müddət · əsas ssenari · ehtimal (yalnız kalibrlidirsə, yoxsa «ölçülməyib») · interval və onun ölçülmüş
əhatəsi · əks ssenari · zəifləmə şərti · məlumat keyfiyyəti · növbəti yenilənmə (vaxt və ya hadisə) · versiya (commit,
model, prompt izi).

Əsas hədəflər: **XAU, 1 gün və 1 həftə**, üstəlik hadisə pəncərəsi (1 saat). Qalan masalar ölçülməyə davam edir.

## 4. Mərhələlər

**Mərhələ 1, pulsuz, ~1 həftə**
- A. Dizayn: agentlər xəritəsi. Hər agent yerində durur, real hadisə gələndə işıqlı «kuryer» onu növbəti agentə
  daşıyır; işləyən agent parlayır.
- B. Jurnal katibi: proqnoz kartı (bölmə 3).
- C. Hadisə birləşdiricisi: eyni xəbər bir hadisə sayılır və nömrə alır.
- D. Arxivçi: ALFRED-dən ilk dərc olunmuş rəqəmlər (tarixi sınaqlar üçün).
- E. Səhv təhlili: gecə yuxusu səhvi 6 növə ayırır (məlumat, gözlənti, model, rejim, proqram, təsadüf). Yeni
  təkliflər H9+ kimi qeydə alınır.

**Mərhələ 2, Databento tarixi məlumatı (yeni hesaba $125 pulsuz kredit verilir)**
- COMEX GC, MGC, PL, PA: 1–2 illik dəqiqəlik şamlar və əməliyyatlar. Almadan əvvəl `get_cost` ilə qiymət
  sahibə göstərilir.
- Sınaqlar əvvəlcədən qeydə alınır (H9+):
  1. impuls real həcmlə və alıcı/satıcı tərəfi ilə;
  2. xəbərdən sonra 90 saniyədən 60 dəqiqəyə qədər sürüşmə;
  3. platin və palladium fyuçers spredi ilə.
- Qapı: yalnız xərcdən sonra sübut çıxsa, mərhələ 3-ə keçilir.

**Mərhələ 3, sübutdan sonra**
- Canlı fyuçers məlumatı: Databento Standard ($199/ay + CME şəxsi lisenziyası) və ya IBKR COMEX L1 (~$1,25/ay,
  broker hesabı lazımdır).
- Yeni agent «Axın ovçusu»: saniyələrdə böyük həcm və alıcı/satıcı dengəsizliyi.
- Alqı-satqı yalnız sahibin qərarı ilə; əvvəl kağız üzərində sınaq.

## 5. Rədd edilənlər

- Zərgərlik və lom tələbi dünya qiymətinə təsir etmir.
- Ağır karkaslar: React, LEAN, Postgres, Redis.
- Sübutsuz aylıq abunə.
