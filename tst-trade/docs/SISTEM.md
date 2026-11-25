# TST Trade — sistemin vahid xəritəsi

Bura sistemin tək giriş qapısıdır. Burada yazılanlar bunlardır:
- sistem nə üçündür;
- hansı hissələrdən ibarətdir;
- kim nə edir, nəyi haradan alır, nəyi kimə verir;
- harada nəyə baxmaq lazımdır.

Ətraflı sənədlər aşağıdakı «Sənədlər» bölməsindədir. Köhnələnmiş sənədlər orada belə qeyd olunub.

## 1. Ana məqsəd (bir cümlə)

Qızıl, gümüş, platin və palladiumun qalxıb-düşəcəyini və gözlənilən aralığını **əvvəlcədən** demək. Bunun xərcdən
sonra düz olduğunu **Hakimin sübutu** ilə bilmək. Ticarət yalnız sübutdan sonra, sahibin qərarı və limiti ilə olur.

Bütün agentlər, alətlər və beyinlər bu bir məqsədə xidmət edir. Hər birinin dəyəri bir rəqəmlə ölçülür: Hakimin
xərcdən sonra hesabladığı nəticə.

## 2. Quruluş: beş qat (sinir sistemi kimi)

```
Gözlər            → Sinirlər            → Beyin (analitiklər)        → Hakim                 → Qərar
qiymət, bazarlar,    siqnal: güclü xəbər,   kod üsulları (texniki,       hər proqnozu real        risk qapısı;
xəbər, təqvim,       ABŞ rəqəmi, sıçrayış,  fundamental, Fibonacci...),  qiymətlə, xərcdən        AL / SAT yalnız
makro, COT, X,       proqnoz xətası →       AI beyinlər, Bilik kitabı    sonra ölçür; çəkiləri     sübut + açıq qapı;
fyuçers tarixi       beyinləri oyadır       qaydaları → VAHİD PROQNOZ    verir; öyrədir            əks halda GÖZLƏ
```

**Son söz birdir: Vahid proqnoz.** Hər metal və müddət üçün bütün analitiklərin fikri bir ehtimalda birləşir. Çəkiləri
sistem öz keçmişindən addım-addım öyrənir. Tərəzi, Konsensus və ayrı-ayrı səslər ancaq izahdır, ayrıca «son söz»
deyil.

**Qərar lenti** (AL / SAT / GÖZLƏ) yalnız Hakimin sübutu və açıq risk qapısı ilə AL və ya SAT deyir.

## 3. Kim nə edir

