# TST Trade — Bloklar xəritəsi (tək mənbə)

> **Kim üçün:** sahib və hər yeni Claude sessiyası. Sahib «blokları bitir», «filan bloku gücləndir» deyəndə Claude
> **əvvəl bu faylı oxuyur**, sonra işləyir və işi bitirəndə bu faylı yeniləyir (vəziyyət, tarix, nə qaldı).
> Blok sayı dəyişə bilər (27.11: 22) (6, 10, 25 — fərq etməz): yeni blok bu fayla eyni şablonla əlavə olunur.
>
> **Qərarlar harada:** sahibin bütün qərarları `docs/IS-PLANI.md` bölmə 5 (12 addım) və 5.1 (blok qərarları);
> hər qərarın qısası həm də plan səhifəsində (claude.ai/artifact/TdikyZXX1gG51oqyw38YGt, «decisions»).
> **Araşdırmalar:** `docs/research/` (özünü təmir edən sistem; dirijor və rejim çəkiləri).
> **Canlı vəziyyət:** serverdə `/api/diag` → `blocks_audit`, `conductor`, `experiments`, `aci`, `autopsy`,
> `judge_canary`, `heartbeat`, `ops`. Növbətçi təlimatı `.claude/skills/temirci/SKILL.md`, səhvlər
> `docs/monitor/sehvlerim.md`, jurnal `docs/monitor/jurnal.md`.
>
> Son yeniləmə: **2026-11-27 19:10 NY** (Claude; iş planı `docs/PLAN-27.11.md`). Vəziyyət işarələri: ✅ hazır və işləyir · 🟡 qurulub, sübut/məlumat
> gözləyir · 🔧 qismən, işi var · ⛔ yoxdur / dayandırılıb · 👤 sahibin addımı lazımdır.

---

## 0. Ana hədəf və ölçü (dəyişmir)

Sahib metalların (XAU, XAG, XPT, XPD) qalxıb-düşəcəyini və aralığını **əvvəlcədən** bilmək istəyir — **Hakimin
xərcdən sonrakı sübutu ilə**. Qiymət yalnız bazar məlumatı provayderindən gəlir, heç vaxt LLM-dən. Hər blok bir və ya
bir neçə «səs» (forecast method) verir; səslər vahid proqnozda birləşir; Hakim hər şeyi xərcdən sonra yoxlayır.
**Bu gün sübut olunmuş yeganə uğur:** 80 % aralıq (real əhatə ~78–87 %). İstiqamət heç bir blokda hələ sübut deyil.

## 1. Ümumi sxem

```
Qiymət (Capital.com axını; ehtiyat gold-api.com)  →  şamlar (1m…1w)
        │
        ├─► 1 Texniki ─┐
        ├─► 2 Fundamental ─┤
        ├─► 3 Xəbər + məlumat agentləri ─┤   səslər (METHODS)
        ├─► 4 Bazarlar arası ─┤
        ├─► 5 Vaxt və təqvim ─┤
        └─► 6 AI beyinlər (hamısını oxuyur) ─┘
                         │
     7 Birləşdirmə: vahid proqnoz · tərəzi · konsensus · 8 Dirijor (kölgədə) · 9 Aralıq (+ACI kölgədə)
                         │
     10 Hakim (xərc, Holm/Šidák, son sınaq, DSR/PBO/DM/e-dəyər, registr, sahib təsdiqi)
                         │
     11 Risk və qərar (AL/SAT/GÖZLƏ) → kağız ticarət (real pul YOXDUR)
                         │
     Öyrənmə: 12 Hedge çəkiləri · kalibrləmə · 13 Səhv yarılması · 14 Hipotez agenti (HY-)
Sistem qatları: 15 Kənar nəzarətçi · 16 Avtomatik təmir · 17 Beyin keçidi · 18 Qoruyucular · 19 Təhlükəsizlik ·
                20 Ehtiyat nüsxə və baza · 21 Blokların gündəlik yoxlaması
```

Səslərin siyahısı (kodda `app/forecast.py` METHODS): rw, up (etalonlar), tsmom, trendmix, qaydalar, chartist (Texniki),
fundamental, surprise (Fundamental), xeber (Xəbər), bazarlar (Bazarlar arası), vaxt, season, jewel (Vaxt),
strateq, brain2, debate (AI), garch, gvz (yalnız aralıq), consensus, terazi, vahid (birləşdiricilər).
Bilik kitabı qaydaları (`app/playbook.py`, 80 qayda): TA 24, TH 4, PA 3, VOL 4, IM 1 (texniki), FA 19, NW 7, CM 11, TM 7.
Pensiyada (RETIRED, köhnə üsullar indi blok qaydalarıdır): momentum, reversal, trend, breakout, rsi, fib, pullback,
session, sam, ichimoku, pair, macro, cot, news, seans, dollar, oil, risk — arxivi `archive:retired`-də.

---

## 2. Hər blokun kartı (şablon)

