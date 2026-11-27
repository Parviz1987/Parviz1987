# TST Trade — Ümumi iş planı və icra təlimatı

**Tarix:** 2026-11-26 (New York)
**Kim üçün:** sahib. Mən (Claude) bu planla işləyirəm.
**Qayda:** bu plan sahibin bir əmri ilə icra olunur. Bu fayl yazılana qədər heç bir işə başlanmayıb.

---

## 0. Ana hədəf və onun ölçüsü
**Hədəf:** qızıl, gümüş, platin və palladiumun qalxıb-düşəcəyini və aralığını əvvəlcədən demək. Bunun düz olduğunu Hakim real qiymətlə, bütün xərclər çıxılandan sonra sübut etməlidir.

**İndiki vəziyyət:**
- Heç bir istiqamət proqnozu sübut olunmayıb.
- Yeganə sübut olunmuş bacarıq 80 %-lik qiymət aralığıdır: proqnoz aralığı real qiyməti təxminən 80 % halda tutur.

**Bütün işlər bir sualla ölçülür:** bu iş Hakimin sübutuna yaxınlaşdırırmı, yoxsa sistemi daha etibarlı edirmi? Heç birini etmirsə, iş görülmür.

---

## 1. «Dərinləşdirmə» təlimatı (əvvəlki əmr) — təfsilatı

**Sahibin istəyi:** araşdırma hesabatı səthi idi. Dərin olsun və bizim sistemə uyğun, gözəl formada təqdim olunsun.

| Addım | Nə | Vəziyyət |
|---|---|---|
| 1.1 | **Əsas mənbələri tam oxumaq.** Mühitə 6 sayt əlavə olundu: Google SRE, LiteLLM, OpenRouter, arXiv, Healthchecks.io, FreqAI. 3 yoxlama aparıldı. | ✅ Bitdi |
| 1.2 | **12 addımın hər biri üçün bizim sistemə uyğun ətraflı layihə.** Hər addımda: nə edir (nümunə ssenari ilə), bizim sistemdə harada dayanır, necə işləyir, sərhədləri, necə yoxlanır, sizdən nə lazımdır, xərc, vaxt, mənbə. | ⏳ Hazırlanır |
| 1.3 | **İnteraktiv səhifə.** Blok xəritəsi, hər addımın kartı və «Təsdiqlə / Sonra / Lazım deyil» düymələri. Seçimlər səhifənin öz bazasında saxlanır, mən onları oxuyub icraya götürürəm. | ⏳ Hazırlanır |

**1.1 yoxlamasının əsas nəticələri (orijinal sənədlərdən):**
- **Beyin keçidi (LiteLLM, OpenRouter):**
  - Hər xəta növünün öz cavabı olmalıdır:
    - 429 (limit) → gözlə;
    - 401/402 (açar və ya ödəniş) → sahib düzəldənə qədər söndür;
    - 404 (model bağlanıb) → yeni model yalnız sahibin təsdiqi ilə.
  - Təkrar cəhd yalnız bir qatda olmalıdır.
  - Gizli keyfiyyət düşməsi: neçə dəfə ehtiyat beyinə keçildiyi sayılmalıdır.
- **Server nəzarəti (Google SRE, Healthchecks.io):**
  - Kənar nəzarətçi mütləqdir.
  - Səbəbə yox, əlamətə görə xəbərdarlıq verilməlidir.
  - Avtomatik təmir limitli və asan dayandırıla bilən olmalıdır.
  - Eyni xəta 7 gündə iki dəfə təkrarlansa → səbəbin yoxlanması.
  - Qışda bazar saatları bazar 23:00 – cümə 22:00 UTC-dir. Saatlar kodda sabit yazılmamalıdır.
- **Səhvdən öyrənmə (arXiv):**
  - AI ticarət agentlərinin üstünlüyü xərclərdən sonra və uzun müddətdə adətən yox olur.
  - Qızıl üzrə əvvəlcədən sabitlənmiş qayda sistemi zərər verib (Sharpe −0,12), sadə «al və saxla» isə Sharpe 1,04 göstərib.
  - Aralıq üçün adaptiv düzəliş düsturu təsdiqləndi.
  - Hakim üçün yeni risk: oxşar sınaqlar sel kimi artanda sübut həddi zəifləyir.

---

## 2. Ümumi iş siyahısı

