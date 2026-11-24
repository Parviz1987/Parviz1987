# Sizin istəkləriniz, mənim anlayışım və qurduğum sistem

Tarix: 24 noyabr 2026 (New York). Bu sənəd sizin istəklərinizi, onları necə başa düşdüyümü və hər biri üçün nə
qurduğumu yan-yana göstərir. Harada fərqli başa düşmüşəmsə, onu da açıq yazmışam.

---

## 1. Ana hədəf

**Sizin istəyiniz:** qızıl, gümüş, platin və palladiumun qiymətinin qalxacağını və ya düşəcəyini **əvvəlcədən**
bilmək. Bu, həm qısa müddətə (dəqiqələr, saatlar), həm uzun müddətə (gün, həftə, ay) aiddir. Səbəbini də bilmək
lazımdır. Sonra da qazanc gətirən yerdə addım atmaq.

**Mənim anlayışım:** «Bilirik» demək üçün söz yox, **sübut** lazımdır. Sübut belədir:
- proqnoz «həmişə yuxarı» kimi sadə qaydadan yaxşı olmalıdır;
- bu, təsadüf olmamalıdır;
- alış-satış fərqindən (spred) sonra pul qazandırmalıdır.

Ticarət yalnız sübut olan yerdə və yalnız sizin qərarınızla olur.

**Qurduğum:**
- **Hakim.** Hər proqnozu vaxtı çatanda real qiymətlə yoxlayır. Təsadüfə qarşı sərt qayda qoyulub: çox üsul yoxlananda
  tələb də sərtləşir. Spred nəzərə alınır. Hər müddət üçün minimum proqnoz sayı var.
- **Kölgə ticarəti.** Hər proqnoz kağız üzərində real sövdələşmə kimi oynanır: stop, hədəf, spred, hamısı var. Nəticə
  «1000 $-lıq sövdələşmədə orta nə qazandırdı» kimi göstərilir.
- **Müddətlər:** 15 dəq, 30 dəq, 1 saat, 4 saat, 1 gün, 3 gün, 1 həftə, 10 gün, 1 ay.

**Harada görünür:** Nəticələr səhifəsi (`/results`), bölmə 2, 4, 5.

---

## 2. Yamaq yox, hər hissənin səbəbi olsun

**Sizin istəyiniz:** sistemdə lazımsız və yamaq hissə olmasın. Hər hissənin səbəbi, gözləntisi, ölçüsü və əvəzi olsun.

**Qurduğum:**
- Hər üsulun **pasportu** var: niyə buradadır, nə gözləyirik, işləməsə nə olacaq.
- Panelə Hakimin rəqəmləri ilə birlikdə çıxır.
- Səhv tapılanda səbəbi aid olduğu yerdə düzəldilir. Məsələn:
  - əlaqəli bazarların «gəlmir» görünməsinin səbəbi gecə saatlarında sakit bazar idi;
  - yeniləmənin geri qaytarılmasının səbəbi ağır hesablamanın əsas dövrü məşğul saxlaması idi.

---

## 3. Bütün məlumatlar gəlsin

**Sizin istəyiniz:** dollar, faizlər, neft, xəbərlər, ABŞ rəqəmləri və X-dəki çıxışlar sistemə avtomatik gəlsin.

**Qurduğum (gözlər):**

| Məlumat | Mənbə | Nə qədər tez |
|---|---|---|
| 4 metalın qiyməti | Capital.com axını | saniyə-saniyə |
| Dollar indeksi, EUR/USD, USD/JPY, neft (WTI, Brent), S&P 500, VIX, ABŞ 10 illik istiqraz | Capital.com axını | saniyə-saniyə |
| Real faiz, dollar, VIX, neft (rəsmi) | FRED | gündəlik |
| Fondların mövqeyi | CFTC COT | həftəlik |
| Xəbərlər | Google News, Fed, Benzinga | dəqiqələr |
| X (Twitter) | Kəşfiyyatçı (Grok) | 4 saatdan bir; həyəcanda dərhal |
| ABŞ rəqəmlərinin vaxtı və gözləntisi | Forex Factory | — |
| ABŞ rəqəmlərinin faktı | Rəqəm ovçusu: iki beyin vebdə ayrı-ayrı axtarır, eyni rəqəmi tapanda qəbul olunur | rəqəm çıxandan 2–20 dəq sonra |

**Açıq qeyd:** Capital-dan uzun tarixçə (səhifə-səhifə) hələ təsdiqlənməyib. Broker köhnə səhifəni verməyib. Səbəbi
növbəti yükləmədə qeyddə görünəcək, sonra düzəldəcəyəm.

---

## 4. Beyinlər həqiqətən proqnoz versin və yoxlansın

**Sizin istəyiniz:** süni intellektlər pul xərcləyir, amma nəticə vermir. Onlar konkret sual almalı, konkret cavab
verməli, cavab da yoxlanmalıdır.