| Agent | Qat | Məqsədə xidməti | Girişi | Çıxışı |
|---|---|---|---|---|
| Qiymət axını | Gözlər | Bütün analizin əsası | Capital.com | 4 metal + 8 bazarın şamları |
| Xəbər lentləri, Kəşfiyyatçı (Grok) | Gözlər | Yeni hadisəni tez görmək | RSS, Benzinga, X | Başlıqlar |
| Hadisə birləşdiricisi | Gözlər | Eyni xəbəri bir dəfə saymaq | Başlıqlar | Hadisə nömrəsi |
| İqtisadi təqvim, Rəqəm ovçusu | Gözlər | ABŞ rəqəmi və gözlənti | Forex Factory, BLS, FRED | Fakt − gözlənti |
| Makro və COT, Arxivçi | Gözlər | Fundamental fon | FRED, ALFRED, CFTC, Kalshi | Real faiz, dollar, Fed ehtimalı |
| Sinirlər | Sinirlər | Vacib anı qaçırmamaq | Hamısı | Həyəcan → beyinlər dərhal oyanır |
| Oxuyucu (AI) | Beyin | Xəbərin istiqaməti və gücü | Hadisələr | Xəbər əhvalı |
| Strateq (AI) | Beyin | Fundamental şərh | Faktlar + Bilik kitabı (fundamental) | Ehtimal, səbəb, əks ssenari, qaydalar |
| İkinci analitik (AI, başqa şirkət) | Beyin | Müstəqil ikinci fikir | Eyni faktlar | Ehtimal |
| Müzakirə (AI) | Beyin | Yuxarı və aşağı dəlilləri tərəzidə çəkmək | Eyni faktlar | Ehtimal |
| Qrafik analitiki (AI) | Beyin | Texniki analiz, qrafikə özü baxır | Şamlar, göstəricilər, Bilik kitabı (texniki), kodun tapdığı qaydalar | Ehtimal, səviyyələr, qaydalar |
| Kod üsulları (~20) | Beyin | Ölçülə bilən fikirlər, hər fikrin bir yeri: uzun trend, makro, ABŞ rəqəmləri, dollar/neft, seans, mövsüm, COT, aralıqlar (GARCH, GVZ) | Şamlar, bazarlar, makro | Hər biri ehtimal və aralıq. Köhnə qrafik üsulları (momentum, trend, sıçrayış, RSI, Fibonacci, geri çəkilmə, şam, İçimoku, metal nisbəti, qısa dönüş, saat effekti) 2026-11-25-də çıxarıldı: hamısı texniki analiz blokunun qaydalarının təkrarı idi |
| **Texniki analiz bloku** (qayda dedektorları) | Beyin | Texniki analizin YEGANƏ yeri — 12 növün hamısı (klassik, fiqurlar, şamlar, trend, osilyatorlar, dəyişkənlik, həcm, Fibonacci, Dow/Elliott/Wyckoff, price action, bazarlar arası, sistematik ölçmə, ADX, İçimoku) — 34 qayda (rules.py, patterns.py); proqnoza bir səs: «Qaydalar» (hər fikir ailəsi bir səs, çəki qaydanın o ana qədərki nəticəsindən) | Şamlar, tik həcmi (2026-11-25-dən) | Qayda siqnalları; Hakim hər qaydanı iki cür ölçür: növbəti şam və stop 1 ATR + hədəf 2 ATR (R ilə) |
| Vahid proqnoz | Beyin → Hakim | **Son söz** | Bütün analitiklər | Bir ehtimal + öz-özünü sınaq |
| Hakim | Hakim | Kim düz deyir, sübut | Proqnozlar, qiymət | Status, çəkilər |
| Jurnal katibi | Hakim | Səhvin səbəbini tapmaq | Beyin cavabı | Dondurulmuş proqnoz kartı |
| Mənbə yoxlayıcısı | Hakim | Uydurmanı tutmaq | Beyin cavabı | Uydurma rəqəm sayı |
| Gecə yuxusu | Hakim | Öyrənmək | Günün səhvləri | Kalibrləmə, qayda təklifləri (A/B sınağı) |
| Likvidlik, Risk qapısı | Qərar | Pis anda göstərməmək | Spred, xəbər vaxtı | Qapı açıq / bağlı |
| Qərar | Qərar | Göstərici | Hakim + qapı | AL / SAT / GÖZLƏ |

## 4. Harada nəyə baxmaq

| Sual | Yer |
|---|---|
| Sabah nə olacaq? | Panel → «Sabah üçün proqnoz» (vahid proqnoz, aralıq, səbəblər) |
| İndi AL/SAT varmı? | Panel → Qərar lenti |
| Kim nə qədər düz deyir? | Nəticələr; Panel → Hakim |
| Qaydalar və onların hökmü | Bilik |
| Sistem necə işləyir (canlı)? | Agentlər |
| Məlumat mənbələri sağlamdırmı? | Sistem |
| Açarlar, limitlər, Databento | Admin |

## 5. Sənədlər

| Sənəd | Nə üçündür | Vəziyyət |
|---|---|---|
| `SISTEM.md` (bu sənəd) | Vahid xəritə | **əsas** |
| `plan-v3-yetkin-qerar.md` | Mərhələlər və yekun qərar | qüvvədədir |
| `sinir-sistemi.md` | Sinir sistemi, blok təlimatı, gözləmə siyahısı | qüvvədədir |
| `acarlar.md` | Açarlar: sahibin işləri | qüvvədədir |
| `ehtiyat.md` | Geri qayıtmaq üçün versiyalar | qüvvədədir |
| `monitor/jurnal.md`, `monitor/teklifler.md` | Növbətçi yoxlama, təkliflər | qüvvədədir |
| `istekler-ve-qurulus.md` | Sahibin istəkləri ↔ qurulan | tarixi qeyd |
| `plan-sinir-v2.md`, `yekun-plan.md`, `gece-plani.md`, `gece-hesabati.md`, `karkas-plani.html` | Köhnə planlar | köhnəlib (tarixçə üçün saxlanılır) |

Kodda tək mənbələr: qaydalar `app/playbook.py`, agentlərin xəritəsi `app/activity.py`, beyin yuvaları
`app/registry.py`, üsullar və pasportları `app/forecast.py`, ana məqsəd mətni `app/registry.py` (MISSION).
