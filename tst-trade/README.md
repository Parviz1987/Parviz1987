# TST Trade — proqnoz laboratoriyası

Qızıl, gümüş, platin və palladium üçün canlı qiymət, şam qrafikləri və proqnozlar. **Alış-satış yoxdur.**
Məqsəd: proqnozların həqiqətən düz çıxıb-çıxmadığını canlı ölçmək. Sübut olunan hissə sonra əsas sayta
(pj-trade-gold) hazır alət kimi verilir.

Tam plan və sxem: [`docs/karkas-plani.html`](docs/karkas-plani.html) (brauzerdə açın).


**Vaxt:** sahib Nyu-Yorkda yaşayır: panel, qrafik və hesabatlar vaxtı Nyu-York vaxtı ilə göstərir (məlumat bazası UTC saxlayır).

## Nə var (bu versiya)

| Hissə | Nə edir | Fayl |
|---|---|---|
| Qiymət mənbəyi | Capital.com axını (saniyə-saniyə), gold-api.com (pulsuz), Twelve Data. DEMO yalnız sınaq üçün, ekranda «DEMO» yazılır | `app/providers/` |
| Şamlar | 1 dəq … 1 həftə. Canlı qiymətdən yığılır; tarixçə Capital.com-dan (4 metal), Twelve Data qızılın köhnə günlərini tamamlayır. Gün 22:00 UTC-də bağlanır (metal bazarının günü) | `app/candles.py` |
| Proqnoz üfüqləri | 1 dəqiqə, 1 saat, 1 gün, 3 gün, 1 həftə, 10 gün, 1 ay | `app/forecast.py` |
| Üsullar | Bazis: «Dəyişməz», «Həmişə yuxarı». Yoxlananlar: Momentum, Qısa dönüş, Trend (3 pəncərə), Sıçrayış (20 şam), RSI 30/70, Fibonacci dönüşü, Makro (real faiz + dollar) | `app/forecast.py` |
| Hakim | Hər proqnozu vaxtı çatanda yoxlayır; «sübut» üçün bazisi p < 0.05 ilə üstələmək və Brier balı müsbət olmalıdır. Üst-üstə düşən uzun proqnozlarda say üfüqün şam sayına bölünür | `app/judge.py` |
| Dəqiqlik qrafikləri | Ümumi cədvəl (hər üfüq × hər üsul), zamanla düz çıxma faizi, 50 % / 80 % aralığın tutma faizi | `static/panel.js`, `/api/judge/series` |
| Qrafik alətləri | EMA 20/50/200, Bollinger, Fibonacci, pivot, dəstək/müqavimət, dəyirmi səviyyələr, RSI və MACD paneli, «Texniki xülasə» | `static/chart.js` |
| Fundamental | FRED: real faiz, nominal faiz, inflyasiya gözləntisi, dollar, VIX, S&P 500; CFTC COT (böyük fondların mövqeyi); qızıl üçün izah | `app/feeds.py` |
| Xəbər və təqvim | Google News, Fed RSS, Forex Factory; mühüm ABŞ rəqəmi ətrafında «Hadisə rejimi» | `app/feeds.py` |
| Beyinlər | Kəşfiyyatçı (Grok: X və vebdə canlı axtarış), Oxuyucu (başlıqları qiymətləndirir), Strateq (saatlıq izah). Hakim Oxuyucunun «yuxarı/aşağı» deməsini növbəti 1 saatla yoxlayır | `app/brainjobs.py`, `app/llm.py` |
| Telefon | Proqram kimi quraşdırılır (PWA): «Telefona yüklə» düyməsi; iPhone-da Safari → Paylaş → «Ana ekrana əlavə et» | `static/manifest.webmanifest`, `static/sw.js` |
| Sistem vəziyyəti | `/status`: qiymətlər, mənbələr, açarlar, beyinlər, tarixçə, xəta jurnalı (yalnız sahib) | `static/status.*` |
| Diaqnostika | `/api/diag`: oxumaq üçün açarla, açar və parol göstərmir | `app/diag.py` |

