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
| 1 | Beyin proqnozçu: Strateq 1s/4s/1g ehtimal verir, Hakim yoxlayır | Hakimdə «Strateqin fikri» canlı istiqamət sayır | ✅ (965283b) |
| A | Sinirlər: siqnal lenti + həyəcan təhlili; beyinlərin öz dövrü | güclü xəbər/rəqəm/sıçrayışdan sonra 15 dəq içində Strateq fikri | ✅ ilk həyəcan 2026-11-23 20:07 NY → 20:12 NY fikir (f4f1709) |
| 2 | Gözlər tam: «sakit» bazar ilə «gəlməyən» bazar ayrıldı; tarixçə brokerdə səhifə-səhifə 4000 şama | Sistem səhifəsində əlaqəli bazarlar yaşıl; 15 dəq tarixçə ~40 gün | ✅ kod (eac4272) |
| 3 | Tərəzi: hər analitikin çəkisi Hakimin ölçüsü ilə; Nəticələr 5-ci bölmə; beyinlərin öz hesabı (həyəcan / saatlıq) | Nəticələr səhifəsində analitik cədvəli | ✅ (1c4e1e8) |
| 4 | Yeni üsullar: COT, mövsümilik, zərgərlik təqvimi; İkinci beyin (OpenAI) | hər biri Hakimdə | ✅ (1c4e1e8) |
| 5 | Ölçmə: həftəlik hesabat (bazar ertəsi, bu söhbətdə), 3 saatlıq növbətçi yoxlama | hər həftə: «harada işləyir» siyahısı | ✅ quruldu; nəticə 2-4 həftəyə |

### Hər analitikin yeri (kim nəyi kimə ötürür)
- Qiymət axını → şamlar → 21 analitik (18 hesab üsulu + 3 yavaş üsul) → Hakim
- Xəbər lentləri + Grok → Oxuyucu → «Xəbər əhvalı» üsulu + siqnal lenti
- Təqvim → Rəqəm ovçusu → «Hadisə sürprizi» + siqnal lenti
- Şamlar (metal və 8 bazar) → sıçrayış siqnalı
- Siqnal lenti → həyəcan → (Grok) → Strateq + İkinci beyin → «Strateqin fikri», «İkinci beyin» üsulları
- Hakim → çəkilər → Tərəzi; ailələr → Seçici konsensus → Nəticələr və kölgə ticarəti
- Hər agent öz vəziyyətini mərkəzə yazır → Agentlər paneli (/agents)

## Sahibin işləri
- Ətraflı: `docs/acarlar.md`. Məcburi heç nə yoxdur; FMP Starter yalnız istəyə görə.

## Gözləmə siyahısı (yeni istəklər, sırası gələndə)
- 2026-11-24 «Radar Gold texniki arayış» (sahibin PDF-i). Götürülə bilənlər, sahibin qərarı ilə:
  1) hadisə zənciri: hər hadisəyə ümumi id (siqnal → beyin → proqnoz → Hakim), Agentlər panelində «niyə» izi;
  2) risk mühərriki (maks. mövqe, gündəlik zərər limiti, köhnə qiymət bloku, təcili dayandırma) — yalnız sübut
     tapılandan sonra, kağız ticarətindən əvvəl;
  3) «yuxarı / aşağı tərəfdarı» beyin müzakirəsi (TradingAgents ideyası) — həyəcanlarda sınaq üsulu kimi.
  Götürülmür: React/Next, PostgreSQL/Redis, LangGraph, 3D WebGL (sadə stek qaydası; dəqiqliyə təsiri yoxdur).
