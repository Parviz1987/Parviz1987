# Sinir sistemi: TST Trade necə işləməlidir (ümumi şəkil və blok təlimatı)

Bu sənəd sistemin xəritəsi və **işin ardıcıllığı üçün təlimatdır** (həm sahib, həm Claude üçün). Kod dəyişəndə bu
sənəd də yenilənir. Yeni istək gələndə əvvəl buraya, «Gözləmə siyahısı»na yazılır; cari blok bitmədən başqa bloka
keçilmir.

## Ana hədəf

Qızıl, gümüş, platin, palladiumun **qalxacağını və ya düşəcəyini əvvəlcədən** bilmək (15 dəqiqə – 1 ay), səbəbini
bilmək və Hakimin sübutu olan yerdə (xərcdən sonra) addım atmaq. Ölçü: Hakimin «sübut» statusu + kölgə ticarətinin
100+ sövdələşmədə xərcdən sonra müsbət orta nəticəsi.

## Orqanizm: 5 qat

```
 GÖZLƏR (məlumat)          SİNİRLƏR (siqnal)        BEYİN (təhlil)            HAKİM (yoxlama)        ƏL (addım)
 qiymət axını (saniyə) ─┐                         ┌─ Oxuyucu (başlıq → metal,  ┌─ hər üsul, hər beyin  ┌─ kölgə ticarəti
 8 əlaqəli bazar        ├─► siqnal lenti ──────►──┤   istiqamət, güc)          │   ayrıca hesab         │   (kağız üzərində)
 xəbər lentləri, Grok X │   (signals cədvəli)     ├─ Strateq (bütün faktlar →  ├─ «harada işləyir»     └─ sonra: sahibin
 iqtisadi təqvim        │   «nə oldu, nə qədər    │   1s/4s/1g ehtimal+səbəb)  │   (sessiya, əhval)        qərarı ilə real
 rəqəm ovçusu (fakt)    │    güclü, hansı metal»  ├─ Rəqəm ovçusu (iki beyin)  ├─ analitikləri tərəzi-
 FRED, COT              ┘                         └─ 18 hesab üsulu (şamlar)   │   də çəkmək (çəki)
                                                                               └─ konsensus (yalnız sübutlular)
```

### Qaydalar
1. **Saat gözləmək yox, hadisəyə reaksiya.** Güclü siqnal gələn kimi təhlil dərhal işə düşür (həyəcan). Saatlıq
   təhlil yalnız sakit vaxt üçün ehtiyatdır.
2. **Hər fikir yazılır və yoxlanır.** Beyinin hər proqnozu (vaxtı, səbəbi, hansı siqnaldan doğduğu) saxlanır; Hakim
   vaxtı çatanda real qiymətlə yoxlayır. Sübutu olmayan fikir qərara təsir etmir.
3. **Qiyməti yalnız bazar verir**, beyin heç vaxt qiymət uydurmur.
4. **Xərc nəzarəti**: hər beyinin aylıq limiti var; həyəcan təhlili gündə məhdud saydadır.
5. **Bir yol, təkrar yox**: hər məlumat bir yerdən gəlir, hər qərar bir yerdə verilir.

### Siqnallar (sinirlər) — nə həyəcan sayılır
| Siqnal | Mənbə | Şərt |
|---|---|---|
| Güclü xəbər | Oxuyucu | güc 3 (bazarı tərpədən) başlıq: müharibə, Fed, sanksiya... |
| Xəbər axını | Oxuyucu | 15 dəqiqədə eyni metala eyni istiqamətdə 2+ güclü (2+) başlıq |
| ABŞ rəqəmi çıxdı | Rəqəm ovçusu / təqvim | iki beyin faktı təsdiqlədi |
| Qiymət sıçrayışı | şamlar | 15 dəqiqəlik hərəkət son 2 günün adi hərəkətindən 4 dəfə böyük (metal və ya dollar, neft, istiqraz, VIX) |

Həyəcan → (lazımsa Grok X-də dərhal axtarır) → Strateq bütün faktlarla + «nə baş verdi» ilə 1s/4s/1g ehtimal verir →
Hakim yoxlayır. Həyəcan fikirləri ayrıca da hesablanır ki, «hadisədən sonra beyin nə qədər düz deyir» bilinsin.

## Bloklar (ardıcıllıq; biri bitmədən o biri başlamır)

| Blok | Nə | Bitdi meyarı | Vəziyyət |
|---|---|---|---|
| 1 | Beyin proqnozçu: Strateq 1s/4s/1g ehtimal verir, Hakim yoxlayır | Hakimdə «Strateqin fikri» canlı istiqamət sayır | ✅ işləyir (965283b): Hakimdə ilk canlı istiqamət sayıldı |
| A | Sinirlər: siqnal lenti + həyəcan təhlili (yuxarıdakı cədvəl) | güclü xəbər/rəqəm/sıçrayışdan sonra 15 dəqiqəyə qədər Strateq fikri yazılır; Agentlər panelində görünür | ✅ işləyir: ilk həyəcan 2026-11-23 20:07 NY (qızıl sıçrayışı + Fed xəbərləri) → Grok axtardı → 20:12 NY Strateq fikri (f4f1709) |
| 2 | Gözlər tam: 8/8 əlaqəli bazar; pulsuz uzun tarixçə | Sistem səhifəsində zəncir yaşıl | növbəti |
| 3 | Tərəzi: Hakim hər analitikin (üsul, beyin, həyəcan fikri) çəkisini nəticəyə görə verir; konsensus çəki ilə | Nəticələr səhifəsində analitik cədvəli | növbədə |
| 4 | Yeni üsullar: COT, mövsümilik, zərgərlik təqvimi; ikinci beyin (OpenAI) ehtimalı | hər biri Hakimdə | növbədə |
| 5 | Ölçmə 2-4 həftə, həftəlik hesabat, sübut olan yerdə kağız ticarəti | «harada işləyir» siyahısı | növbədə |

## Sahibin işləri
- Məcburi heç nə yoxdur. Açarlar artıq yerindədir (Capital, Twelve Data, OpenAI, Anthropic, xAI, FRED, Alpaca, FMP).
- İstəyə görə: FMP Starter (~29 $/ay) — ABŞ rəqəmlərinin **keçmiş** faktlarını verir (sürpriz üsulunu keçmişdə
  yoxlamaq üçün). Canlı faktları rəqəm ovçusu (iki beyin) onsuz da tapır.

## Gözləmə siyahısı (yeni istəklər, sırası gələndə)
- (boş)