Hər işin yanında beş şey yazılıb: **Nə**, **Niyə**, **Necə**, **Nəyə əsaslanır**, **Dərinlik**. **Sahibdən** sətri sizin edəcəyiniz işi göstərir.

### Faza A — Təhlükəsizlik və «gözlər» (ən birinci)

**A1. Kənar nəzarətçi (heartbeat) — sahibin sualı ilə əlavə olunub**
- **Nə:**
  - Server hər 5 dəqiqədən bir Healthchecks.io-ya «sağam» siqnalı göndərir.
  - Ayrıca siqnallar təxminən 13 əsas iş üçündür: tətbiq, qiymət axını, qaydalar, proqnozun verilməsi, Hakimin hesablaması, 3 məlumat qrupu, ehtiyat nüsxə, yeniləmə, növbətçi yoxlama, aylıq bərpa sınağı.
  - Siqnal gecikərsə, Telegram-a mesaj gəlir.
- **Niyə:** server tam dayansa, bunu indi heç kim dərhal bilmir. Mənim yoxlamam 3 saatda bir dəfədir.
- **Necə:**
  - Siqnallar bazar saatlarına görə qurulur, bazar bağlı olanda da «atlandı» siqnalı göndərilir.
  - Qiymət «təzəlik» həddi:
    - 15 dəqiqə dəyişməyən qiymət köhnə sayılır;
    - gündəlik fasilədən sonra 5 dəqiqə istiləşmə vaxtı verilir.
  - Pulsuz plan 20 nəzarətə qədərdir, bizə təxminən 13-ü lazımdır.
  - İkinci, ehtiyat kənar yoxlayıcı GitHub Actions ilə qurulur, çünki Healthchecks.io-nu bir nəfər idarə edir.
- **Nəyə əsaslanır:** Healthchecks.io sənədləri, Google SRE «Monitoring» fəsli.
- **Dərinlik:** tam. Testlər yazılır, serverdə saxta bir dayanma yaradılıb mesajın gəldiyi yoxlanır.
- **Sahibdən:** healthchecks.io hesabı, @HealthchecksBot Telegram botu, ping linkini Admin-ə yazmaq (söhbətə yox).

**A2. 2FA-nı açmaq**
- **Nə / Niyə:** 3 səhv giriş cəhdi Çindən gəlib. 2FA hazırdır, amma açılmayıb.
- **Sahibdən:** Admin → «2FA qur» (addımlar əvvəlki mesajdadır).
- **Mən:** açıldığını diaqnostikada yoxlayıram.

**A3. Düzəlişlər serverə yalnız sahibin təsdiqi ilə**
- **Nə:**
  - Mən düzəlişi ayrıca budağa yazıram.
  - Sizə «nə dəyişdi, niyə, testlər keçdimi» qısa xülasəsi gəlir.
  - Siz təsdiqləyəndən sonra server yenilənir.
- **Niyə:** indi mənim düzəlişlərim baxılmadan serverə düşür. Dünya təcrübəsi (Sentry, GitHub, Replit hadisəsi) bunu riskli sayır.
- **Necə:** server təsdiqlənmiş budağı izləyir, mən layihə budağına yazıram. Təsdiq Admin səhifəsində bir düymə ilə olur.
- **Diqqət:**
  - Bu iş qurulandan sonra siyahının qalanı daha yavaş gedəcək, çünki hər yeniləmə sizin düymənizi gözləyəcək.
  - **Təklifim:** A3-ü siyahının sonunda quraq.
- **Sahibdən:** qərar. A3 əvvəldə olsun, yoxsa sonda?

**A4. Təcili dayandırma düyməsi**
- **Nə:** Admin-də bir düymə bütün avtomatik təmiri dayandırır.
- **Niyə:** AWS-in 2025-ci il hadisəsində avtomatika problemi böyütdü və onu dayandırmaq lazım oldu.

### Faza B — «Nəzarətçi» qat (server özü, avtomatik)

