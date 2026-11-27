# İş planı 27.11 — qırıq əlaqələr, artıqlar, saytın önü (sahib: «BAŞLA, HAMISINI DAYANMADAN BİTİR», 27.11 10:20 NY)

> **Kim üçün:** sahib və hər Claude sessiyası. Bu fayl planın **tək mənbəyidir**: hər addımdan sonra işarə və
> jurnal sətri yazılır. Sessiya ilişsə, yeni sessiya buradan davam edir (əvvəl `SOHBET-TARIXCESI.md` bölmə 5a).
> Sahibin təsdiqləri (27.11 çatda «Bəli, bunları eləyə bilərsən» + «Başla»): sınaqları 3–5 namizədə daraltmaq;
> İkinci analitiki və müzakirəni seyrəltmək; Hakimin «30 % gələcəyə baxan» yoxlamasını düzəltmək (qorunan fayl);
> artıqları çıxarmaq. **«Çıxarmaq» = ekrandan və birləşmədən çıxır; kod və məlumat silinmir, geri qaytarmaq olar.**

## Qaydalar (köhnə səhvlərə qayıtmamaq üçün — `monitor/sehvlerim.md`)
1. Hər addım: xətanı göstərən test → düzəliş → bütün testlər (`set -o pipefail`) → commit + push (əvvəl öz budaq,
   sonra `claude/amazing-keller-c4hwfl`) → serverdə yoxla (`/api/diag`, `curl -I`) → bu faylda işarə.
2. Sadə olmayan dəyişiklik — ayrıca yoxlayıcı agent («ikinci göz»). Proqnoz rəqəmi gözlənilmədən dəyişsə — dayan, yaz.
3. Üç söz: **işləyir** (serverin öz məlumatında görünür) · **kod hazırdır, sahibi gözləyir** · **işləmir**.
4. Sahibsiz edilmir: real pul / ticarət, yeni pullu xidmət və ya açar, məlumat silmək, Avtomatik Hakim siyasəti.
   Belə ehtiyac çıxsa — bura yazılır, həmin addım dayanır, qalanı davam edir.

## Mərhələ 0 — təhlükəsizlik toru
- [x] 0.1 Bu plan faylı.
- [x] 0.2 Növbətçi yoxlama və həftəlik hesabat hər dəfə **təzə sessiyada** başlayır (ilişmiş sessiyadan asılı deyil),
      vacib xəbər telefona. `trig_01VQ4otCpmwHSbgWngdMWzpY` (3 saat), `trig_01ATe3NLPyGeK2h81xVAUUSn`
      (bazar ertəsi 12:13); köhnələr söndürülüb (silinməyib). Təzə sessiya jurnal 6 saatdan köhnədirsə planı davam etdirir.

## Mərhələ 1 — hər əlaqənin xəritəsi
- [x] 1.1 Diaqnostikada əlaqə xəritəsi: mənbə → blok → analitik → birləşdirici → Hakim → səhifə; hər halqada son
      məlumatın yaşı, sətir sayı, növbəti halqa istifadə edirmi; «yalançı OK» (0 sətir, amma «ok») ayrıca.
- [x] 1.2 GitHub-dakı saatlıq kənar yoxlama həqiqətən işləyirmi. **Yox:** saatlıq yazılıb, amma GitHub onu 22 saatda 2 dəfə
      işə salıb (26.11 22:39, 27.11 08:53 NY). Əsas kənar göz — 3 saatlıq növbətçi yoxlama (təzə sessiya, telefona xəbər).

## Mərhələ 2 — qırıqlar və yalançı «işləyir»lər (27.11 səhər tapılanlar + 1.1-in tapdıqları)
- [x] 2.1 Hakimin öz yoxlaması: 30 % gələcəyə baxan saxta qayda (64 % düz) tutulmadı. Nəticə həddi (10–15 bənd, sahibin
      siyasəti) onu prinsipcə tuta bilmir. «Boz zona + gecikmə testi» sınandı, ikinci göz göstərdi ki, qısa üfüqlərdə həqiqi
      tez sönən üstünlüyü həmişəlik rədd edər — atıldı. Yerinə: hər proqnozun **yazılma vaxtı** qeyd olunur, son sınaq yalnız
      hədəf vaxtından əvvəl yazılanları sayır (nəticədən asılı olmayan qoruyucu). Öz yoxlaması dürüst «diqqət» göstərir.
- [x] 2.2 Blokların gündəlik yoxlaması köhnə şəkil göstərir (Xəbəri «qırıq»); tez-tez + yaşı görünsün.
- [x] 2.3 Alpaca (Benzinga) 48 saatda 0 başlıq, amma «ok». Yalnız ETF tikerləri soruşulurdu; indi ümumi axından da (yalnız
      metal adı keçənlər). Xəritə 0 gətirəni «heç nə gətirmir» göstərir.