Hər blok üçün: **Nə edir · İç quruluşu (alt hissələr, fayllar) · Girişlər → çıxışlar · Əlaqələr · Vəziyyət ·
Nə qalıb · Necə bitirilir (nəyə əsaslanaraq) · Sahibdən**.

### 1. Texniki analiz — `ta` 🟡
- **Nə edir:** şamlardan qrafik qaydaları (dəstək/müqavimət, trend xətləri, pivot, Fibonaççi, formalar, divergensiya,
  həcm), uzun trend (tsmom), çoxsürətli trend (trendmix), qrafik analitiki beyni (chartist, Claude Haiku).
- **İç quruluşu:** `app/ta.py` (öz hesablamamız: swinglər, auto-Fib, formalar), `app/patterns.py`, `app/rules.py`
  (qaydaların aşkarlanması, `rule_signals`, walk-forward çəkilər `Lookup`), `app/playbook.py` (qaydaların mətni),
  səhifə `/ta`. ADX rejimi ilə ayrıca qeyd.
- **Giriş → çıxış:** 1h/4h/1d şamlar, tik və COMEX həcmi → səslər `qaydalar`, `tsmom`, `trendmix`, `chartist`.
- **Vəziyyət (26.11):** bütün qaydalar hesablanır və keçmişdə yenidən oynadılıb (RULES_VER 2026-11-26.1); Hakimdə
  heç bir qayda sübut deyil (62 zəif, 50 yox, 36 az). Qızıl 1h-də `qaydalar` çəkisi 1,24; palladium uzun horizontda
  güclü (1mo 2,6).
- **Nə qalıb:** (a) «tanış olmayan gün» darvazası — 26.11 kölgə sınağı quruldu (`shadow:experiments.unfamiliar`:
  ən yad 20 % gündə səsin düz çıxma payı aşağıdırmı, z > 2 olarsa darvaza sınağa dəyər); nəticəyə görə qərar;
  (b) dirijorun vəziyyət sübutu gələnə qədər gözləmək; (c) həcm məlumatı zəifdir (yalnız tik + COMEX gündəlik).
- **Necə:** yeni qayda yalnız hipotez agenti (HY-) → Hakim → sahib registri yolu ilə; sabit parametrlər əvvəlcədən.
  Əsas: Moskowitz-Ooi-Pedersen (uzun trend), Hurst-Ooi-Pedersen; «sadə orta çox vaxt üstündür» (Timmermann).

### 2. Fundamental — `fund` 🟡
- **Nə edir:** WGC GRAM məntiqi: fürsət xərci (real faiz, dollar), risk, böyümə, mərkəzi bank, mövqe (COT), ABŞ rəqəm
  sürprizləri, ETF axını (Hindistan AMFI rəsmi), fiziki tələb (SGE).
- **İç quruluşu:** `app/fundamental.py` (19 FA qaydası, `Data` — yalnız o an dərc olunmuş dəyərlər, ALFRED ilk dərc),
  `app/surprise.py` (gözlənti vs faktiki), `app/official.py` (BLS/FRED rəsmi rəqəmlər), `app/hunter.py`, səhifə
  `/fundamental`.
- **Vəziyyət:** bütün FA qaydaları «zəif» (~49–50 %). Araşdırma: 2022-dən sonra qızıl–real faiz əlaqəsi qırılıb
  (0,84 → ~0,03–0,07; mərkəzi bankların ~1000 t/il alışı). **Sahibin qərarı (5.1-3):** son 3 ilin pəncərəsi —
  kölgədə ölçülür (`app/shadowtests.py` → `shadow:experiments.fa_window`).
- **Kölgə nəticəsi (26.11):** «son 3 il» bütün keçmişdən **yaxşı deyil** (XAU Brier fərqi +0,00026, interval 0-ı
  əhatə edir; XAG eyni) → canlı çəkilər dəyişmir (bütün keçmiş qalır). Kölgə hər gün davam edir.
- **Nə qalıb:** mərkəzi bank aylıq məlumatı yoxdur (WGC avtomatik yükləməni qadağan edir; IMF gecikmə ilə var).

### 3. Xəbər + məlumat agentləri — `news` 🟡
- **Nə edir:** RSS / Benzinga başlıqları, Kəşfiyyatçı (Grok, X), hadisə birləşdiricisi (eyni xəbər bir dəfə),
  Oxuyucu (Haiku) hər başlığı qiymətləndirir (istiqamət, güc 0–3, mövzu, metallar) → 7 NW qaydası → səs `xeber`.
  İçində **9 məlumat agenti** (`app/reporter.py`): ibja_rate, india_premium, india_imports, rbi_gold, china_premium,
  pboc_gold, wgc_etf, comex_stocks, fomc_next — iki fərqli şirkətin beyni tapır, **ikisi razılaşanda** istifadə olunur.
