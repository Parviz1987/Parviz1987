# Söhbət tarixçəsi — sahiblə Claude arasında nə danışılıb, nə qərar verilib, nə qurulub

> **Kim üçün:** hər yeni Claude sessiyası. Köhnə söhbət («Pj Trade Gold repository review», 22–27.11.2026) arxivə
> gedir; yeni sessiya onu oxuya bilmir, ona görə vacib olan hər şey buradadır. Ətraflı: `BLOKLAR.md` (bloklar),
> `IS-PLANI.md` bölmə 5 (qərarlar), `monitor/` (jurnal, səhvlər, təkliflər), `research/` (araşdırmalar).

## 1. Sahib kimdir, necə danışmaq
- Qızıl, brilliant, saat sahəsində təcrübəli; New York-da; proqramlaşdırmada başlanğıc, sistem düşüncəsi güclüdür.
- Azərbaycan dilində (bəzən rus), sadə və hörmətli; termini ilk dəfə izah et; vaxtlar **New York saatı** ilə.
- Əvvəl əsas fikir və səbəb, sonra izah. Qısa suala qısa cavab. Texniki siyahıları ondan soruşma
  («Mən onu bilə bilmərəm … sən özün ayarlamalısan»).
- **Məsuliyyəti ona atma:** «Məsuliyyəti öz avtomatlaşdırmadan çıxardıb mənim üzərimə atmaq lazım deyil». Sistem
  avtomatik işləməlidir; sahibdən yalnız: pul, real ticarət, açar/model, məlumat silmək, blok çıxarmaq, Hakim
  siyasətini dəyişmək.
- Açar/parol addımını **bütöv** ver: harada yaranır, hara yazılır, nə vaxt işə düşür (27.11 səhvi, `sehvlerim.md`).
- Ekran şəkli göndərəndə düymə adlarını ekrandakı kimi (rusca) de.

## 2. Ana hədəf
Metalların (XAU, XAG, XPT, XPD) qalxıb-düşəcəyini və aralığını əvvəlcədən bilmək — **Hakimin xərcdən sonrakı
sübutu ilə**. Sübut olmayan heç nə pula (hətta kağız ticarətə) getmir. Real pul — yalnız sahibin qərarı.

## 3. Bu söhbətdə alınan qərarlar (xronologiya)
1. **12 plan addımı** (26.11) bir-bir müzakirə olundu, hamısı qəbul — `IS-PLANI.md` bölmə 5.
   - s1 kənar nəzarətçi (13 siqnal, 4-ü təcili Telegram-a); s2 «Merge düyməsi yox», Claude 8 qoruyucu qatla özü
     işləyir, qorunan fayllar `Sahib-təsdiqi:` sətri ilə; s3 siyahıları Claude özü seçir; s6 Gemini saxlanılır
     (sahib ödənişli açar qoydu); s7 beyin keçidi qaydası (eyni şirkət + sınaq pis deyil + qiymət ≤ +20 %);
     s9 ACI əvvəl keçmişdə; s10 dirijor kölgədə; s11 səhv yarılması; s12 gücləndirilmiş 9 qatlı Hakim.
2. **Blok qərarları 5.1:** mövsüm/zərgərlik → dalğalılıq bayrağı (kölgə); gecə dərsləri dayandırıldı;
   fundamental 3 illik pəncərə (kölgə).
3. **Avtomatik Hakim siyasəti** (26.11, bir dəfə təsdiq): bal 0–100 (ən zəif hissə), pillələr 50/70/85,
   bir üsul ≤ 25 %, gündə 2 % stop, zirvədən 10 % düşmədə hər şey dayanır. `app/autojudge.py` (qorunur).
4. **Keçmiş məlumat 5.2** (27.11: «Kitabxananı qur, ara yolu da et»):
   - Hadisələr kitabxanası `app/eventlib.py` — ABŞ rəqəmləri (CPI, NFP, ÜDM, PCE), Fed qərarları, **geosiyasət**
     (GDELT, sahibin 27.11 istəyi). Beyinlərə yalnız kölgə sınağından keçən hissə.
   - Ara yol: keçmişdə balı ≥ 70 üsul canlıda tez kölgəyə; kağız ticarət üçün canlı sübut şərt.

