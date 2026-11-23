# TST Trade — proqnoz laboratoriyası

Qızıl, gümüş, platin və palladium üçün canlı qiymət, şam qrafikləri və proqnozlar. **Alış-satış yoxdur.**
Məqsəd: proqnozların həqiqətən düz çıxıb-çıxmadığını canlı ölçmək. Sübut olunan hissə sonra əsas sayta
(pj-trade-gold) hazır alət kimi verilir.

Tam plan və sxem: [`docs/karkas-plani.html`](docs/karkas-plani.html) (brauzerdə açın).

## Nə var (bu versiya)

| Hissə | Nə edir | Fayl |
|---|---|---|
| Qiymət mənbəyi | gold-api.com (pulsuz, açarsız) və ya Twelve Data (açar). DEMO yalnız sınaq üçün, ekranda «DEMO» yazılır | `app/providers/` |
| Şamlar | 1 dəq, 5 dəq, 15 dəq, 1 saat, 4 saat, 1 gün, 1 həftə — canlı qiymətdən yığılır, tarixçə Twelve Data-dan | `app/candles.py` |
| Proqnoz masaları | 1 dəqiqə, 1 saat, 1 gün, 1 həftə. Hər şam bağlananda növbəti şam üçün proqnoz | `app/forecast.py` |
| Üsullar | «Dəyişməz» və «Həmişə yuxarı» (bazis), «Momentum», «Qısa dönüş». Hamısına eyni volatillik aralığı | `app/forecast.py` |
| Hakim | Hər proqnozu vaxtı çatanda yoxlayır, bazisləri üstələyib-üstələmədiyini statistikayla deyir: «sübut», «yox», «məlumat azdır» | `app/judge.py` |
| Tarixçə üzrə yoxlama | Keçmiş şamlarda addım-addım (hər proqnoz yalnız özündən əvvəlki şamları görür) | `app/engine.py` |
| Açar yerləri | Hər açarın adı, nə üçün olduğu, pulsuz/pullu, haradan alındığı, kim istifadə edir | `app/registry.py`, `app/keys.py` |
| Beyin yuvaları | Kəşfiyyatçı, Oxuyucu, Strateq, Nəzarətçi: iş, tələblər və çəkisi, provayder və model seçimi, ehtiyat, aylıq limit | `app/registry.py`, `app/brains.py` |
| Panel | 4 metal, şam qrafiki üzərində növbəti şamın 50 % və 80 % aralığı, proqnoz kartları, Hakim cədvəli, jurnal | `static/` |

**Hələ qoşulmayanlar (yerləri hazırdır):** xəbər lenti, iqtisadi təqvim, makro məlumat toplayıcıları və beyinlərin
proqnoza qatılması. Beyinlər bu versiyada yalnız saxlanır və yoxlanır («Beyni yoxla»), proqnoz vermir.

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

Skript parolu soruşur, `SESSION_SECRET`-i özü yaradır, xidməti (`tst-trade`) və HTTPS-i (Caddy) qurur.
Skript repozitoriyanın əsas budağını götürür; başqa budaq üçün `BRANCH=<budaq adı> bash setup.sh ...` yazın.

## Dürüst qeydlər

- 1 dəqiqəlik istiqamət elmi baxımdan təsadüfə yaxındır; panel bunu rəqəmlə göstərəcək.
- «Sübut» statusu üçün: kifayət qədər yoxlama (1 dəq: 300, 1 saat: 200, 1 gün: 250, 1 həftə: 100),
  bazisləri üstələmə (p < 0.05) və müsbət Brier balı lazımdır.
- gold-api.com tarixçə vermir: 1 gün və 1 həftə üçün Twelve Data açarı lazımdır (pulsuz plan yalnız qızıl).

## Mənbə

`app/providers/base.py`, `goldapi.py`, `twelvedata.py`, `app/netutil.py` və açar şifrələməsi (`app/seal.py`)
pj-trade-gold layihəsindən köçürülüb; orada heç nə dəyişdirilməyib.