**B1. Ağıllı beyin keçidi (bütün beyinlər üçün)**
- **Nə:** hər xəta növünə uyğun hərəkət.

  | Xəta | Hərəkət |
  |---|---|
  | 429 (limit) | gözləmə |
  | 401/402 (açar və ya ödəniş) | söndür və sizə xəbər ver |
  | 404 (model bağlanıb) | yeni modeli **siz** təsdiqləyirsiniz |
  | Uzun cavabsızlıq | təkrar sorğu göndərilmir |

  Bundan əlavə:
  - təkrar cəhd yalnız bir qatda olur, aralarında təsadüfi fasilə ilə;
  - «yarımaçıq» sınaq: dayanmış beyin bir sorğu ilə yoxlanır;
  - hər beyin üçün aylıq büdcədən əvvəlcədən ehtiyat ayrılır;
  - ehtiyat beyinə keçidlərin sayı gündəlik ölçülür.
- **Niyə:**
  - Gemini-nin kvota xətası göstərdi ki, indiki keçid xətaları ayırd etmir.
  - Bu gün qurduğum avtomatik model dəyişməsi sizin «modeli mən təsdiqləyirəm» qaydanıza ziddir. Bu, düzəldilir.
- **Nəyə əsaslanır:** LiteLLM və OpenRouter sənədləri.
- **Dərinlik:** təxminən 150 sətirlik öz yönləndiricimiz və 15 xəta növünün cədvəli. Ayrıca LiteLLM proqramı yüklənmir, çünki sistemi sadə saxlamaq qaydamızdır.

**B2. Məlumatın təzəliyi**
- **Nə:**
  - Hər məlumat növü üçün öz təzəlik həddi var, yalnız bazar açıq olanda yoxlanır.
  - «Donmuş qiymət» ayrıca tutulur.
  - Köhnə məlumat proqnoza «köhnədir» nişanı ilə düşür, ya da üsul susur.
- **Niyə:** başqa sistemlərdə «bağlıdır» yazılıb qiymət günlərlə 0 qalıb.

**B3. İcazəli avtomatik hərəkətlər siyahısı**
- **Nə:**

  | Hərəkət | Limit |
  |---|---|
  | İşi yenidən başlatmaq | saatda ən çox 3 dəfə |
  | Ehtiyat mənbəyə keçmək | 30 dəqiqədə 1 dəfə |
  | Xarab mənbəni dayandırmaq | sonuncu mənbə heç vaxt dayandırılmır |
  | Köhnə versiyaya qayıtmaq | hər yeniləmədə 1 dəfə |

  - Hər hərəkət jurnala yazılır.
  - Eyni xəta 7 gündə 2 dəfə → səbəbin yoxlanması.
  - 3-cü dəfə → həmin hərəkət dayanır, sizə xəbər gedir.
- **Niyə:** təmir səbəbi gizlətməməlidir (Google SRE).

**B4. Blok əlaqələrinin xəritəsi**
- **Nə:** «hansı blok nədən məlumat alır, nəyə verir» xəritəsi. Hər əlaqənin vəziyyəti Sistem səhifəsində şəkil kimi görünür.

### Faza C — «Təmirçi» (mən, cədvəllə)

**C1. Təmirçi təlimatı (skill)**
- **Nə:** növbətçi yoxlamanın yazılı qaydası:
  1. xəritəyə bax;
  2. sübut topla;
  3. səbəbi tap;
  4. testlə düzəlt;
  5. serverdə yoxla;
  6. jurnala yaz;
  7. sizə xülasə ver.
- **Niyə:** hər yoxlama eyni dərinlikdə olsun.

**C2. Test qoruyucusu**
- **Nə:**
  - Test silinsə və ya zəiflədilsə xəbərdarlıq.
  - Hakimin hədləri dəyişsə xəbərdarlıq.
  - Qaydalar faylı dəyişsə xəbərdarlıq.
- **Niyə:** AI agentləri bəzən «keçsin» deyə testi dəyişir (ImpossibleBench).

### Faza D — «Analitik» (səhvdən öyrənmə; ən dərin hissə)

**D1. Aralığın adaptiv düzəlişi**
- **Nə:**
  - 80 % aralıq real tutma nisbətinə görə özünü düzəldir. Düstur: α yeni = α + γ·(α − xəta), γ ≈ 0,01–0,02.
  - Tutma 80 %-dən uzaqlaşanda bu, «bazar rejimi dəyişdi» siqnalıdır.
- **Niyə:** bizim yeganə sübutlu bacarığımızı daha da gücləndirir.

**D2. Çəkilərin yenilənməsi**
- **Nə:**
  - Hedge + Fixed Share üsulu ilə hər üsula minimum çəki saxlanır, heç bir üsul tam silinmir.
  - Bu çəkilər bərabər çəkilərdən yaxşı nəticə verəndə istifadə olunur, verməyəndə yox.
