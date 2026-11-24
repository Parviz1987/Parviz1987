# Sinir sistemi v2: araşdırmanın nəticəsi və plan (2026-11-24)

Bu sənəd üç araşdırmaya əsaslanır:
- sübutla nəticə vermiş üsullar və GitHub layihələri;
- OpenAI, Anthropic, Grok, Gemini imkanları, pulsuz məlumat bazaları, DigitalOcean və Cloudflare;
- insan sinir sisteminin iş prinsipləri.

Ana hədəf dəyişmir: qiymətin qalxacağını və ya düşəcəyini əvvəlcədən, sübutla bilmək.

---

## 1. Araşdırmanın 5 əsas həqiqəti

1. **Qısa müddət (15 dəq – 4 saat) üçün qızılda xərcdən sonra sübut olunmuş istiqamət üsulu tapılmadı.**
   Qızıl ABŞ rəqəminə təxminən 90 saniyəyə tam reaksiya verir. Elm reaksiyanın ölçüsünü sübut edib, ondan sonra
   qazanc gətirən davamı isə yox.
2. **Bizim beyinlərin həyəcandan sonrakı 88–100 %-i, çox güman, artıq baş vermiş ilk reaksiyanı ölçür.** Ən məşhur
   araşdırma (Lopez-Lira və Tang) da xəbərdən sonra 90 % tapır, amma deyir ki, o hərəkətlə ticarət etmək olmur. Ona
   görə **ilk iş: düzgün ölçmək.** Beyin fikri yazandan sonrakı ilk real qiymətdən saymalıyıq və «ilk 1–5 dəqiqənin
   istiqaməti» kimi pulsuz sadə qaydanı keçməliyik.
3. **Ən güclü sübutu olan fikir: həftə-ay müddətində trend,** amma tək metal üçün düz çıxma təxminən 51–53 %-dir. Bunu
   4 metal üçün birlikdə, portfel kimi ölçmək lazımdır.
4. **Gecə (Asiya) saatlarında qızıl qalxmağa, ABŞ saatlarında düşməyə meyllidir.** Bir neçə müstəqil mənbə bunu
   göstərir. Yoxlanmağa dəyər.
5. **Beyin müzakirəsi, COT, mövsümilik, zərgərlik təqvimi və ETF axını üçün sübut tapılmadı.** Bunları silmirik,
   Hakim ölçür. Amma «sınaq» statusundadırlar və müddət keçəndə sübut yoxdursa söndürülürlər.

**Statistik xəbərdarlıq:** 480 sınaqla 53 % düzlüyü sübut etmək üçün təxminən 5700 müstəqil proqnoz lazımdır. Ona görə
əvvəlcədən 5–10 əsas fərziyyə seçirik və onları ayrıca, daha az sərt həddlə ölçürük. Qalanı «kəşfiyyat» olaraq qalır.

---

## 2. Sinir sistemi: insan orqanizmi necə işləyir → bizdə nə olacaq

| İnsanda | Necə işləyir | Bizdə indi | Nə əlavə olunur | Necə ölçülür |
|---|---|---|---|---|
| **Hissedici sinirlər** | Siqnal içəri bir istiqamətdə, vaxt nişanı ilə gəlir | Gözlər (qiymət, bazarlar, xəbər, təqvim) | Hər girişə «nə vaxt bilindi» nişanı; beyinə gələcəkdən heç nə düşməsin | Beyin girişlərinin 100 %-i nişanlı |
| **Refleks** | Əl istidən beyindən əvvəl, 30–50 ms-də çəkilir | Risk qapısı (dəqiqədə bir) | **Refleks qatı**: hər qiymətdə risk yoxlaması, beyinsiz, dərhal GÖZLƏ | Refleks gecikməsi; qapı bağlı ikən 0 AL/SAT |
| **Talamus (diqqət süzgəci)** | Lazımsız siqnalı susdurur, yenisini gücləndirir, təkrara öyrəşir | Həyəcan və gündəlik limitlər | **Əhəmiyyət balı**: sürpriz × mənbə etibarı × yenilik; eyni mövzunun təkrarı zəifləyir; həyəcandan sonra «dincəlmə» müddəti | Həyəcan dəqiqliyi: 60 dəqiqədə böyük hərəkət gəldimi |
| **Proqnozlaşdıran beyin** | Beyin girişi əvvəlcədən gözləyir, yalnız gözləntidən fərqi (xətanı) yuxarı ötürür | Proqnoz koridorları var, həyəcan isə xam hərəkətə reaksiya verir | **Xəta həyəcanı**: qiymət öz koridorumuzdan çıxanda beyin oyanır | Koridor ~80 % tutur; xəta həyəcanı xam həyəcandan dəqiqdir |
| **Dopamin (öyrənmə)** | «Gözlənilən − baş verən» fərqi ilə sinapslar güclənir və ya zəifləyir | Tərəzi (Hakimin çəkiləri) | **Öyrənən tərəzi**: hər nəticədən sonra çəki yenilənir, rejimə görə ayrıca; heç kəsin çəkisi tam sıfıra düşmür | Tərəzi bərabər çəkidən və ən yaxşı tək analitikdən yaxşıdır |
| **Vegetativ sistem** | Həyəcan (simpatik) ↔ dinclik (parasimpatik); həyəcan özü sönür | Saatlıq və həyəcanlı rejim | **Vəziyyət: SAKİT / DİQQƏT / HƏYƏCAN**, özü sönür; xərc «termostatı» | HƏYƏCANDA keçən vaxt, xərc hədəfə nə qədər yaxındır |
| **Neyromodulyasiya** | Bir neçə kimyəvi maddə bütün beynin həssaslığını dəyişir | Hədlər sabitdir | 3 ümumi göstərici: **oyanıqlıq** (dalğalanma), **qeyri-müəyyənlik** (beyinlər razı deyil), **sürpriz**. Hədlər bunlara görə dəyişir | Həyəcan dəqiqliyi dalğalı bazarda da sabitdir |
| **Ehtiyat yollar** | Bir hissə zədələnəndə digəri əvəz edir | İkinci beyin, DISABLED nişanı | **Ehtiyat pilləkəni**: iki beyin → bir beyin → yalnız qaydalar (ZƏİF REJİM) → donmuş qərar | «Zədə» testləri: hər hissəni söndürüb yoxlamaq |
| **Yuxu (yaddaşın möhkəmlənməsi)** | Gecə günün təcrübəsi yenidən oynanır, dərslər yaddaşa yazılır | Yoxdur | **Gecə yoxlaması**: günün ən böyük səhvləri → ən çox 3 dərs → əvvəl kölgədə sınaq, faydalıdırsa beyinə verilir; ehtimalların kalibrlənməsi | Hər dərsin kölgədə Brier qazancı |
| **Özünü hiss etmə** | Bədən öz vəziyyətini daim bilir | Agentlər mərkəzi | Hər agentin gecikməsi, xətası, xərci refleksə və tərəziyə təsir edir | Ölü agent 2 dövrdə tapılır |

