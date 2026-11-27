"""Every key place, every data source and every brain slot of TST Trade, with its name and purpose.

The admin page is drawn from these lists, so each key place says what it is for, whether it is free or paid, where
to get it and which part of the system uses it. Adding a source means adding one entry here."""
from __future__ import annotations

# Stages: "live" = built and working in this version; "next" = the place is ready, the collector comes next.
LIVE, NEXT = "live", "next"

CATEGORIES = [
    ("price", "Qiymət və qrafik"),
    ("news", "Xəbərlər"),
    ("calendar", "İqtisadi təqvim"),
    ("macro", "Makro: faiz, dollar"),
    ("brain", "Beyinlər (süni intellekt)"),
    ("ops", "Nəzarət: kənar izləmə"),
]

# Key places. fields: what the provider gives you (most give one key; Alpaca gives an ID and a secret).
KEY_SLOTS: list[dict] = [
    {"id": "capital", "category": "price", "name": "Capital.com qiymət axını",
     "purpose": "Qiymət hər dəyişəndə dərhal gəlir (gold-api.com 30 saniyədə bir verir). 1 dəqiqə və 1 saat şamları dəqiq "
                "olur. Ancaq qiymət oxunur: kodda ticarət əmri yoxdur. Demo hesabın açarı tövsiyə olunur.",
     "cost": "Pulsuz (Capital.com hesabı ilə).", "url": "https://capital.com/trading/platform/",
     "fields": ["api_key", "login", "password"], "used_by": "Canlı qiymət (açar işləyəndə özü qoşulur)",
     "stage": LIVE},
    {"id": "databento", "category": "price", "name": "Databento (COMEX fyuçersləri)",
     "purpose": "Qızıl, gümüş, platin və palladium fyuçerslərinin (GC, MGC, SI, PL, PA) illərlə dəqiqəlik şamları və hər "
                "əməliyyatı: real həcm və alanın/satanın tərəfi. Sahibin impuls fikri və «xəbərdən sonra» sınağı "
                "bununla yoxlanır (Mərhələ 2). Heç nə sahibin təsdiqi olmadan alınmır: əvvəl qiymət göstərilir.",
     "cost": "Standard plan ~$199/ay (2026; canlı axın + illərlə tarixçə, şəxsi istifadə) — sahib 27.11 almağa qərar verdi; "
             "plan alınandan sonra canlı axın qoşulacaq (PLAN-27.11 addım 11.1). Hazırda: tarixi məlumat pulsuz kreditdən.",
     "url": "https://databento.com/portal/keys", "fields": ["key"],
     "used_by": "Mərhələ 2 sınaqları (impuls, xəbərdən sonra hərəkət, platin spredi)", "stage": NEXT},
    {"id": "twelvedata", "category": "price", "name": "Twelve Data açarı",
     "purpose": "Canlı qiymət və keçmiş şamlar (tarixçə). Tarixçə olmadan 1 günlük və 1 həftəlik proqnoz yoxlanmır.",
     "cost": "Pulsuz plan: ancaq qızıl. Pullu plan (Grow, ayda 29–79 $): 4 metal.",
     "url": "https://twelvedata.com/pricing", "fields": ["key"], "used_by": "Qiymət mənbəyi, tarixçə, Hakim",
     "stage": LIVE},
    {"id": "alpaca", "category": "news", "name": "Alpaca xəbər lenti",
     "purpose": "Saniyələrlə gələn başlıqlar (Benzinga). Oxuyucu beyin onları hadisəyə çevirəcək.",
     "cost": "Pulsuz plan var; pullu plan ayda 99 $.",
     "url": "https://app.alpaca.markets/signup", "fields": ["key_id", "secret"],
     "used_by": "Söndürülüb 27.11 (48 saatda 1 metal başlığı gətirirdi); sürətli başlıqları FinancialJuice verəcək",
     "stage": LIVE},
    {"id": "financialjuice", "category": "news", "name": "FinancialJuice (sürətli başlıqlar)",
     "purpose": "Saniyələr içində gələn makro, Fed, geosiyasət və xammal başlıqları — vaxtı bilinməyən qəfil xəbər üçün "
                "(vaxtı məlum ABŞ rəqəmləri və Fed qərarı rəsmi mənbədən «snayper»lə gəlir). Oxuyucu hər başlığı "
                "qiymətləndirəcək; gecikməsi əlaqə xəritəsində ölçüləcək.",
     "cost": "Developer API planı ~$99/ay (2026, «beta» səhifə — alışdan əvvəl təsdiqləyin); sahib 27.11 almağa qərar verdi.",
     "url": "https://beta.financialjuice.com/developers", "fields": ["key"],
     "used_by": "Xəbər bloku, həyəcanlar (PLAN-27.11 addım 11.1: açar qoyulandan sonra qoşulur)", "stage": NEXT},
    {"id": "fmp", "category": "calendar", "name": "Financial Modeling Prep",
     "purpose": "İqtisadi təqvim: gözlənti və fakt. Rəqəmin gözləntidən fərqi (sürpriz) bununla ölçülür.",
     "cost": "Pullu, ayda təxminən 49–69 $ (hansı planda olduğu alışdan əvvəl yoxlanmalı).",
     "url": "https://site.financialmodelingprep.com/pricing-plans", "fields": ["key"], "used_by": "Təqvim, hadisə xətti",
     "stage": NEXT},
    {"id": "bls", "category": "calendar", "name": "BLS (ABŞ Əmək Statistikası Bürosu)",
     "purpose": "ABŞ rəqəmlərinin rəsmi faktı (CPI, qeyri-kənd təsərrüfatı iş yerləri, işsizlik, saatlıq qazanc, PPI) "
                "dərc olunan dəqiqədə, beyinsiz. «Hadisə sürprizi» bununla dəqiq işləyir. Açarsız da işləyir, amma gündə "
                "25 sorğu ilə; açarla 500.",
     "cost": "Pulsuz, qeydiyyatla (ad və e-poçt; açar e-poçta gəlir).",
     "url": "https://data.bls.gov/registrationEngine/", "fields": ["key"],
     "used_by": "Rəsmi rəqəmlər → Hadisə sürprizi, siqnal lenti", "stage": LIVE},
    {"id": "r2", "category": "macro", "name": "Cloudflare R2 (gecəlik ehtiyat nüsxə)",
     "purpose": "Hər gecə verilənlər bazasının nüsxəsi serverdən kənarda saxlanır: server itsə, məlumat itmir.",
     "cost": "Pulsuz (10 GB-a qədər).",
     "url": "https://dash.cloudflare.com/?to=/:account/r2/overview",
     "fields": ["account_id", "access_key_id", "secret_access_key", "bucket"],
     "used_by": "Gecəlik ehtiyat nüsxə (Blok 14)", "stage": LIVE},
    {"id": "healthchecks", "category": "ops", "name": "Healthchecks.io (kənar nəzarətçi)",
     "purpose": "Server və vacib işləri hər neçə dəqiqədən bir «sağam» deyir; siqnal gəlməsə Healthchecks.io özü "
                "Telegram-a yazır (server ölsə belə). Açar layihənin API açarıdır (Settings → API Access → "
                "«Create API key», yazma icazəli); 12 yoxlama özü yaradılır.",
     "cost": "Pulsuz (20 yoxlamaya qədər).", "url": "https://healthchecks.io/accounts/signup/",
     "fields": ["key"], "used_by": "Kənar nəzarətçi (plan addımı 1)", "stage": LIVE},
    {"id": "fred", "category": "macro", "name": "FRED (St. Louis Fed)",
     "purpose": "Real faizlər, dollar indeksi, inflyasiya gözləntisi: uzun üfüqlərin fonu.",
     "cost": "Pulsuz, qeydiyyatla.", "url": "https://fred.stlouisfed.org/docs/api/api_key.html",
     "fields": ["key"], "used_by": "Makro: real faiz, nominal faiz, inflyasiya gözləntisi, dollar (6 saatda bir)",
     "stage": LIVE},
    {"id": "anthropic", "category": "brain", "name": "Anthropic (Claude)",
     "purpose": "Strateq və Nəzarətçi yuvalarının beyni.", "cost": "İstifadəyə görə ödəniş.",
     "url": "https://platform.claude.com", "fields": ["key"], "used_by": "Strateq, Nəzarətçi (müzakirə və gecə yoxlaması), Oxuyucu, Qrafik analitiki", "stage": LIVE},
    {"id": "openai", "category": "brain", "name": "OpenAI (GPT)",
     "purpose": "Oxuyucu yuvasının beyni.", "cost": "İstifadəyə görə ödəniş.",
     "url": "https://platform.openai.com/api-keys", "fields": ["key"], "used_by": "İkinci analitik, müzakirənin tərəfləri, Oxuyucu və Qrafik analitikinin ehtiyatı", "stage": LIVE},
    {"id": "xai", "category": "brain", "name": "xAI (Grok)",
     "purpose": "Kəşfiyyatçı yuvasının beyni: X və vebdə axtarış.", "cost": "İstifadəyə görə ödəniş.",
     "url": "https://console.x.ai", "fields": ["key"], "used_by": "Kəşfiyyatçı", "stage": LIVE},
    {"id": "gemini", "category": "brain", "name": "Google (Gemini)",
     "purpose": "Ehtiyat beyin: Oxuyucu və Strateq üçün, Nəzarətçidə ikinci rəy.", "cost": "İstifadəyə görə ödəniş.",
     "url": "https://aistudio.google.com/apikey", "fields": ["key"], "used_by": "Ehtiyat, ikinci rəy", "stage": LIVE},
]
KEY_IDS = {s["id"] for s in KEY_SLOTS}
FIELDS = {s["id"]: s["fields"] for s in KEY_SLOTS}