- **Niyə:** araşdırmalara görə sadə ortalama çox vaxt «ağıllı» çəkilərdən yaxşıdır.

**D3. Səhvin yarılması**
- **Nə:**
  - Hər proqnozun anında bütün blokların göstəriciləri saxlanır.
  - Səhvlər 8 sabit səbəb növünə ayrılır: trend dönüşü, xəbər şoku, ABŞ rəqəmi, likvidlik, rejim dəyişməsi və s.
  - Həftəlik toplanır. Yalnız davamlı qanunauyğunluq fərziyyə agentinə ötürülür.
- **Niyə:** sizin istədiyiniz «keçmişə baxıb əlaqə tapmaq» budur. Amma tək bir səhvə görə proqnoz dəyişmir.

**D4. Hakimin gücləndirilməsi**
- **Nə:**
  - Sübut həddinin aşağı sərhədi olur və hədd heç vaxt enmir.
  - Hədd həmişə xam sınaq sayı ilə hesablanır.
  - Yeni qayda üçün DSR/PBO yoxlaması aparılır, proqnoz müddəti qədər «karantin» ilə.
- **Niyə:** arXiv 2611.14539 məqaləsi sınaq seli ilə bu həddin aldadıla biləcəyini göstərir.

### Faza E — Blokların dərinləşdirilməsi (azdır, çoxalmalıdır)
Təmiz yenidən hesablama bitəndən sonra hər blok üçün **Hakimin təmiz rəqəmləri** ilə audit aparılır:

| Blok | Nə azdır / nə edilməlidir |
|---|---|
| Texniki analiz | Zərərli qaydaları ayır (səsi onsuz da 0-a düşür). Rejimlərə (ADX) görə harada işlədiyini göstər. |
| Fundamental | Yeni agent rəqəmlərini qaydaya çevir: IBJA, RBI, PBoC, WGC, COMEX. Hindistan və Çin tələbi qaydaları gücləndirilsin. |
| Xəbər | Son gündə heç bir qayda işə düşməyib. Səbəbini yoxla: həddlər çox sərtdir, yoxsa giriş zəifdir? |
| Bazarlar arası | Brokerin yuan və mis bazarlarını verib-vermədiyini yoxla, verirsə qoş. |
| Vaxt | Fed iclas tarixlərini agentdən al və «Fed günü» qaydası qur. |
| AI beyinlər | 30 noyabrda xərc və fayda müqayisəsi. Zərərli olan beyini dayandırmaq təklifi (sizin qərarınızla). |

### Faza F — Məlumat boşluqları
- **F1. Gemini:** sizin qərarınız lazımdır: ödəniş qurulsunmu? Qurulmasa, agentlər OpenAI + Anthropic ilə işləyir.
- **F2. FMP planı:** planda başqa faydalı məlumat varmı, yoxlanılsın.
- **F3. Agentlərin ilk nəticələri:** hansı agent rəqəm tapır, hansı tapmır. Tapmayanların sualı yaxşılaşdırılsın.

### Faza G — Gözləyən yoxlamalar (təqvim)
| Tarix | İş |
|---|---|
| 27 noyabr | VACUUM nəticəsi (baza faylının kiçilməsi) |
| 27 noyabr | «Bazarlar» və «vaxt» keçmiş hesablarının bitməsi |
| 29 noyabr | Fərziyyə agentinin ilk işi |
| 30 noyabr | Həftəlik hesabat və AI beyinlərinin xərc qərarı |
| 2 dekabr | Qızıl üzrə həftəlik proqnozumun yoxlanması (3 480 $) |
| 9 dekabr | Fed iclası. Proqnozların necə davrandığına baxış |

### Faza H — Sonra (indi yox)
- Kağız ticarət → demo broker (sizin demo açarınız lazımdır).
- Kompüterinizdəki sessiya üçün təhvil faylı. Siz «indi lazım deyil» dediniz.

---

## 3. İcra qaydası (sizin bir əmrinizdən sonra)
1. **Sıra:** A1 → A4 → B1 → B2 → B3 → B4 → C1 → C2 → D1 → D2 → D3 → D4 → E → F → (A3 sizin qərarınıza görə). G öz tarixlərində edilir.
2. **Hər iş üçün:**
   1. kod;
   2. testlər (hamısı keçməlidir);
   3. GitHub;
   4. serverdə yoxlama;
   5. jurnal;
   6. sizə 2–3 sətirlik xəbər.