**Mənim anlayışım:** Haqlı idiniz. Əvvəl beyinləri **mətn yazan izahçı** kimi qurmuşdum. Strateqə qiymətin son
hərəkəti verilmirdi, təlimatı isə ona proqnoz verməyi qadağan edirdi. Nəticədə Hakimdə Strateqin istiqaməti 0 idi.
Bu, mənim xətam idi.

**Qurduğum:**

| Beyin | Şirkət | İşi |
|---|---|---|
| Strateq | Claude | Hər saatda bir dəfə və hər həyəcanda: bütün faktlar → 1 saat, 4 saat, 1 gün üçün «yuxarı» ehtimalı və səbəbi |
| İkinci analitik | OpenAI | Eyni faktlarla, Strateqin cavabını görmədən öz ehtimalını verir |
| Oxuyucu | OpenAI | Hər başlığı qiymətləndirir: hansı metal, hansı istiqamət, nə qədər güclü (0–3) |
| Rəqəm ovçusu | OpenAI + Claude | ABŞ rəqəminin faktını vebdə tapır |
| Kəşfiyyatçı | Grok | X-də son xəbərləri axtarır |

- Hər fikir saxlanır və Hakim onu sonra real qiymətlə yoxlayır.
- **Beyinlərin öz hesabı:** həyəcandan sonra verilən fikirlər və saatlıq fikirlər ayrıca hesablanır.

**Açıq qeyd:** Beyni keçmiş üzərində yoxlamaq olmur, çünki o, keçmişin nəticəsini artıq bilir. Ona görə beyinlərin
hökmü üçün 2–4 həftə canlı nəticə lazımdır.

---

## 5. Sinir sistemi: hadisə olan kimi avtomatik reaksiya

**Sizin istəyiniz:** sistem saatı gözləməsin. Harasa müharibə başlayanda, X-də kimsə faiz barədə danışanda, ABŞ
rəqəmi çıxanda analitik dərhal işə düşsün, beyinləri çağırsın, məlumatı çəksin, proqnoz versin. Hamısı canlı orqanizm
kimi bir-birinə bağlı olsun.

**Qurduğum (sinirlər):** siqnal lenti. Bunlar həyəcan sayılır:
- güclü xəbər (güc 3: müharibə, Fed, sanksiya…);
- 15 dəqiqədə eyni istiqamətdə 2 və daha çox güclü xəbər;
- ABŞ rəqəminin faktı təsdiqləndi;
- metalda və ya əlaqəli bazarda qəfil sıçrayış (adi hərəkətdən 4 dəfə böyük).

**Həyəcan zənciri:**
1. Xəbərdirsə, Grok X-də dərhal axtarır.
2. Strateq və İkinci analitik «nə baş verdi» ilə birlikdə ehtimal yazır.
3. Hakim sonra yoxlayır.

Hər hadisə yalnız bir dəfə həyəcan yaradır. Xərc nəzarəti üçün həyəcan ən çox 15 dəqiqədə bir və gündə 12 dəfə ola
bilər. Beyinlərin öz dövrü var və heç nəyi gözləmir.

**Sübut:** 23 noyabr 20:07 NY-də qızıl +0,32 % sıçradı və Fed-dən xəbərlər gəldi. Sistem bunu özü tutdu, Grok
axtarış etdi, 20:12 NY-də Strateq fikrini yazdı.

---

## 6. Hakim analitikləri tərəzidə çəksin

**Sizin istəyiniz:** Hakim təkcə proqnozları yox, analitiklərin fikirlərini də yoxlasın. Kim düz deyib, kim səhv,
tərəzidə çəkib son nəticəni versin.

**Qurduğum:**
- **Tərəzi.** Hər analitik (hesab üsulu və ya beyin) Hakimin ölçdüyü nəticəyə görə çəki alır:
  - həddən nə qədər yaxşıdırsa, çəkisi o qədər ağırdır (ən çox 3);
  - həddən yaxşı deyilsə, çəkisi 0-dır.
- Tərəzi bütün fikirləri bu çəkilərlə birləşdirib son ehtimalı verir. Onun özü də yoxlanır.
- **Seçici konsensus** də qalır: müstəqil fikir ailələri razı olanda istiqamət verir.
- **Harada görünür:** Nəticələr → bölmə 5 «Analitiklər və tərəzi»: hər analitikin canlı və keçmiş nəticəsi və
  çəkisi.

---

## 7. Dostunuzun 31 agenti

**Sizin istəyiniz:** o agentlərə baxmaq, lazım olanı götürmək, lazım olmayanı demək.

**Mənim anlayışım:**
- Hamısını kopyalamaq şişkinlik yaradardı: yarısı mağaza işidir, çoxu bizdə artıq var.
- Onların heç birinin ölçülmüş dəqiqliyi yox idi.
- Ona görə ideyanı götürüb, bizim Hakimin yoxladığı üsul kimi yazdım.

**Qurduğum:**
- 3 yeni üsul:
  - **COT** — fondlar həddən çox alanda və ya satanda əks meyl;
  - **Mövsümilik** — hər ayın tarixi meyli; ən az 5 il lazımdır və onların 70 %-i eyni istiqamətdə olmalıdır;
  - **Zərgərlik təqvimi** — Divali və Çin Yeni ili öncəsi 21 gün.