- [x] 2.4 ~~Seçici konsensus heç vaxt ölçülə bilmir~~ — **səhər dediyim səhv idi:** sübutlu üsullardan asılı deyil; ən azı iki
      ailə razı və heç biri əks olanda danışır, ailələr çox vaxt razılaşmır. Birləşdirici kimi arxa plana (3.1).
- [x] 2.5 Qrafik analitikinin ehtiyat modeli 39 çağırışdan 2-də cavab verib — bu, cavabların kəsilməsi səhvi idi (26.11 21:22
      NY düzəldilib); o vaxtdan heç bir səhv cavab yoxdur. Düzəltməyə ehtiyac yoxdur; xəritə 24 saatlıq payı göstərir.
- [x] 2.6 Gemini: köhnə model bağlanıb, yeni modelin sınağı Google 503 ilə alınmayıb — sınaq təkrarı, sahibin
      qabaqcadan qaydası (eyni şirkət + sınaq pis deyil + qiymət ≤ +20 %). Müvəqqəti xətada sınaq 6 saatdan bir təkrar
      (3 dəfə). Yeni modelin qiyməti sistemdə məlum deyil → qayda avtomatik keçə bilmir, **qərar sahibindədir**; məlumat
      agentləri ehtiyat beyinlə işləyir.
- [x] 2.7 Google News gümüş/platin 429 — 429 deyən axın 15→30→60 dəq dincəlir (hər 2 dəqiqə soruşmaq onu daha da kəsirdi).
- [x] 2.8 R2, Healthchecks, 2FA hər yerdə «kod hazırdır, sahibin açarını gözləyir».
- [x] 2.9 `feed geo failed` xətası — 26.11 yeniləmə anında bir dəfə (fayllar dəyişərkən idxal), təkrarlanmayıb.

## Mərhələ 3 — artıqları çıxarmaq, sınaqları daraltmaq
- [x] 3.1 Birləşdiricilər: önə yalnız vahid proqnoz (+ müqayisə üçün sadə orta); konsensus, tərəzi, dirijor arxada.
      Panelin yeni bölməsində konsensus/tərəzi göstərilmir; «Nəticələr»in 7 günlük hesabı konsensus yox, vahid proqnozla.
- [x] 3.2 Mövsüm və zərgərlik səsləri pensiyaya (7 gündə 0 fikir; dalğalılıq sınağı sübut vermədi).
- [x] 3.3 İkinci analitik və müzakirə seyrək (pula qənaət) — 4 saatda bir (əvvəl hər saat).
- [x] 3.4 Yeni kiçik sınaq ailəsi (3–5 namizəd), qeyd vaxtı ilə, yalnız yeni canlı məlumatla. **Q1–Q3** (qızıl, 1 saat:
      qaydalar, vahid proqnoz, qrafik analitiki), qeyd 27.11 13:00 NY, hədd 0,05/3, pulla (tam xərcdən sonra), V ailəsi ilə
      eyni üsul. Niyə: V əsasən uzun üfüqlərdir (həftədə/ayda bir hal — illər); 1 saatda hər saat bir hal.
- [x] 3.5 Qeydə alınmış əsas sınaqların (V1–V5) istifadə etdiyi üsullara toxunulmur — yoxlandı (vahid,
      trendmix, tsmom, up, ABŞ rəqəmi impulsu — heç biri pensiyaya getmədi).

## Mərhələ 4 — saytın önü (sahibin 27.11 04:57 tapşırığı, `SOHBET-TARIXCESI.md` 5a)
- [x] 4.1 Panel: hər metal üçün analitiklərin indiki fikri (▲/▼, aralıq) + həmin metaldakı düz/səhv qeydi.
- [x] 4.2 Texniki şeylər «Ətraflı»ya; təkrarlar bir yerə; «Nəticələr»də bir sınaq siyahısı. «Nəticələr»: önə əsas sınaqlar
      (V+Q), 7 günlük hesab, «nə dedik»; qalan 8 cədvəl bir «Ətraflı (texniki)» düyməsində (masaüstü 2426→1342 px). «Bloklar»:
      hər blokun təfərrüatı «Ətraflı»da (2009→1157 px). Blok səhifələrində 2 illik qrafiklər və qayda cədvəlləri yığılır.
      Yığma mexanizmi bir fayl (`static/fold.js`), açılanda qrafiklər düzgün ölçüdə çəkilir.
- [x] 4.3 Hər səhifə 1366 və 390 ölçüdə şəkil, brauzer xətası yox, hər düymə basılıb.