3. **Dayanma nöqtələri** (sizsiz keçilmir): açar, ödəniş, model seçimi, Hakim qaydaları, ticarət, məlumat silmə. Belə yerə çatanda dayanıb sizdən soruşuram, qalan işlərə davam edirəm.
4. **Növbətçi yoxlama** hər 3 saatda davam edir.
5. **Dürüstlük:** yoxlanmayan şeyi «işləyir» kimi demirəm, ehtimalı fakt kimi təqdim etmirəm.

## 4. Sizin qərarlarınız (əmrdən əvvəl və ya əmrlə birlikdə)
1. A3 (düzəlişlər sizin təsdiqinizlə): əvvəldə, yoxsa sonda?
2. Gemini-yə ödəniş qurulsunmu?
3. A1 üçün healthchecks.io hesabını nə vaxt açacaqsınız? Mən kodu hazırlayıram, hesab açılana qədər siqnallar sadəcə göndərilmir.

## 5. Razılaşdırılmış qərarlar (çatda, 26.11.2026) — icra bunlara əsaslanır

Sahib 12 addımı bir-bir müzakirə edib təsdiqlədi («12 keç»). Plan səhifəsində də qeyd olunub.

- **İş bölgüsü (s2, sahibin öz variantı):** Merge düyməsi yoxdur. Texniki işi Claude özü edir, 8 qoruyucu qatla:
  əvvəl xətanı göstərən test, kiçik addım, ikinci göz (ayrı yoxlayıcı), bütün testlər, brauzer «dünən/bu gün», **nəticə izi**
  (dəyişiklikdən əvvəl/sonra eyni məlumatla proqnoz — rəqəm dəyişirsə dayan, sahibə izahla yaz), serverdə hazırlıq
  yoxlaması + bir dəfə geri qayıtma, «səhvlərim siyahısı». Sahibdən soruşulur: pul, nəticə izini dəyişən hər şey,
  ticarət, açar və model, məlumat silmək, blok/səhifə/düymə çıxarmaq. Qorunan fayllara toxunan commit «Sahib-təsdiqi:»
  qeydi olmadan serverə düşmür.
- **s1:** 13 siqnal; Telegram-a dərhal yalnız 4 təcili hal (server, qiymət, backup, deploy geri qaytarıldı), qalanı gündəlik
  icmal; gecə mesajı səsli; saatda bir GitHub Actions-dan ehtiyat yoxlama. Bazar saatı New York vaxtı ilə (qış/yay, fasilə).
- **s3:** qorunan siyahını Claude müəyyən etdi (Hakim hədləri, sınaq qaydaları, xərc hesabı, öyrənmə sabitləri, ticarət qatı,
  açar/limit/model, LIVE/DELAYED/OFFLINE məntiqi, CLAUDE.md, spesifikasiya).
- **s4, s5, s8:** texniki — Claude özü (kataloq + limitlər + «Dayandır»; canlı/hazır yoxlaması; növbətçi təlimatı).
- **s6:** Gemini qalır (Google axtarışı). Sahib ödənişli layihədən açarı sonda Admin-ə qoyacaq. Limitlər indiki kimi.
- **s7:** qabaqcadan icazə: eyni şirkət + sınaqda keyfiyyət aşağı deyil + xərc ≤ +20% → avtomatik keçid və xəbər; qalanı
  müqayisə kartı ilə sahibə. Sınaq sürüşü (20–30 sual), 1 həftə kölgə (10%), işə uyğun beyin, aylıq beyin hesabatı.
- **s9:** aralığın avtomatik tənzimlənməsi (ACI) — əvvəl keçmişdə sınaq, sonra canlı.
- **s10:** dirijor kimi dərinləşdirildi və kölgədə quruldu (`app/conductor.py`). İlk nəticə: sadə ortanı keçmədi; canlıya
  qoşma qərarı sahibdə.
- **s11:** gücləndirilmiş səhv yarılması: 8 səbəb + 6 qat (Murphy bölgüsü, dilimlər, «kim yanlış apardı», qərar/nəticə
  4 qutu, ayın 5 ən böyük səhvi kartı, aralıq sürüşməsi). Canlıya toxunmur.