- **26.11 tapılan əsl səbəb və düzəliş:** etiketlər 23.11-də başlayıb (2341 başlıq, qızılda 1880). Kod **bütün** NW
  qaydalarını ilk etiketdən 7 gün gözlədirdi — səs bütün ilk həftə susurdu (qızılın 6 saatlıq əhvalı −6,8 olduğu
  halda). İndi yalnız «axın sıçrayışı» (NW-SURGE-1) həftə gözləyir (adi axını bilmək üçün); qalanları dərhal.
  Araşdırmaya görə planlı ABŞ rəqəmi və Fed xəbərlərinin çəkisi 1 saatda yarıya sönür (qızıl onları dəqiqələrdə
  qəbul edir), digərləri 2 saatda. NW_VER 2026-11-26.2 — keçmiş yenidən hesablanır. Canlı diaqnostika: diag
  `news_debug`.
- **Araşdırma (docs/research, 26.11):** mənfi xəbər güclüdür (Smales 2014/2015) ✓ bizdə 1,5x; yalnız yüksək
  əlaqəli xəbər işləyir (Groß-Klußmann & Hautsch) ✓ metalı olmayan etiket sayılmır; LLM lüğətdən xeyli dəqiqdir;
  qızıl üçün 1 saat–1 gün xəbər proqnozunun kənar sınaqda sübutu tapılmayıb — sübutu bizim Hakim verəcək.
- **27.11:** Benzinga (Alpaca) yalnız metal ETF tikerləri ilə soruşulurdu — 48 saatda 0 başlıq, amma «ok» deyirdi; indi
  ümumi axından da (yalnız metal adı keçənlər). Google News-un «429 çox sorğu» deyən axını 15→30→60 dəq dincəlir.
- **27.11 axşam (sahib: «xəbər çıxan kimi gəlsin»):** vaxtı məlum ABŞ rəqəmi (BLS) və Fed qərarı dəqiqəsində **«snayper»**
  rəsmi mənbəni 3 saniyədən bir soruşur, tapılan kimi həyəcan (`feeds.sniper`). Benzinga söndürüldü; Google News 10 dəqiqədən
  bir (Fed lenti 2 dəq). Hər başlığın gəliş vaxtı yazılır — əlaqə xəritəsində mənbə-mənbə gecikmə. Qəfil xəbər üçün
  **FinancialJuice** (pullu, Developer $99/ay, 27.12 yenilənir) — **27.11 20:49-dan canlı** (`app/fjnews.py`, bir WebSocket
  qoşulma); təcili 3-cü səviyyə başlıq (qızıl/dollar/Fed/ABŞ/geosiyasət) dərhal həyəcan. Kəşfiyyatçı yalnız böyük rəqəm
  ətrafında və həyəcanda. **1 aylıq sınaq qabaqcadan qeydə alınıb** (`app/paidtrial.py`, 21:00 NY-dən, qərar 22.12): T1
  FinancialJuice → qızıl 15 dəq, T2 Databento böyük əməliyyat → qızıl 15 dəq; tam xərcdən sonra, hədd 0,05/2, ən az 30.
- **Nə qalıb:** (a) qaydaların öz qeydi yığılmalıdır (çəki yalnız müsbət qeydlə); (b) NW-SHOCK-1-i istiqamət yox,
  dalğalılıq/gözlə işarəsinə çevirmək — **kölgə ölçüsü qurulub (27.11):** `shadowtests.news_shock_vol` (böyük xəbərdən
  sonrakı saat, günün eyni saatı ilə) və `geo_shock_vol` (GDELT gərginlik günündən sonrakı gün); gündə bir, diag
  `experiments`; t > 2 çıxsa bayraq təklif olunur; (c) gündəlik geosiyasi risk indeksi (GPR) —
  lisenziya aydınlaşanda; (d) agentlər: Gemini açarı saxlanıb ✅, ilk uğurlar yoxlanacaq.

### 4. Bazarlar arası — `cross` 🟡
- **Nə edir:** dollar (DXY, EUR/USD), JPY, CNH, istiqrazlar, neft, risk (S&P, VIX), korrelyasiya, mis, öncül bazar.
- **İç quruluşu:** `app/crossmarket.py` (CM_VER 2026-11-26.1, 11 qayda: CM-USD-1/2, JPY-1, CNH-1, YLD-1, OIL-1,
  RISK-1/2, CORR-1, CU-1, LEAD-1), `app/markets.py` (RELATED), səhifə `/bazarlar`.
- **Vəziyyət:** bir neçə metalda 1–3 günlük horizontda müsbət çəki (1,1–1,4); bayram günü VIX gəlmir (normal).
- **Nə qalıb:** «hansı bazar qızıldan əvvəl hərəkət edir» — 26.11 kölgə sınağı quruldu (`shadow:experiments.lead_lag`:
  hər bazarın 1 saatlıq hərəkəti qızılın NÖVBƏTİ saatı ilə korrelyasiya, |t| > 3); nəticəyə görə yeni CM qaydası
  hipotez agenti → Hakim yolu ilə. Rejim asılılığı dirijorda ölçülür.

### 5. Vaxt və təqvim — `time` 🟡
- **Nə edir:** sessiyalar (Asiya qalxır, ABŞ enir), London fiksinqi, həftə günü, ay dönüşü, ABŞ bayramları, ABŞ rəqəm
  saatları; mövsüm (`season`), zərgərlik təqvimi (`jewel`: Divali, Çin Yeni ili).