# Sources that need no key: listed so the admin page shows the whole data map in one place.
FREE_SOURCES: list[dict] = [
    {"id": "goldapi", "category": "price", "name": "gold-api.com",
     "purpose": "Canlı spot qiymət, 4 metal, açarsız. Tarixçə vermir: şamlar canlı qiymətdən yığılır.",
     "cost": "Pulsuz", "stage": LIVE},
    {"id": "rss", "category": "news", "name": "Google News, Fed RSS",
     "purpose": "Qızıl, gümüş, Fed, geosiyasət başlıqları; 2 dəqiqədə bir.", "cost": "Pulsuz", "stage": LIVE},
    {"id": "forexfactory", "category": "calendar", "name": "Forex Factory təqvimi",
     "purpose": "ABŞ rəqəmlərinin vaxtı, gözlənti, əvvəlki və fakt; saatda bir.", "cost": "Pulsuz", "stage": LIVE},
    {"id": "cot", "category": "macro", "name": "CFTC COT hesabatı",
     "purpose": "Böyük fondların (managed money) qızıl, gümüş, platin, palladium fyuçerslərində mövqeyi; həftədə bir "
                "(cümə axşamı çərşənbə axşamının vəziyyəti dərc olunur).", "cost": "Pulsuz", "stage": LIVE},
]