## Mərhələ 5 — sənədlər və hesabat
- [x] 5.1 `BLOKLAR.md`, `SOHBET-TARIXCESI.md`, `IS-PLANI.md` (5.3), `monitor/sehvlerim.md` yeniləndi.
- [x] 5.2 Sahibə yekun: nə edildi, necə yoxlandı, nə qaldı.

## İkinci hissə (sahib 27.11 18:35 NY: «Başla … ardıcıl, yarımçıq nəsə buraxıb başqa şeyə keçmə, dəqiq plan üzrə et, bitir»)
Seçilən yol: **pulsuz agentlər** (vaxtı məlum rəsmi mənbələr, qiymət sıçrayışı) + **pullu** (FinancialJuice — qəfil xəbər,
Databento — böyük oyunçular, həqiqi həcm, 15 il tarixçə). Hamısı bir axın: giriş → həyəcan → Oxuyucu/beyinlər → Hakim.
Ardıcıllıq: hər addım bitir (test, serverdə yoxlama, bu faylda işarə), sonra növbəti.
- [x] 6.1 Paneldən çıxır: «Etibar işığı», 24 xanalı «GÖZLƏ» cədvəli (yerinə hər metal bir sətir: aralıq + AL/SAT yalnız
      sübutla), «Sabah üçün», «Strateqin izahı» (→ Analitiklər səhifəsi), «Sadə rejim» düyməsi.
- [x] 6.2 Nəticələrdən çıxır: H1–H8, H9–H13, «Analitiklər və tərəzi», «Süzgəc», 2 illik «Fyuçers sınaqları».
- [x] 6.3 Bloklar: uzun izah mətnləri bir-iki sətrə.
- [x] 7.1 Benzinga (Alpaca) xəbəri söndürülür; Google News 10 dəqiqədən bir; Kəşfiyyatçı yalnız həyəcanda; cavabı bəlli
      kölgə sınaqları (ACI, dirijor, FA pəncərəsi, bayram) həftədə bir.
- [x] 8.1 Sıçrayış 1 dəqiqədə tutulur (canlı axından), dərhal səbəb axtarılır.
- [x] 9.1 Rəsmi mənbə agenti: təqvimdəki ABŞ rəqəmi (BLS, BEA) və Fed qərarı dəqiqəsində rəsmi sayt yoxlanır, rəqəm
      gözləntiylə müqayisə olunur, saniyələr içində həyəcan.
- [x] 9.2 Hər xəbərin gəliş vaxtı yazılır: mənbə-mənbə real gecikmə (pul ödəməzdən əvvəlki «əvvəl» rəqəmi).
- [ ] 10.1 Şənbə 28.11: server 1 GB → 2 GB (ayda $6 → $12; sahib «başla» ilə təsdiqlədi), bazar bağlıdır.
- [ ] 11.1 Açarlar gələndə: FinancialJuice + Databento qoşulur, 15 il tarixçə, 1 aylıq sınaq qabaqcadan qeyd olunur.
      (Açarsız sınamaq mümkün deyil — bu addım açarı gözləyir, yarımçıq deyil.)
- [ ] 12.1 Sənədlər və sahibə yekun.

## Sahibsiz qalanlar (sistem onsuz işləyir)
| | Əvəzi | Nə itirilir |
|---|---|---|
| R2 | DigitalOcean gündəlik nüsxəsi (7 gün), həftədə bir API ilə yoxlanır | DigitalOcean hesabı itsə nüsxə də itər |
| Healthchecks | 3 saatlıq növbətçi yoxlama + GitHub saatlıq kənar yoxlama | dəqiqələr içində Telegram xəbəri |
| 2FA | parol + giriş qoruyucusu + bloklama | yalnız sahibin telefonu ilə qurulur |
| Gemini | ehtiyat beyinlər (OpenAI, Anthropic) | — |

## Jurnal (NY saatı)
- 27.11 10:20 — plan təsdiqləndi, iş başladı.
- 27.11 10:33 — Mərhələ 0 bitdi: plan faylı; növbətçi yoxlama və həftəlik hesabat təzə sessiyada (ilk yoxlama 10:47).
- 27.11 10:37 — 1.1: əlaqə xəritəsi (`pipeline.py`): 18 analitikin hamısının səsi, hər mənbə ayrıca (yalançı OK, qismən
  xəta, yoxlanmayan), beyinlərin 24 saatlıq cavabı, Hakimin öz yoxlaması, sahibi gözləyənlər («owner»), cədvəllərin
  təzəliyi. Blokların yoxlaması saatda bir. Köhnə sorğu 14 mln sətri tam oxuyurdu — indi indekslə (bir sorğu).