- **İç quruluşu:** `app/timeblock.py` (TM_VER 2026-11-26.1, 7 qayda), `app/slowviews.py` (season, jewel), səhifə
  `/vaxt`. Hadisə tarixləri: FRED (CPI, NFP, ÜDM, PCE — `calendar:history`), Fed iclasları federalreserve.gov-dan
  (`feeds.fomc_dates`, ilk dəfə 26.11 gecəsi).
- **Sahibin qərarı (5.1-1):** mövsüm və zərgərlik istiqamət yox, **dalğalılıq işarəsi** — kölgədə ölçülür
  (`shadow:experiments.festival_vol`). Araşdırma: Baur «payız effekti» ETF dövründə itib; bayramlar dalğalılığı
  artırır, istiqaməti yox.
- **Kölgə nəticəsi (26.11):** bayram öncəsi dalğalılıq fərqi **sübut olunmayıb** (XAU 1,09x, t=0,88, 8 ilin 3-ündə
  yüksək; XAG 1,02x) → aralıq dəyişmir. Hadisə tarixləri: FOMC gəlir; FRED tarixləri səhvi 26.11 düzəldildi.
- **27.11 (plan 3.2):** `season` və `jewel` səsləri **pensiyaya** (7 gündə canlı fikir yox; sahibin 5.1-1 qərarı ilə onlar
  dalğalılıq bayrağıdır, `festival_vol` kölgədə ölçülür). Məlumatları silinmir (təmizlik yalnız 26.11 siyahısını silir).
- **Nə qalıb:** heç nə (kölgə ölçməyə davam edir).

### 6. AI beyinlər — `brain` 🟡
- **Nə edir:** strateq (Claude), ikinci analitik (OpenAI), müzakirə (debate), qrafik analitiki — bütün blokların
  faktlarını və Bilik kitabını oxuyur.
- **İç quruluşu:** `app/brainjobs.py`, `app/brains.py` (yuvalar, aylıq limit, ehtiyat), `app/llm.py`,
  `app/llmrouter.py` (17), `app/brainviews.py` (dürüst qiymətləndirmə), `app/checker.py` (uydurma rəqəm sayğacı),
  `app/learning.py` (kalibrləmə).
- **Vəziyyət:** beyinlər həddən artıq əmindir (məs. brain2 1d «0,6+» deyəndə qalxma ~0 %) — kalibrləmə düzəldir.
  **Gecə dərsləri dayandırılıb** (sahibin qərarı 5.1-2: 526 halda fayda yoxdur).
- **Quruldu (26.11):** `app/braintrial.py` — təklif olunan yeni model 20 sabit tapşırıqla sınanır; sahibin qabaqcadan
  icazə qaydası (eyni şirkət + sınaq aşağı deyil + qiymət ≤ +20 %) saatda bir tətbiq olunur, qalanı Admin-də kart.
  Aylıq beyin hesabatı diag `agents.router.month`.
- **27.11 (plan 3.3, sahib təsdiqlədi):** İkinci analitik və müzakirə hər saat yox, **4 saatda bir** (383 və 93 fikirdə
  şansdan fərq yox, ayın 89 $ beyin xərcinin 36 $-ı). Qrafik analitikinin ehtiyat modeli «39-dan 2» — bu, 26.11 21:22 NY
  düzəldilən cavab kəsilməsi idi, o vaxtdan səhv yoxdur. Gemini: müvəqqəti xətada sınaq 6 saatdan bir təkrar (3 dəfə);
  yeni modelin qiyməti məlum deyil → qərar sahibindədir; məlumat agentləri ehtiyat beyinlə işləyir.
- **Nə qalıb:** 1 həftəlik kölgə (10 %) rejimi yeni model üçün — sınaq sürüşündən sonra əlavə addım (sonraya).

### 7. Birləşdirmə: vahid proqnoz, tərəzi, konsensus ✅
- **27.11 (plan 3.1):** önə yalnız **vahid proqnoz** («sistemin son sözü»): Panelin «Analitiklər nə deyir» bölməsi və
  «Nəticələr»in 7 günlük hesabı onu göstərir; konsensus və tərəzi arxada ölçülür (Hakim, Analitiklər səhifəsi).
  Seçici konsensus sübutlu üsullardan asılı deyil — ən azı iki ailə razı, heç biri əks olanda danışır.
- `app/unified.py` (onlayn logistik reqressiya, walk-forward öz-özünü sınaq, blok dəyəri testi — `unified:ablation`),
  `app/learning.py` (Hedge, tərəzi). Vahid proqnoz Hakimdə `vahid` kimi ölçülür.

### 8. Dirijor (kölgədə) — `app/conductor.py` 🟡
- **Nə edir:** bazar vəziyyəti (hadisə · şok · trend · yan) → hər vəziyyətin öz çəkiləri, ümumi çəkilərə doğru
  büzülmüş (100 ticarət günü); yalnız fikri olan səslər iştirak edir və öyrənir (specialists); Fixed Share 0,005 ilə
  susan səs ölmür; «bilmirəm» xərc həddində; sadə orta ilə gün-gün müqayisə (blok intervalları); «səs oyandı».