# Brain slots: the job comes first, the brain second. requirements = what the job needs and its weight (sum 100).
BRAIN_SLOTS: list[dict] = [
    {"id": "scout", "name": "Kəşfiyyatçı",
     "job": "X və vebdə ilk xəbəri, şayiəni tapır. Hər tapıntı «yoxlanmamış» etiketi ilə gəlir.",
     "may_not": "Tək mənbə kimi qərara təsir etmək.",
     "requirements": [("X-də axtarış", 50), ("Sürət", 25), ("Qiymət", 25)],
     "provider": "xai", "model": "grok-4.7", "fallback": None, "fallback_model": None,
     "why": "X-i daxildən axtaran yeganə provayder; veb axtarışı 1000 sorğu üçün 5 $ (OpenAI və Anthropic 10 $)."},
    {"id": "hunter", "name": "Rəqəm ovçusu",
     "job": "ABŞ rəqəmi açıqlanandan 2–10 dəqiqə sonra faktiki rəqəmi vebdən tapır, mənbə linki ilə. İki beyin ayrı-ayrı "
            "tapır; rəqəmlər üst-üstə düşməsə, heç biri istifadə olunmur.",
     "may_not": "Rəqəmi təxmin etmək; tək beynin tapdığını istifadə etmək; qiymət yazmaq.",
     "requirements": [("Uydurmamaq", 50), ("Veb axtarışı", 30), ("Qiymət", 20)],
     "provider": "openai", "model": "gpt-5.4-nano", "fallback": "anthropic", "fallback_model": "claude-opus-5-5",
     "why": "İki fərqli şirkətin beyni bir-birini yoxlayır; FMP təqvimi olmadan faktı gətirmək üçün."},
    {"id": "reporter", "name": "Məlumat agentləri (Bazar müxbiri)",
     "job": "Pulsuz rəsmi lenti olmayan fiziki bazar rəqəmlərini dərc olunmuş xəbərlərdə tapır: Hindistan və Çin "
            "premiumu (həftəlik), Hindistanın qızıl ETF axını və idxalı (aylıq). İki beyin ayrı-ayrı tapır, mənbə linki "
            "ilə; rəqəm və dövr üst-üstə düşməsə, heç biri istifadə olunmur.",
     "may_not": "Rəqəmi təxmin etmək və ya hesablamaq; tək beynin tapdığını istifadə etmək; qiymət yazmaq.",
     "requirements": [("Uydurmamaq", 50), ("Veb axtarışı", 30), ("Qiymət", 20)],
     "provider": "gemini", "model": "gemini-2.5-flash", "fallback": "openai", "fallback_model": "gpt-5.4-nano",
     "why": "Hindistan tələbi üçün pulsuz rəsmi gündəlik mənbə yoxdur (IBJA pullu API); həftəlik xəbərlər var. "
            "Sahibin qərarı (2026-11-25): aylıq limit 10 $. 2026-11-26 (sahib: boş duran açarlardan istifadə et): "
            "Gemini Google axtarışı ilə (ayda ~1 500 sorğuya qədər pulsuz) + OpenAI veb axtarışı — iki şirkət."},
    {"id": "ideas", "name": "Fərziyyə agenti",
     "job": "Həftədə bir dəfə tədqiqat yaddaşını oxuyur (hər qaydanın xərcdən sonrakı nəticəsi, rejim və metal üzrə, "
            "əvvəlki fikirlərin taleyi) və ən çox 2 yeni ölçülə bilən fikir təklif edir. Proqram fikri sərt şablonla "
            "qaydaya (HY-) çevirir; Hakim onu hər qayda kimi ölçür, son sınaq və sahibin təsdiqi olmadan işə düşmür.",
     "may_not": "Qiymət yazmaq; şablondan kənar qayda yazmaq; fikri özü işə salmaq.",
     "requirements": [("Tədqiqat düşüncəsi", 50), ("Sərt cavab forması", 30), ("Qiymət", 20)],
     "provider": "anthropic", "model": "claude-sonnet-5-5", "fallback": "openai", "fallback_model": "gpt-5.4-nano",
     "why": "Radar Gold sxemi (R2 + R3), sahibin qərarı 2026-11-25. Həftədə bir sorğu: ayda ~0.2-0.5 $; limit 3 $."},
    {"id": "reader", "name": "Oxuyucu",
     "job": "Başlığı oxuyur: nə oldu, hansı metal, hansı istiqamət, nə qədər güclü, mənbə. Cavab sərt formada.",
     "may_not": "Qiymət yazmaq, proqnoz vermək.",
     "requirements": [("Uydurmamaq", 40), ("Sərt cavab forması", 20), ("Qiymət", 20), ("Sürət", 20)],
     "provider": "anthropic", "model": "claude-haiku-5-5", "fallback": "openai", "fallback_model": "gpt-5.4-nano",
     "why": "Blok 12 (xərc termostatı): Claude Haiku 5.5 GPT-5.4 nano-dan ~2 dəfə ucuzdur (0.10/0.50 $ / 1M), başlıq "
            "etiketi üçün kifayətdir; nano ehtiyatdadır. Vectara: nano uydurma 3.1 %."},
    {"id": "strategist", "name": "Strateq",
     "job": "Proqnoz kartlarını sözlə izah edir, ssenari yazır, yeni qayda fikrini Hakimə sınağa göndərir.",
     "may_not": "Fikri özü işə salmaq; kodun vermədiyi rəqəmi yazmaq.",
     "requirements": [("Maliyyə düşüncəsi", 50), ("Rəqəmlə dəqiqlik", 30), ("Qiymət", 20)],
     "provider": "anthropic", "model": "claude-sonnet-5-5", "fallback": "gemini", "fallback_model": "gemini-4-argon",
     "why": "Blok 12: Opus saatlıq + həyəcanlarla ayda ~30 $ olurdu (limit 20 $); Sonnet 5.5 yarı qiymətinədir. Hakim "
            "beyinin dəyərini ölçür: Sonnet Opus-dan zəif çıxsa, geri qaytarılır."},
    {"id": "analyst2", "name": "İkinci analitik",
     "job": "Strateqlə eyni faktları alır və ondan ayrı, öz ehtimalını verir (1 saat, 4 saat, 1 gün). Hakim hər birini "
            "ayrıca ölçür; vahid proqnozda hər biri öz ölçülmüş nəticəsinə görə çəki alır.",
     "may_not": "Qiymət yazmaq; Strateqin cavabını görmək.",
     "requirements": [("Başqa şirkətdən olmaq (müstəqil fikir)", 50), ("Qiymət", 30), ("Sərt cavab forması", 20)],
     "provider": "openai", "model": "gpt-5.4-nano", "fallback": None, "fallback_model": None,
     "why": "Strateq Claude-dur; müstəqil ikinci fikir üçün başqa şirkət. Ucuz model: saatda bir sorğu ayda ~1-3 $."},
    {"id": "reviewer", "name": "Nəzarətçi",
     "job": "Müzakirənin hakimi: «yuxarı» və «aşağı» tərəfdarlarının dəlillərini faktlarla tutuşdurub ehtimal verir. "
            "Gələcəkdə: hər sövdələşmə təklifinə baxır (təsdiq, azalt, ləğv).",
     "may_not": "Sövdələşmə açmaq, ölçünü artırmaq, ayar dəyişmək; faktda olmayan dəlili saymaq.",
     "requirements": [("Özünə həddən artıq güvənməmək", 50), ("Sərt cavab forması", 25), ("Sabitlik", 25)],
     "provider": "anthropic", "model": "claude-sonnet-5-5", "fallback": "gemini", "fallback_model": "gemini-4-argon",
     "why": "KalshiBench: Claude ailəsi ən az özünə güvənən (xəta 0.120), OpenAI ən çox (0.395)."},
    {"id": "chartist", "name": "Qrafik analitiki",
     "job": "Treyder kimi qrafikə özü baxır: 1 saat, 4 saat və 1 günlük şamlar, səviyyələr, göstəricilər; trendi, dəstək "
            "və müqaviməti, fiqurları yazır və 1 saat, 4 saat, 1 gün ehtimalı verir. Hakim onu ayrıca ölçür.",
     "may_not": "Şamlarda olmayan qiyməti yazmaq; xəbər və makro haqqında danışmaq (bu, başqa analitiklərin işidir).",
     "requirements": [("Qrafik oxuma", 50), ("Qiymət (saatda bir)", 30), ("Sərt cavab forması", 20)],
     "provider": "anthropic", "model": "claude-haiku-5-5", "fallback": "openai", "fallback_model": "gpt-5.4-nano",
     "why": "Sahibin istəyi (2026-11-24): analitik qrafikə özü baxıb texniki analiz etsin. Saatda bir çağırış: ucuz model "
            "ayda təxminən 5-10 $; Hakim faydasını ölçür, fayda yoxdursa, söndürülür."},
]
# One goal for every brain (owner 2026-11-24: «all agents serve one main goal»). Prepended to every brain's
# instructions by brains.run. No digits in it: the source checker counts numbers a brain was not given.
MISSION = (
    "ANA MƏQSƏD (bütün agentlər üçün eynidir): qızıl, gümüş, platin və palladiumun qalxıb-düşəcəyini və gözlənilən "
    "aralığını əvvəlcədən demək; bunun düz olduğunu Hakim real qiymətlə, xərcdən sonra yoxlayır. Sənin işin bu "
    "məqsədin bir hissəsidir: yalnız verilən faktlardan istifadə et, rəqəm uydurma, bilmədiyin yerdə «fikir yoxdur» de "
    "(ehtimal yarıya yaxın), əminliyini şişirtmə — kalibrlənmiş, dürüst ehtimal ən faydalıdır. Sənin fikrin vahid "
    "proqnozda digər analitiklərlə birləşir; çəkisi yalnız sənin ölçülmüş nəticəndən asılıdır (Hakim real qiymətlə "
    "yoxlayır).\n\n")

BRAIN_IDS = {b["id"] for b in BRAIN_SLOTS}
BRAIN_PROVIDERS = ("anthropic", "openai", "xai", "gemini")