- Qalanları üçün qərar cədvəli verdim: bizdə var / lazım deyil / sonraya.
- Dostunuzun reposunda heç nə dəyişməyib.

---

## 8. Agentləri canlı görmək

**Sizin istəyiniz:**
- ortada kürə;
- nömrəli tapşırıq düyünləri, vəziyyəti və rəngi ilə;
- W1…Wn mərhələləri;
- zaman xətti (x1 / x10 / x50);
- limit, son sinxron və saat;
- canlı yenilənmə; hər agent bir mərkəzə yazsın.

**Qurduğum:**
- `/agents` səhifəsi: fırlanan kürə, 12 düyün, asılılıq xətləri, mərhələlər, zaman xətti və təkrar.
- Hər agent vəziyyətini bir mərkəzə yazır, səhifə yalnız oradan oxuyur.
- Yenilənmə canlı WebSocket bağlantısı ilə gəlir. Səhifəni yalnız siz görürsünüz.
- Telefonda kartlar şaquli siyahı kimi düzülür.

---

## 9. Təhlükəsizlik və nəzarət

**Sizin istəyiniz:** açarlar, bot, haker — sistem qorunsun və mənə xəbər versin.

**Qurduğum:**
- Server divarı: yalnız sayt portları açıqdır, SSH bağlıdır.
- Giriş qoruması: 15 dəqiqədə 5 səhv cəhddən sonra ünvan 15 dəqiqəlik bloklanır.
- Təhlükəsizlik jurnalı və brauzer qoruma başlıqları.
- Açarlar yalnız serverdə saxlanır.
- **Növbətçi yoxlama hər 3 saatdan bir** bu söhbətdə işləyir: əvvəl təhlükəsizlik, sonra sağlamlıq, sonra təhlil.
  Sakit olsa da xəbər verir.

---

## 10. Asan baxış və New York saatı

**Sizin istəyiniz:** 15 dəqiqə, 30 dəqiqə, 1 saat və 1 gün üçün «nə dedik, nə oldu» asan görünsün. Bütün saatlar New
York vaxtı ilə olsun.

**Qurduğum:**
- Nəticələr səhifəsi, 5 bölmə:
  1. indi nə gözləyirik;
  2. 7 günün hesabı;
  3. nə dedik və nə oldu (qrafik);
  4. uğur xəritəsi;
  5. analitiklər və tərəzi.
- Hər yerdə saat New York vaxtı ilə göstərilir.

---

## 11. İş qaydası: bloklar, ardıcıllıq, təlimat

**Sizin istəyiniz:** işi böyük bloklara böl, biri bitmədən o birinə keçmə, qarışıqlıq olmasın. Unutmamaq üçün özün
üçün təlimat yarat.

**Qurduğum:**
- `docs/sinir-sistemi.md`: sistemin xəritəsi, bloklar, hər blokun «bitdi» meyarı və vəziyyəti, «Gözləmə siyahısı»
  (yeni istəklər sırası gələnə qədər oraya yazılır).
- **Həftəlik hesabat** hər bazar ertəsi 12:13 NY-də gəlir (ilki 30 noyabrda). Orada olacaq:
  - harada işləyir;
  - ən yaxın gələn analitiklər;
  - beyinlərin hesabı;
  - həyəcanlar;
  - növbəti addım təklifi.

---

## 12. Açarlar və sizin işləriniz

**Sizin istəyiniz:** hansı açarı almaq, haraya qoymaq lazımdırsa, hazırla.

**Qurduğum:** `docs/acarlar.md`.
- 9 açarın hamısı serverdə yoxlanıb və işləyir. **Məcburi alış yoxdur.**
- **İstəyə görə FMP Starter (~29 $/ay):** yalnız keçmiş ABŞ rəqəmləri üçündür. Alsanız: Admin → FMP → «Yoxla».

---

## Dəyişməz qaydalar (sizinlə razılaşdırılıb)

- Qiyməti yalnız bazar verir, beyin heç vaxt qiymət uydurmur.
- Ticarət və ödəniş yalnız sizin qərarınızla olur.
- Dostunuzun reposuna (dtxxkxxtq/pj-trade-gold) toxunulmur.
- Açar və parol söhbətə yazılmır.
- Hər dəyişiklikdən əvvəl ehtiyat nüsxə saxlanır, sonra test və serverdə yoxlama aparılır.

## Açıq həqiqət

Sistem indi sizin təsvir etdiyiniz kimi bir-birinə bağlı işləyir: gözlər, sinirlər, beyin, Hakim, tərəzi.

Amma **hər dəqiqəni əvvəlcədən bilmək heç bir sistemə mümkün deyil**. Real hədəf belədir: Hakim harada (hansı metal,
müddət, şərait və analitik) sübut versə, yalnız orada addım atmaq.

Bu günə qədər heç bir analitik sübut almayıb. İlk ciddi canlı hökm 2–4 həftəyə gələcək, mən də hər həftə rəqəmlə
yazacağam.