- 27.11 10:48 — Mərhələ 2 bitdi (2.1 başqa yolla), 3.2 və 3.3 bitdi. Mövsüm/zərgərlik məlumatı silinmir (təmizlik yalnız 26.11 siyahısı).
- 27.11 10:58 — 3.4 və 3.5 bitdi: Q1–Q3 qeydə alındı (13:00 NY-dən sayılır); qeydə alınmış sınaqlar da yalnız vaxtında
  yazılmış proqnozları sayır. 3.1 (birləşdiricilər arxaya) saytın önü ilə birlikdə (Mərhələ 4).
- 27.11 11:07 — Mərhələ 4: 13 səhifə 1366 və 390-da, brauzer xətası 0; 10 səhifədə hər görünən düymə basıldı (Admin xaric — ayar
  dəyişir), xəta 0; yığılmış bölmələr açılanda qrafik ölçüsü sıfır qalmır.
- 27.11 11:13 — 5.1: sənədlər yeniləndi. Növbətçi yoxlama 10:47-də təzə sessiyada uğurla işlədi (sakit, commit yoxdur).
- 27.11 11:16 — **Serverdə yoxlandı** (versiya 76e6e8f, 11:13 NY quruldu, qorunan fayllar «held» olmadı): əlaqə xəritəsində
  20 halqa — 15 işləyir, 2 diqqət (Gemini modeli bağlıdır, iş ehtiyat beyinlə; Hakimin öz yoxlaması — izahlı), 3 sahibin
  addımını gözləyir (Healthchecks, R2, 2FA); blokların yoxlaması 0,4 saatlıq, Xəbər bloku artıq «qırıq» deyil; Google
  News 429 yoxdur; son 1 saatda xəta yoxdur; boş yaddaş 521 MB. Benzinga ümumi axından da 48 saatda yalnız 1 metal başlığı
  verir — mənbə zəifdir, əsas xəbər RSS-dən (316). Plan bitdi.
- 27.11 18:38 — ikinci hissə başladı (6.1 → 12.1 ardıcıl).
- 27.11 18:47 — 6 bitdi: Panel (masaüstü 1831→1566 px, telefon 2973→2449), «Bloklar» 1157→987; strateqin izahı «Analitiklər»də;
  13 səhifə × 2 ölçü, brauzer xətası 0; 10 səhifədə hər düymə basıldı, xəta 0. Kod silinmədi (köhnə fayllar yüklənmir).
- 27.11 18:49 — 7 bitdi: Benzinga söndürüldü (boz, «istifadə olunmur»); Google News 10 dəq (Fed lenti 2 dəq qalır); Kəşfiyyatçı
  yalnız böyük ABŞ rəqəmi ətrafında və xəbər həyəcanında; dirijor və ACI kölgəsi, FA pəncərəsi, bayram sınağı həftədə bir
  (cavabı olmayan 4 kölgə sınağı gündəlik qalır). Testlər 346/346.
- 27.11 18:51 — 8 bitdi: metalın 1 dəqiqəlik şamı adi 1 dəqiqəlik hərəkətin 6 qatı (ən az 0,15 %) olanda dərhal həyəcan;
  həyəcanda Kəşfiyyatçı səbəbi X-də axtarır (gündə ən çox 3 dəfə, xərc sərhədi). 15 dəqiqəlik yoxlama da qalır.
- 27.11 18:54 — 9 bitdi: «snayper» — təqvimdəki ABŞ rəqəmi (BLS: inflyasiya, iş yerləri, işsizlik, maaş, PPI) və Fed qərarı
  dəqiqəsində rəsmi mənbə 3 saniyədən bir, 4 dəqiqə soruşulur; rəqəm tapılan kimi həyəcan (əvvəl dəqiqədə bir + növbəti beyin
  dövrəsi). PCE və ÜDM FRED-dən gəlir (FRED-in öz gecikməsi var — adi dövrə). Hər başlığın gəliş vaxtı yazılır; əlaqə
  xəritəsində «Xəbər gecikməsi» sətri mənbə-mənbə median gecikməni və son ABŞ rəqəminin neçə saniyəyə gəldiyini göstərir.
- 27.11 18:56 — 10.1 hazırlandı: şənbə 10:07 NY bu sessiyaya xatırlatma (`trig_012AQJgmWKiDemgCQXMAxUG2`) — server böyütməni özüm
  edib saytın qayıtdığını yoxlayacağam (disk böyüdülmür ki, lazım olsa $6-a qayıtmaq olsun). 11.1: Admin-də FinancialJuice
  açar xanası; əlaqə xəritəsində FinancialJuice və Databento canlı axını «sizin addımınızı gözləyir» — açar/plan gələndə qoşulur.