- **Vəziyyət:** ilk nəticə — sadə ortanı **keçmədi** (XPT/XPD 1d-də bir az pis). Canlıya təsiri yoxdur.
- **Nə qalıb:** sübut gələrsə canlıya qoşmaq — 👤 sahib qərarı. Əsaslar: Freund et al. 1997, Herbster & Warmuth 1998,
  Elliott & Timmermann 2005, Claeskens et al. 2016; hesabat `reports/Dirijor qatı və rejim çəkiləri.md`.

### 9. Aralıq və ACI — `app/forecast.py`, `app/aci.py` 🟡
- 80 % aralıq keçmiş hərəkətlərdən öyrənilir (✅ sübut olunmuş uğur). ACI (Gibbs & Candès 2021): qaçırış çoxdursa
  genişlənir, azdırsa daralır (γ 0,02 qısa, 0,01 uzun). **Kölgədə keçmişdə sınaq** (`aci:shadow`); sahibin qərarı
  (s9): «əvvəl keçmişdə sınaq, sonra canlı». **Kölgə nəticəsi (26.11):** ACI 16 masanın 14-ündə 77–83 %, indiki
  üsul 15-ində → **üstün deyil, canlıya qoşulmur**; kölgə hər gün davam edir.

### 10. Hakim — `app/judge.py`, `app/rigor.py`, `app/judgeplus.py`, `app/hypotheses.py` ✅ (qorunur)
- Tam xərc (spread + sürüşmə + gecəlik faiz), Holm, Šidák, yalnız artan sınaq sayğacı (fikirlər, kölgə təcrübələri
  da), bir dəfəlik son sınaq + müstəqil yenidən hesablama, registr və sahib təsdiqi. **Gücləndirilmiş (s12):**
  t ≥ 3, DSR ≥ 0,95 (dispersiya döşəməsi), PBO ≤ 0,10, Diebold–Mariano (bazarın öz meylinə qarşı), e-dəyər ≥ 20,
  «inanılmaz yaxşı» → insan yoxlaması; həftəlik öz yoxlaması (20 təsadüfi + 30 % və 100 % gələcəyə baxan qayda);
  canlıda zəifləyən təsdiqli üsul/qayda avtomatik kölgəyə; sadə dildə hökm kartı. Pilləkən: kölgə → son sınaq →
  sahib registri → kağız ticarət; «kiçik/tam real pul» heç vaxt avtomatik deyil (sahib).
- **Öz yoxlaması (26.11):** 20 təsadüfi qaydadan 0 keçdi ✅, tam gələcəyə baxan tutuldu ✅, 30 % baxan (64 % düz)
  tutulmadı ⚠️. Əvvəlki «+12 → +10 bənd» təklifi artıq sahibin qərarı deyil: 26.11 təsdiqlənən avtomatik siyasətə
  görə həddi Hakim həftəlik öz yoxlamasında özü qoyur (10–15 bənd, hamarlanmış; `judgeplus.delta`). 26.11 16:46 NY
  yoxlaması bu koddan əvvəl idi — növbəti həftəlik yoxlamada `judge_canary.margin` görünməlidir.
- **Qorunan fayllar** (`deploy/protected.txt`): dəyişiklik yalnız `Sahib-təsdiqi:` sətri ilə serverə düşür.
- **27.11 (plan 2.1, sahib təsdiqlədi):** öz yoxlamasında 30 % gələcəyə baxan saxta qayda (64 %) nəticə həddinin (10–15
  bənd) altında qalır — nəticəyə görə tutmaq prinsipcə mümkün deyil. «Boz zona + gecikmə testi» sınandı, ikinci göz
  göstərdi ki, qısa üfüqlərdə həqiqi tez sönən üstünlüyü həmişəlik rədd edər — atıldı. Yerinə: hər proqnozun **yazılma
  vaxtı** (`forecasts.created_ts`) qeyd olunur; son sınaq və qeydə alınmış sınaqlar yalnız hədəf vaxtından ƏVVƏL
  yazılanları sayır (nəticədən asılı olmayan qoruyucu).
- **27.11 (plan 3.4, sahib təsdiqlədi): Q ailəsi** — qızıl, 1 saat: Q1 qaydalar, Q2 vahid proqnoz, Q3 qrafik analitiki;
  qeyd 27.11 13:00 NY, hədd 0,05/3, pulla (tam xərcdən sonra), V ailəsi ilə eyni üsul. Niyə: V əsasən həftə/ay
  üfüqüdür (illər), 1 saatda hər saat bir hal — ən tez dürüst cavab. «Nəticələr»in başında V ilə birlikdə.