Heç bir süni intellekt qiymət vermir: qiymət yalnız qiymət mənbəyindən gəlir; beyin cavabında rəqəm olan cümlələr silinir.
Alış-satış yoxdur.

## Açar yerləri (admin səhifəsi)

| Açar | Nə üçün | Qiymət |
|---|---|---|
| Twelve Data | Canlı qiymət və tarixçə (1 gün və 1 həftə yoxlaması üçün) | Pulsuz plan ancaq qızıl; Grow ayda 29–79 $ |
| Alpaca | Saniyələrlə gələn xəbər başlıqları | Pulsuz plan var; ayda 99 $ |
| Financial Modeling Prep | İqtisadi təqvim: gözlənti və fakt | Pullu, ayda ~49–69 $ |
| FRED | Real faizlər, dollar | Pulsuz |
| Anthropic | Strateq, Nəzarətçi | İstifadəyə görə |
| OpenAI | Oxuyucu | İstifadəyə görə |
| xAI (Grok) | Kəşfiyyatçı | İstifadəyə görə |
| Google Gemini | Ehtiyat və ikinci rəy | İstifadəyə görə |

Açarlar serverdə `SESSION_SECRET` ilə şifrələnmiş saxlanılır, brauzerə qayıtmır (yalnız son 4 simvol).
Qiymətlər alışdan əvvəl provayderin səhifəsində yoxlanmalıdır.

## Yerli sınaq

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
APP_PASSWORD=test SESSION_SECRET=$(python3 -c "import secrets;print(secrets.token_hex(32))") COOKIE_SECURE=0 PRICE_PROVIDER=demo .venv/bin/uvicorn app.main:create_app --factory --port 8100
```

## Serverə qurulma (DigitalOcean, Ubuntu 24.04)

1. DigitalOcean-da kiçik droplet yaradın (Ubuntu 24.04).
2. Domen varsa, onun A qeydini serverin IP-sinə yönəldin.
3. Droplet Console-da, root kimi:

```bash
curl -fsSLO https://raw.githubusercontent.com/Parviz1987/Parviz1987/HEAD/tst-trade/deploy/setup.sh
bash setup.sh panel.sizin-domen.com
```

Skript parolu iki dəfə soruşur (serverdə yalnız şifrələnmiş hash saxlanır), `SESSION_SECRET`-i özü yaradır, xidməti (`tst-trade`) və HTTPS-i (Caddy) qurur.
Skript repozitoriyanın əsas budağını götürür; başqa budaq üçün `BRANCH=<budaq adı> bash setup.sh ...` yazın.

## Dürüst qeydlər

- 1 dəqiqəlik istiqamət elmi baxımdan təsadüfə yaxındır; panel bunu rəqəmlə göstərəcək.
- «Sübut» statusu üçün: kifayət qədər yoxlama (1 dəq: 300, 1 saat: 200, 1 gün: 250, 1 həftə: 100),
  bazisləri üstələmə (p < 0.05) və müsbət Brier balı lazımdır.
- gold-api.com tarixçə vermir: 1 gün və 1 həftə üçün Twelve Data açarı lazımdır (pulsuz plan yalnız qızıl).

## Mənbə

`app/providers/base.py`, `goldapi.py`, `twelvedata.py`, `app/netutil.py` və açar şifrələməsi (`app/seal.py`)
pj-trade-gold layihəsindən köçürülüb; orada heç nə dəyişdirilməyib.

## Parolu dəyişmək

- **Saytdan:** Admin → «Parol» bölməsi: köhnə parol, yeni parol iki dəfə, «Parolu dəyiş».
- **Parol unudulubsa** (yalnız DigitalOcean konsolundan, çünki sahibliyi ancaq server girişi sübut edir):

```bash
curl -fsSLO https://raw.githubusercontent.com/Parviz1987/Parviz1987/HEAD/tst-trade/deploy/set-password.sh
```

```bash
bash set-password.sh
```