- **s12:** Hakim: real sınaq sayı, enməyən hədd, DSR ≥ 0,95, PBO ≤ 0,10 (purge/embargo), gələcəyə baxma qadağası.

İcra sırası dəyişmir: A → B → C → D → E → F. Sahibdən gözlənən: Gemini açarı (ödənişli), healthchecks.io hesabı, 2FA-nı açmaq.

### 5.2 Keçmiş məlumat (sahib, 27.11.2026: «Kitabxananı qur, ara yolu da et»)
- Hadisələr kitabxanası qurulur (keçmiş ABŞ rəqəmləri və Fed qərarları, o an bilinənlə; beyinlərə yalnız kölgə
  sınağından keçən hissə).
- Ara yol: keçmişdə güclü (bal ≥ 70) üsul canlıda tez kölgəyə keçir; kağız ticarət üçün canlı sübut şərt qalır.

### 5.1 Blok qərarları (sahib, 26.11.2026: «3 qərarı sənin təkliflərinlə razıyam»)
1. **Mövsüm və zərgərlik tələbi** (`season`, `jewel`): istiqamət səsi yox, dalğalılıq işarəsi kimi — əvvəl kölgədə, Hakimin
   nəticəsi ilə qərar.
2. **Gecə dərsləri dayandırılır** (526 halda fayda yoxdur: 44,5 % və 44,9 %): beyin pulu xərclənmir; yerinə addım 11-in
   beyinsiz səhv yarılması.
3. **Fundamental çəkilər** son 2–3 ilin hərəkət edən pəncərəsi ilə yenidən hesablanır (2022 qırılması) — əvvəl kölgədə.

### 5.3 İş planı 27.11 (sahib, 27.11.2026: «Bəli, bunları eləyə bilərsən» + 10:20 NY «BAŞLA, HAMISINI DAYANMADAN BİTİR»)
Tam yoxlama siyahısı və jurnal: `docs/PLAN-27.11.md`. Qərarlar:
1. **Artıqları çıxarmaq** — «çıxarmaq» = ekrandan və birləşmədən çıxır; kod və məlumat silinmir (sahib: «silmək lazım
   deyil, arxada işləsin»). İcra: `season`, `jewel` pensiyaya; konsensus/tərəzi arxada, önə vahid proqnoz.
2. **Sınaqları daraltmaq** — Q ailəsi (qızıl, 1 saat: qaydalar, vahid, qrafik analitiki), qeyd 27.11 13:00 NY, hədd 0,05/3.
3. **İkinci analitik və müzakirə seyrək** — 4 saatda bir (pula qənaət).
4. **Hakimin 30 % yoxlaması** — nəticə həddi dəyişmədi (siyasət); əlavə qoruyucu: yazılma vaxtı hədəfdən sonra olan
   proqnoz son sınaqda sayılmır.
5. **Sahibsiz işləmək** — R2, Healthchecks, 2FA, Gemini onsuz da sistem işləyir; hər yerdə «sizin addımınızı gözləyir»
   kimi göstərilir. Növbətçi yoxlama hər dəfə təzə sessiyada; iş planı ilişsə (jurnal 6 saatdan köhnə), növbətçi davam etdirir.

### 5.4 Məlumat yolu və sayt (sahib, 27.11 axşam: «hansı yol hansıdırsa onu seçək … başla, ardıcıl, yarımçıq buraxma»)
1. **Qarışıq yol:** vaxtı məlum rəsmi mənbələr (BLS, Fed) — pulsuz «snayper»; qəfil xəbər — **FinancialJuice** (~$99/ay);
   böyük oyunçular, həqiqi həcm, 15 il tarixçə — **Databento Standard** (~$199/ay). Sahib ikisini də almağa qərar verdi;
   1 aylıq sınaq qabaqcadan qeyd olunacaq, fayda yoxdursa dayandırılır.
2. **Saytdan həqiqətən çıxarmaq** (kod/məlumat silinmir): Panel — etibar zolağı, 24 xanalı «GÖZLƏ», «Sabah üçün»,
   strateqin izahı (→ Analitiklər), «Sadə rejim»; Nəticələr — H1–H8, H9–H13, analitiklər/tərəzi, süzgəc, 2 illik fyuçers.
3. **Server** 1 GB → 2 GB (ayda $12), şənbə 28.11, bazar bağlı.