---

## 3. Bloklar (ardıcıllıq; biri bitmədən o biri başlamır)

| Blok | Nə | Niyə birinci / sonra | Sizdən |
|---|---|---|---|
| **8. Dürüst ölçmə** ✅ | Beyin fikrini yazıldığı andan sonrakı ilk real qiymətdən saymaq, spred daxil; «ilk 1–5 dəqiqənin istiqaməti» rəqibi; əvvəlcədən seçilmiş 5–10 əsas fərziyyə ayrıca; dəyişməz canlı yoxlama dəsti | Yanlış ümiddən qorunmaq: bütün sonrakı qərarlar bu ölçüyə əsaslanır | heç nə |
| **9. Gözlər (pulsuz məlumat)** ✅ | BLS / BEA / DOL rəsmi API-ləri (ABŞ rəqəmlərinin faktı 8:30-da, beyinsiz); Kalshi və Polymarket (Fed qərarı ehtimalları, açarsız); ALFRED (ilk dərc olunmuş dəyərlər: keçmişdə gələcəyə baxmasın); Alpaca ilə gün içi GLD, SLV, TIP, IEF, UUP, GDX; GLD-nin XLSX arxivi; Atlanta Fed ehtimal izləyicisi | Ən böyük məlumat boşluqları pulsuz bağlanır | **BLS və BEA açarı** (pulsuz, e-poçtla qeydiyyat) |
| **10. Refleks, talamus, xəta həyəcanı, vəziyyət** ✅ | Refleks qatı; əhəmiyyət balı və təkrara öyrəşmə; koridordan çıxma həyəcanı; SAKİT / DİQQƏT / HƏYƏCAN; 3 ümumi göstərici | Sinir sisteminin özü | heç nə |
| **11. Öyrənmə və yuxu** ✅ | Öyrənən tərəzi (rejimə görə, sıfıra düşmədən); ehtimalların kalibrlənməsi; gecə yoxlaması və kölgədə sınanan dərslər | Sistem öz səhvindən öyrənsin | heç nə |
| **12. Xərc termostatı** ✅ | Oxuyucu → Claude Haiku (~40 dəfə ucuz); Strateq → Sonnet + 1 saatlıq yaddaş keşi; Opus yalnız müzakirənin hakimi; təcili olmayan işlər yarı qiymətinə (Batch/Flex); Grok X axtarışında nəticə sayı məhdud (indi hər posta görə ödənir) | Eyni limitlə 2–5 dəfə çox beyin işi | heç nə |
| **13. Yeni sınaqlar** ✅ | 4 metal üçün birlikdə trend portfeli (1 həftə – 1 ay); Asiya/ABŞ seansı üsulu; ABŞ rəqəmindən sonra +2/+5/+15 dəqiqədə giriş; fərqli şirkətlərin beyinlərindən kalibrlənmiş ansambl | Sübutu ən çox olan fikirlər | heç nə |
| **14. Server** ✅ | 1 GB yaddaş (indi 512 MB, baza böyüdü); gecəlik baza ehtiyatı Cloudflare R2-yə (pulsuz) | Sabitlik və ehtiyat | **DigitalOcean-da ölçünü 1 GB-a qaldırmaq (+~2 $/ay)**; istəyə görə Cloudflare R2 açarı |