- **Avtomatik Hakim siyasəti (sahib 26.11 bir dəfə təsdiqlədi, `app/autojudge.py`, qorunur):** hər üsula 0–100 bal
  (ən zəif hissə: xərcdən sonrakı nəticə, bazarın meylinə qarşı bacarıq, sabitlik, müstəqil hal sayı, DSR; son 100
  hal balı yalnız endirə bilər). Pilləkən: < 50 söndürülüb · 50–70 kölgə · 70–85 kiçik kağız payı (risk ¼) · ≥ 85 +
  son sınaq → tam kağız payı. Bir üsula ≤ min(25 %, yarım Kelly), gündə 2 %, zirvədən 10 % düşəndə hər şey dayanır
  (sahib buraxanda yenidən sayılır). Sahibin rəddi, avtomatik kölgəyə qaytarma və uğursuz son sınaq həmişə veto.
  «İnanılmaz yaxşı» həddi Hakimin həftəlik öz yoxlamasından (10–15 bənd, hamarlanmış); şübhədə bir şam gecikmə
  testi avtomatik qərar verir. **Sahibdən yalnız: real pul və bu siyasətin özünü dəyişmək.**
- **Ara yol (sahib 27.11: «ara yolu da et»):** keçmiş üzrə sınaqda (history) balı ≥ 70 olan üsul canlı nəticəsi
  hələ azdırsa da **kölgəyə** keçir (yalnız proqnoz, ticarət yox), canlı nəticəsi səhv tərəfə getmirsə (t > −1) və
  veto yoxdursa. Kağız payı (kiçik/tam) yenə yalnız canlı bal ilə. Keçmiş balı gündə bir dəfə hesablanır; diag
  `autojudge.early_shadow`.

### 11. Risk və qərar, kağız ticarət ✅
- `app/risk.py`, `app/nerve.py`, `app/liquidity.py`, `app/paper.py` (virtual hesab), `app/signals.py`.
- **27.11:** sıçrayış 1 dəqiqədə tutulur (metalın 1 dəqiqəlik şamı adi hərəkətin 6 qatı, ən az 0,15 %) — 15 dəqiqəlik yoxlama
  da qalır; həyəcanda Kəşfiyyatçı səbəbi axtarır (gündə ən çox 3). Panel: «GÖZLƏ» cədvəli yerinə hər metal bir sətir
  (1 saat / 1 gün / 1 həftə 80 % aralığı), AL / SAT yalnız sübutla. AL/SAT yalnız
  Hakimin son sınağı + sahib registri ilə; **real ticarət yoxdur** (👤 heç vaxt Claude qərar vermir).

### 12. Öyrənmə ✅ / 13. Səhv yarılması 🟡 / 14. Hipotez agenti ✅
- 12: Hedge çəkiləri döşəmə ilə, kalibrləmə gecə (dərslər dayandırılıb).
- 13: `app/autopsy.py` (s11, aylıq): Murphy bölgüsü, dilimlər (Bonferroni), «kim yanlış apardı», qərar/nəticə 4 qutu,
  ayın 5 ən böyük səhvi, aralıq sürüşməsi, 8 sabit səbəb → hipotez agentinə ipucu. **26.11:** canlı vahid proqnozun
  fikirli halları hələ azdır (masa başına ≤ 18) → hər gün yenidən işləyir, kifayət qədər hal yığılanda aylığa keçir.
- 14: `app/ideas.py`: bazar günü 14:00 UTC, həftədə ən çox 2 fikir, HY- qaydaları yalnız registr təsdiqindən sonra səs
  verir; ilk iş 29.11.

### 15. Kənar nəzarətçi — `app/heartbeat.py` ✅ 👤
- 12 yoxlama (təcili: panel, qiymət, backup, deploy; qalanı e-poçt icmalı), bazar saatı New York vaxtı, bayram/qısa
  günlər sakit, 3 pis nümunədən sonra «fail»; GitHub Actions saatlıq ehtiyat yoxlama (`.github/workflows/outside-check.yml`).
- 👤 **Açar lazımdır** (aşağıda «Sahibin işləri» 2).
- **27.11:** GitHub-un «saatlıq» ehtiyat yoxlaması faktiki nizamsızdır (GitHub onu 22 saatda 2 dəfə işə salıb). Əsas kənar
  göz — 3 saatlıq növbətçi yoxlama: hər dəfə **təzə sessiyada** (`trig_01VQ4otCpmwHSbgWngdMWzpY`), telefona xəbər; ilk iş
  27.11 10:47 NY uğurlu.

### 16. Avtomatik təmir — `app/repair.py`, `app/ops.py` ✅
- Kataloq: qiymət ehtiyat mənbəyi 30 dəq, WAL sıxma, mühərriki yenidən başlatmaq; limitlər, jurnal `ops_actions`,
  təkrar → araşdırma (Admin-də bağlanır), Admin-də **«Dayandır»**.

### 17. Beyin keçidi — `app/llmrouter.py` ✅
- Hər xəta növünə bir hərəkət, bir təkrar qatı, sorğuya 4 çağırış / 120 s, yarı açıq sınaq, büdcə rezervi, model
  bağlananda təklif (Admin: Təsdiqlə/Rədd et), heç vaxt avtomatik model dəyişməsi.

