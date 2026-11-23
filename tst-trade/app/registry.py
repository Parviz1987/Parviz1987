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
]

# Key places. fields: what the provider gives you (most give one key; Alpaca gives an ID and a secret).
KEY_SLOTS: list[dict] = [
    {"id": "capital", "category": "price", "name": "Capital.com qiymət axını",
     "purpose": "Qiymət hər dəyişəndə dərhal gəlir (gold-api.com 30 saniyədə bir verir). 1 dəqiqə və 1 saat şamları dəqiq "
                "olur. Ancaq qiymət oxunur: kodda ticarət əmri yoxdur. Demo hesabın açarı tövsiyə olunur.",
     "cost": "Pulsuz (Capital.com hesabı ilə).", "url": "https://capital.com/trading/platform/",
     "fields": ["api_key", "login", "password"], "used_by": "Canlı qiymət (açar işləyəndə özü qoşulur)",
     "stage": LIVE},
    {"id": "twelvedata", "category": "price", "name": "Twelve Data açarı",
     "purpose": "Canlı qiymət və keçmiş şamlar (tarixçə). Tarixçə olmadan 1 günlük və 1 həftəlik proqnoz yoxlanmır.",
     "cost": "Pulsuz plan: ancaq qızıl. Pullu plan (Grow, ayda 29–79 $): 4 metal.",
     "url": "https://twelvedata.com/pricing", "fields": ["key"], "used_by": "Qiymət mənbəyi, tarixçə, Hakim",
     "stage": LIVE},
    {"id": "alpaca", "category": "news", "name": "Alpaca xəbər lenti",
     "purpose": "Saniyələrlə gələn başlıqlar (Benzinga). Oxuyucu beyin onları hadisəyə çevirəcək.",
     "cost": "Pulsuz plan var; pullu plan ayda 99 $.",
     "url": "https://app.alpaca.markets/signup", "fields": ["key_id", "secret"],
     "used_by": "Sürətli xəbər (açar yoxlanır; axın növbəti mərhələdə)", "stage": NEXT},
    {"id": "fmp", "category": "calendar", "name": "Financial Modeling Prep",
     "purpose": "İqtisadi təqvim: gözlənti və fakt. Rəqəmin gözləntidən fərqi (sürpriz) bununla ölçülür.",
     "cost": "Pullu, ayda təxminən 49–69 $ (hansı planda olduğu alışdan əvvəl yoxlanmalı).",
     "url": "https://site.financialmodelingprep.com/pricing-plans", "fields": ["key"], "used_by": "Təqvim, hadisə xətti",
     "stage": NEXT},
    {"id": "fred", "category": "macro", "name": "FRED (St. Louis Fed)",
     "purpose": "Real faizlər, dollar indeksi, inflyasiya gözləntisi: uzun üfüqlərin fonu.",
     "cost": "Pulsuz, qeydiyyatla.", "url": "https://fred.stlouisfed.org/docs/api/api_key.html",
     "fields": ["key"], "used_by": "Makro: real faiz, nominal faiz, inflyasiya gözləntisi, dollar (6 saatda bir)",
     "stage": LIVE},
    {"id": "anthropic", "category": "brain", "name": "Anthropic (Claude)",
     "purpose": "Strateq və Nəzarətçi yuvalarının beyni.", "cost": "İstifadəyə görə ödəniş.",
     "url": "https://platform.claude.com", "fields": ["key"], "used_by": "Strateq, Nəzarətçi", "stage": LIVE},
    {"id": "openai", "category": "brain", "name": "OpenAI (GPT)",
     "purpose": "Oxuyucu yuvasının beyni.", "cost": "İstifadəyə görə ödəniş.",
     "url": "https://platform.openai.com/api-keys", "fields": ["key"], "used_by": "Oxuyucu", "stage": LIVE},
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
    {"id": "reader", "name": "Oxuyucu",
     "job": "Başlığı oxuyur: nə oldu, hansı metal, hansı istiqamət, nə qədər güclü, mənbə. Cavab sərt formada.",
     "may_not": "Qiymət yazmaq, proqnoz vermək.",
     "requirements": [("Uydurmamaq", 40), ("Sərt cavab forması", 20), ("Qiymət", 20), ("Sürət", 20)],
     "provider": "openai", "model": "gpt-5.4-nano", "fallback": "gemini", "fallback_model": "gemini-2.5-flash-lite",
     "why": "Vectara (oktyabr 2026): uydurma 3.1 %, ən aşağılardan biri. Grok Fast 17.8 % — bu yuvaya qoyulmur."},
    {"id": "strategist", "name": "Strateq",
     "job": "Proqnoz kartlarını sözlə izah edir, ssenari yazır, yeni qayda fikrini Hakimə sınağa göndərir.",
     "may_not": "Fikri özü işə salmaq; kodun vermədiyi rəqəmi yazmaq.",
     "requirements": [("Maliyyə düşüncəsi", 50), ("Rəqəmlə dəqiqlik", 30), ("Qiymət", 20)],
     "provider": "anthropic", "model": "claude-opus-5-5", "fallback": "gemini", "fallback_model": "gemini-4-argon",
     "why": "Vals maliyyə testlərində 1-ci (67.85 % və 65.59 %); Gemini 4 praktik bərabərdir, ehtiyatdadır."},
    {"id": "reviewer", "name": "Nəzarətçi",
     "job": "Hər sövdələşmə təklifinə baxır: təsdiq, azalt və ya ləğv et, səbəbi ilə.",
     "may_not": "Sövdələşmə açmaq, ölçünü artırmaq, ayar dəyişmək.",
     "requirements": [("Özünə həddən artıq güvənməmək", 50), ("Sərt cavab forması", 25), ("Sabitlik", 25)],
     "provider": "anthropic", "model": "claude-sonnet-5-5", "fallback": "gemini", "fallback_model": "gemini-4-argon",
     "why": "KalshiBench: Claude ailəsi ən az özünə güvənən (xəta 0.120), OpenAI ən çox (0.395)."},
]
BRAIN_IDS = {b["id"] for b in BRAIN_SLOTS}
BRAIN_PROVIDERS = ("anthropic", "openai", "xai", "gemini")