**Pul baxımından:**
- Məcburi alış yoxdur.
- FMP yalnız keçmiş gözləntilər üçün lazım olardı. BLS/BEA faktları, ALFRED isə ilk dəyərləri pulsuz verir, ona görə
  FMP-yə ehtiyac azalıb.
- Server +2 $/ay.

---

## Vəziyyət
- **Blok 8 bitdi.** Tapılan xəta: beyin fikri sorğunun **başladığı** anla qeyd olunurdu, cavab isə dəqiqələr sonra
  gəlirdi. Fikir artıq baş vermiş hərəkətə görə «düz» sayılırdı. İndi hər fikir cavabın gəldiyi anla qeyd olunur.
  Köhnə fikirlər 10 dəqiqə sonradan sayılır və hesabata düşmür. Beyinlərin hesabında indi spreddən sonrakı nəticə və
  «artıq olan hərəkət davam edir» rəqibi də var. 8 əsas fərziyyə 2026-11-24 12:00 UTC-də qeydə alındı (Nəticələr,
  6-cı bölmə).

- **Blok 9–14 bitdi (kod, testlər).** Nə edildi:
  - 9: ABŞ rəqəmlərinin faktı BLS/FRED-dən (beyinsiz, dövrü yoxlanılaraq); Kalshi Fed ehtimalları; Alpaca ilə GLD, SLV,
    GDX, UUP, TIP, IEF gün içi şamları — hamısı beyinlərin faktlarına düşür. ALFRED, GLD XLSX və Atlanta Fed izləyicisi
    götürülmədi: ünvan və ya format bu mühitdən yoxlanıla bilmədi, kor kod yazılmadı.
  - 10: refleks (1 dəqiqədə sıçrayış → həmin metal dərhal GÖZLƏ, 5 dəq); diqqət süzgəci (eyni növ siqnal bir saatda bir
    dəfə); xəta həyəcanı (qiymət öz 1 saatlıq koridorumuzdan çıxanda); SAKİT/DİQQƏT/HƏYƏCAN; oyanıqlıq, fikir
    ayrılığı, sürpriz göstəriciləri; HƏYƏCANDA Strateq 30 dəqiqədə bir.
  - 11: öyrənən tərəzi (Hedge + uzunmüddətli veto); beyin ehtimallarının kalibrlənməsi; gecə yoxlaması (01:00 NY):
    ən çox 3 dərs, ikinci analitikə yalnız cüt günlərdə verilir (A/B).
  - 12: Oxuyucu → Claude Haiku, Strateq → Claude Sonnet (sahibin limiti saxlanır); xərc termostatı: ay sonuna limiti
    keçəcəksə, işlər iki dəfə seyrəlir.
  - 13: «Seans: Asiya ↑ / ABŞ ↓» (1 saat, 4 saat) və «Çoxsürətli trend» (1 həftə – 1 ay).
  - 14: gecəlik ehtiyat nüsxə Cloudflare R2-yə (02:00 NY), açar kartı Admin-də.

## 4. Görünüş təklifləri (PDF üslubunda, hədəfdən yayındırmadan)

1. **Kürənin rəngi sistemin vəziyyətini göstərir.** SAKİT olanda mavi və yavaş, DİQQƏT olanda sarı, HƏYƏCAN olanda
   qırmızımtıl nəbz kimi. Yanında yazı: «HƏYƏCAN: Fed xəbəri, 12 dəq».
2. **Sinir yolu görünüşü:** soldan sağa axın. Gözlər → sinirlər → beyinlər → Hakim → Qərar. Siqnal xətt boyu işıq kimi
   axır, yalnız real hadisə olanda.
3. **Panelin yuxarısında «Qərar lenti».** 4 metal × 6 müddət, hər xanada AL / SAT / GÖZLƏ və səbəbi. Ən vacib məlumat
   birinci görünür.
4. **Qrafikdə proqnoz koridoru və həyəcan nişanları.** Qiymət koridordan çıxanda qrafikdə nişan olur; toxunanda «niyə»
   açılır.
5. **Səs və titrəmə (istəyə görə, telefonda):** yalnız HƏYƏCAN və AL/SAT-da.
6. **Sadə rejim düyməsi:** yalnız qiymət, Qərar lenti və vəziyyət. Gündəlik baxış üçün.

---

## 5. Sizin işləriniz

1. **BLS açarı:** https://data.bls.gov/registrationEngine/ — ad və e-poçt yazırsınız, açar e-poçta gəlir. Admin →
   açarlar bölməsinə qoyulacaq (kartı mən əlavə edəcəyəm).
2. **BEA açarı:** https://apps.bea.gov/API/signup/ — eyni qayda.
3. **DigitalOcean:** droplet → Resize → 1 GB (~6 $/ay). Bunu etsəniz, mən serverdə yoxlayaram.
4. **İstəyə görə Cloudflare R2:** gecəlik ehtiyat nüsxə üçün. Açarı yalnız serverin `.env` faylına yazılır, söhbətə
   yox.