### 18. Qoruyucular ✅
- Testlər (`python -m pytest -q`, ~290), nəticə izi `tests/fingerprint.json`, test zəiflətmə qoruyucusu
  `scripts/guard_tests.py`, CI `.github/workflows/tests.yml`, deploy qoruyucusu `deploy/update.sh` + `protected.txt`,
  ikinci göz (hər sadə olmayan dəyişiklikdə ayrıca yoxlayıcı agent).

### 19. Təhlükəsizlik ✅ 👤
- Giriş jurnalı, geo-IP (DB-IP Lite), bloklama, başlıqlar; **2FA qurulub, sahib açmalıdır** (aşağıda 3).

### 20. Ehtiyat nüsxə və baza 🔧 👤
- DigitalOcean gündəlik backup (7 gün) ✅ — 26.11 yoxlandı (DO API): 3 nüsxə, sonuncu 26.11 19:00 NY, 4,3 GB.
- Gecəlik R2 nüsxə (`app/backup.py`, 02:00 NY, serverdən kənarda ikinci nüsxə): kod hazırdır, **amma açar saxlanmayıb —
  işləmir** (diag `learning.backup`: «R2 açarı saxlanmayıb»; əvvəl burada səhvən ✅ yazılmışdı). 👤 «Sahibin işləri» 4.
- Təmizlik (`app/cleanup.py`: 1,12 mln sətir silindi), VACUUM 27.11 04:30 UTC (26.11 23:30 NY).

### 21. Blokların gündəlik yoxlaması — `app/blockaudit.py` ✅
- Hər blok: mənbələr, qayda işə düşmələri, səsin fikirləri, Hakim, blokun dəyəri, vəziyyət asılılığı → «sağlam /
  zəif / qırıq» (diag `blocks_audit`). **Hər blok işindən əvvəl buna bax.**
- **27.11:** saatda bir yenilənir (gündə bir idi: Xəbəri düzəlişdən 17 saat sonra da «qırıq» göstərirdi); 14 mln sətri tam
  oxuyan sorğu indekslə bir sorğuya endi. **Əlaqə xəritəsi** (diag `pipeline`, Admin → Sistem): hər analitikin səsi
  (susan / fikri olmayan), hər mənbə ayrıca (yalançı «ok», qismən xəta), beyinlərin cavabı, Hakimin öz yoxlaması,
  sahibi gözləyənlər («sizin addımınızı gözləyir» — heç vaxt «işləyir» yox), cədvəllərin təzəliyi.

### 22. Hadisələr kitabxanası — `app/eventlib.py` 🟡 (27.11)
- **Nə edir:** keçmiş ABŞ rəqəmləri (CPI, NFP, ÜDM, PCE) və Fed qərarları; hər hadisədə o an bilinən (ALFRED ilk
  dərc, sonradan düzəliş yox), nəticə gözləntiyə görə «yuxarı / yaxın / aşağı», dolların trendi və metalların 1 gün,
  1 həftə hərəkəti. Alət: «oxşar hallar» — eyni hadisə eyni nəticə ilə çıxanda neçə dəfə qalxıb, orta %.
- **Gözlənti:** yeni rəqəmlərdə ekspert gözləntisi (təqvim); köhnələrdə əvəzi — son 3 dəyişikliyin ortası («trend
  əvəzi», açıq yazılır). Hər gün özü yenilənir (yeni rəqəm → yeni hadisə).
- **Kölgə sınağı:** hər hadisə yalnız ondan əvvəlki hallarla proqnozlaşdırılır; xərcdən sonra bazarın meylini
  keçməyən metal/horizont beyinlərə **verilmir** (t ≥ 2,5, ≥ 60 hal). Keçənlər strateqin faktlarında
  `history_analogs`. Diag `eventlib`.
- **Geosiyasət (27.11):** GDELT-in (açıq məlumat, mənbə göstərilməklə pulsuz) hər gün dünya xəbərlərində müharibə və
  hərbi zərbə mövzusunun payı, 2017-dən. Pay öz son 90 gününün medianından 1,5 dəfə yuxarı → «orta», 2 dəfə → «böyük»
  hadisə (7 gün ara ilə); gün bitəndən sonra bilinir, hərəkət ondan sonra ölçülür. Dünən belə gün olubsa, kölgə
  sınağından keçən metallarda beyinlər oxşar halları görür.
- **Qalan:** GPR indeksi (lisenziya aydın olanda); hadisə növləri (müharibə / sanksiya / neft) ayrıca — sübut olsa.

---

## 3. «Bloku bitir» tapşırığı gələndə Claude-un qaydası

1. Bu faylı, `docs/IS-PLANI.md` bölmə 5-i, `sehvlerim.md`-ni oxu; `/api/diag`-dan `blocks_audit`, `conductor`,
   `experiments`, `aci`, `autopsy`, `judge_canary`-ni oxu.
2. Blokun kartındakı «Nə qalıb»ı sıra ilə et. Hər iş: əvvəl xətanı/boşluğu göstərən test → kod → bütün testlər →
   ikinci göz → push → serverdə yoxla → bu kartı yenilə (vəziyyət, tarix).