## 4. Sahibin suallarına verilən əsas cavablar (təkrar soruşulsa)
- **«21 blok neçəsi hazırdır?»** (27.11): 12 hazır və işləyir, 9 qurulub və işləyir amma xərcdən sonra sübut
  gözləyir, 0 dayanıb. İndi 22 blok (22 = hadisələr kitabxanası). Çatışmayan kod deyil, **zaman və real nəticə**.
- **«Bloklar bir-biri ilə əlaqəlidirmi?»** Bəli: qiymət → 6 blokun səsi → vahid proqnoz (çəkilər keçmiş nəticədən)
  → Hakim → Avtomatik Hakim → risk/kağız ticarət → öyrənmə çəkiləri geri qaytarır. Dirijor və ACI kölgədədir.
- **«Sübut nə vaxt?»** Ən tez 1 saatlıq masalarda (dekabrın ortası həcm, ən erkən kiçik kağız payı dekabrın 2-ci
  yarısı); 1 gün+ horizontlar canlı sübutla ~1 il. Heç biri keçməyə də bilər — bu da faydalı nəticədir.
- **«Planı nəyə əsasən qurmusan?»** 1) sahibin qərarları, 2) 4 dərin araşdırma (`research/`), 3) serverin öz
  rəqəmləri, 4) Claude-un öz biliyi (ən zəif, açıq deyilir).

## 5. Vəziyyət (27.11 səhər, New York)
- Server: https://tsttrade.duckdns.org, budaq **`claude/amazing-keller-c4hwfl`** (yalnız buradan yenilənir).
- Xəbər qaydaları işləyir (26.11 düzəlişi). Kitabxana: 704 hadisə; GDELT tarixçəsi 429 səbəbindən hissə-hissə dolur.
- Avtomatik Hakim: 89 üsulun hamısı «söndürülüb» (xərcdən sonra müsbət yoxdur); erkən kölgə yoxdur.
- 27.11 düzəlişi: beyin cavabları çıxış həddində kəsilirdi (qrafik analitiki, analitik 2) — hədd artırıldı,
  kəsilmə adı ilə yazılır; `agents.router.failed_recent` ilə yoxla.
- Diaqnostika açarı 27.11 yeniləndi, mühitin «Сетевые секреты» bölməsindədir, işləyir.

## 6. Açıq işlər
- **Sahibin:** 2FA; Healthchecks.io açarı; Admin → Əməliyyatlar → WAL araşdırma kartını bağlamaq.
- **Claude-un:** 3 saatlıq növbətçi yoxlama (temirci) — cədvəli yeni sessiyaya köçürüb köhnəni söndürmək;
  kəsilmə düzəlişini yoxlamaq; GDELT dolması; `news_shock_vol` / `geo_shock_vol` ilk nəticələri (t > 2 olsa,
  dalğalılıq bayrağı təklifi); `BLOKLAR.md`-ni hər işdən sonra yeniləmək.
- **Təqvim:** 29.11 hipotez agentinin ilk işi; 30.11 həftəlik hesabat; 2.12 qızıl proqnozu yoxlaması; 9.12 Fed.

## 7. Dəmir qaydalar (dəyişmir)
Dostun repo-su `dtxxkxxtq/pj-trade-gold` — yalnız oxu. Açar/parol çata yazılmır. Qiymət LLM-dən heç vaxt.
Qorunan fayllar (`deploy/protected.txt`) yalnız `Sahib-təsdiqi:` sətri ilə. Push yalnız testlər yaşıl olanda
(`set -o pipefail`). Commit-lərdə model adı yoxdur. IBJA yalnız rəsmi API; WGC/BlackRock avtomatik çəkilmir.