3. Dünya təcrübəsi: yeni üsul əvvəl yoxlanmış mənbələrlə araşdırılır (deep-research), sonra **kölgədə** sınanır,
   sonra Hakim, sonra sahibin qərarı. Parametrlər əvvəlcədən sabit; az vəziyyət; sadə orta etalondur.
4. **Sahibdən soruş** (izahla): pul, nəticə izini dəyişən hər şey, ticarət, açar/model, məlumat silmək, blok/səhifə/
   düymə çıxarmaq. Qalanı Claude özü edir.
5. Yeni blok: bu fayla eyni şablonla kart, `app/blocks.py`-ə giriş, `blockaudit.PREFIX/SOURCES/FEEDS`-ə sətir, Hakim
   ölçüsü, kölgə sınağı.

## 4. Sahibin işləri (👤) — addım-addım

### 1) Gemini açarı (ödənişli)
1. **aistudio.google.com** → Gemini açarı aldığınız Google hesabı ilə daxil olun.
2. Solda **«Get API key»** → açarın yanındakı layihə (project) → **«Set up billing»** → kart əlavə edin.
3. Həmin layihədə açarı kopyalayın (yeni açar lazımdırsa **«Create API key»**).
4. Bizim saytda **Admin** → **«Beyinlər (süni intellekt)»** → **Google (Gemini)** → açarı yapışdırın → **«Saxla»** →
   **«Yoxla»**. Açarı çata yazmayın.
5. Mənə «Gemini qoydum» yazın: agentlərin ilk nəticəsini yoxlayıram. Xərc limiti ayda $10 (aşmır).

### 2) Healthchecks.io (kənar nəzarətçi)
1. **healthchecks.io/accounts/signup/** → pulsuz hesab (e-poçt ilə).
2. Telegram-da **@HealthchecksBot**-u açın → **/start**. Healthchecks saytında **Integrations** → **Telegram** →
   botun verdiyi linkə basıb təsdiqləyin.
3. Saytda **Settings** → **API Access** → **«Create API key»** (yazma icazəli, *read-only* YOX) → açarı kopyalayın.
4. Bizim saytda **Admin** → **«Nəzarət: kənar izləmə»** → **Healthchecks.io** → açar → **«Saxla»** → **«Yoxla»**.
5. 12 yoxlama özü yaranır; Admin-də **«Avtomatik təmir və kənar nəzarətçi»** bölməsində hər birinin son siqnalı
   görünür. Telegram kanalını sonra əlavə etsəniz də olar — saatda bir yoxlanır.

### 3) 2FA (ikiqat yoxlama)
1. Telefonda **Google Authenticator** (və ya Microsoft Authenticator / iPhone «Passwords») quraşdırın.
2. **Admin** → **«İkiqat yoxlama (2FA)»** → **«2FA qur»** → proqramda **«+»** → **«Enter a setup key»** → ekrandakı
   açarı yazın (Ad: TST Trade, növ: Time based).
3. Proqramdakı 6 rəqəmi Admin-dəki xanaya yazıb təsdiqləyin.
4. Ekranda çıxan **8 ehtiyat kodu kağıza yazın** (telefon itsə onlarla girəcəksiniz) → **«Yazdım»**.

### 4) Cloudflare R2 (ikinci ehtiyat nüsxə — serverdən kənarda; istəyə bağlı)
Nə üçün: DigitalOcean nüsxəsi eyni şirkətdədir; R2 nüsxəsi server və ya DigitalOcean hesabı itsə də qalır. Pulsuz
10 GB-a qədərdir (bizim sıxılmış nüsxə ~0,2–0,4 GB), amma Cloudflare R2-ni açmaq üçün kart istəyə bilər — pul
məsələsi olduğu üçün qərar sizindir.
1. **dash.cloudflare.com** → hesab yaradın və ya daxil olun.
2. Solda **R2 Object Storage** → (istəsə ödəniş üsulu əlavə edin) → **Create bucket** → ad: `tst-trade-backup` →
   **Create bucket**.
3. R2 səhifəsində sağda **Account ID**-ni kopyalayın (sonra lazım olacaq).
4. R2 səhifəsində **Manage API tokens** (və ya **API** → **Manage API tokens**) → **Create API token** → icazə
   **Object Read & Write**, yalnız `tst-trade-backup` bucket-i → **Create API Token**. Ekranda bir dəfə görünən
   **Access Key ID** və **Secret Access Key**-i kopyalayın (çata yazmayın).
5. Bizim saytda **Admin** → **«Makro: faiz, dollar»** bölməsi → **Cloudflare R2 (gecəlik ehtiyat nüsxə)** → 4 xana:
   Account ID, Access Key ID, Secret Access Key, bucket adı (`tst-trade-backup`) → **«Saxla»** → **«Yoxla»**.
6. İlk nüsxə həmin gecə 02:00 NY-də gedir; səhəri mənə «R2 qoydum» yazın — nüsxənin çatdığını yoxlayıram.
