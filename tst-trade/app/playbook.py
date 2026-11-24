"""Bilik kitabı (Block 25, owner 2026-11-24): our own school of analysis — one source of truth for the rules the
analysts (brains and code) use, how each is applied, when it is void, and where it comes from.

Why it exists: the system must not depend on anyone for ANALYSIS. Prices and information come from outside; how they
are read is ours, written down, versioned and measured. Every rule has an id; analysts cite the ids they used, the
Judge scores every rule separately (rules.py), and the nightly review proposes changes as new or changed rules that
must pass a test before they count. When a forecast fails we can say who failed, by which rule, on which data.

Fields: id, area, name, how (the method, step by step), signal (when it says up / down), void (when it does not apply
or is cancelled), source (where the idea comes from and how strong the evidence is), detector (True: code detects it
in rules.py and the Judge measures it on its own; False: an analyst applies it by reading the facts)."""
from __future__ import annotations

VERSION = "2026-11-24.2"

RULES = [
    # ---------------- Texniki analiz: trend ----------------
    {"id": "TA-TREND-1", "area": "Texniki", "name": "EMA düzülüşü (trend)", "detector": True,
     "how": "EMA 20, 50, 200 hesablanır. Qiymət > EMA20 > EMA50 > EMA200 = yüksələn trend; tərsi = enən trend. "
            "Trend üç vaxt çərçivəsində (1 saat, 4 saat, 1 gün) ayrıca qiymətləndirilir.",
     "signal": "Tam yüksələn düzülüş → yuxarı; tam enən düzülüş → aşağı.",
     "void": "EMA-lar bir-birinə qarışıqdırsa (yatay bazar), qayda susur.",
     "source": "Klassik trend izləmə; Moskowitz-Ooi-Pedersen (2012) trend sübutu güclüdür, qısa üfüqdə zəifdir."},
    {"id": "TA-TREND-2", "area": "Texniki", "name": "Vaxt çərçivələrinin uzlaşması", "detector": True,
     "how": "Böyük çərçivə (1 gün) istiqaməti verir, orta (4 saat) təsdiqləyir, kiçik (1 saat) giriş anını göstərir.",
     "signal": "Üçü eyni istiqamətdədirsə → o istiqamət; ziddirsə → fikir yox.",
     "void": "Böyük çərçivə yataydırsa.",
     "source": "Elder «Triple Screen» (1985); peşəkar praktikada standart, akademik sübutu orta."},
    # ---------------- dəstək / müqavimət, sıçrayış ----------------
    {"id": "TA-SR-1", "area": "Texniki", "name": "Dəstəkdən / müqavimətdən dönüş", "detector": True,
     "how": "Son 100 şamın yerli zirvə və dibləri (hər tərəfdə 3 şamdan yüksək/alçaq) səviyyə sayılır; 2+ toxunuş = güclü. "
            "Qiymət səviyyəyə ATR-in 0,3-ü qədər yaxınlaşıb geri çəkilirsə, dönüş siqnalıdır.",
     "signal": "Dəstəkdə alıcı şamı → yuxarı; müqavimətdə satıcı şamı → aşağı.",
     "void": "Şam səviyyənin o tayında bağlanırsa (qırılma) — dönüş fikri ləğvdir, TA-BRK-1-ə baxılır.",
     "source": "Osler (2000, NY Fed): dəstək/müqavimət səviyyələrində dönüş təsadüfdən tez-tez olur (valyutalarda)."},
    {"id": "TA-BRK-1", "area": "Texniki", "name": "Sıçrayış (breakout)", "detector": True,
     "how": "Şam son 20 şamın ən yüksəyindən yuxarı (və ya ən aşağısından aşağı) BAĞLANIR, şamın aralığı ATR-dən böyükdür.",
     "signal": "Yuxarı qırılma → yuxarı; aşağı qırılma → aşağı.",
     "void": "Növbəti şam səviyyənin içinə qayıdırsa (yalançı qırılma).",
     "source": "Donchian kanalı, «Turtle» qaydaları; trend ailəsi, uzun üfüqdə sübutu var."},
    # ---------------- göstəricilər ----------------
    {"id": "TA-RSI-1", "area": "Texniki", "name": "Trend içində RSI geri çəkilməsi", "detector": True,
     "how": "Yüksələn trenddə (TA-TREND-1) RSI 14 40-dan aşağı düşüb yenidən yuxarı dönür; enən trenddə 60-dan yuxarı "
            "qalxıb aşağı dönür.",
     "signal": "Yüksələn trenddə → yuxarı; enən trenddə → aşağı.",
     "void": "Trend yoxdursa; RSI 20-dən aşağı / 80-dən yuxarıdırsa (həddən güclü hərəkət).",
     "source": "Wilder (1978); trend + osilator birləşməsi praktikada geniş; sübutu qarışıqdır."},
    {"id": "TA-DIV-1", "area": "Texniki", "name": "RSI divergensiyası", "detector": True,
     "how": "Qiymət yeni zirvə edir, RSI isə əvvəlki zirvəsindən aşağıdır (aşağı divergensiya); qiymət yeni dib, RSI "
            "daha yüksək dib (yuxarı divergensiya). Son 30 şam, iki dalğa nöqtəsi arasında.",
     "signal": "Yuxarı divergensiya → yuxarı; aşağı divergensiya → aşağı.",
     "void": "Güclü trenddə tək divergensiya çox vaxt işləmir: ikinci təsdiq (şam fiquru və ya səviyyə) lazımdır.",
     "source": "Klassik osilator təhlili; akademik sübutu zəifdir — Hakim ayrıca ölçür."},
    {"id": "TA-MACD-1", "area": "Texniki", "name": "MACD histoqramının işarə dəyişməsi", "detector": True,
     "how": "MACD (12, 26) xətti siqnal (9) xəttini kəsir: histoqram mənfidən müsbətə və ya tərsinə keçir.",
     "signal": "Müsbətə keçid → yuxarı; mənfiyə keçid → aşağı.",
     "void": "Histoqram sıfır ətrafında tez-tez işarə dəyişirsə (son 10 şamda 3+ keçid).",
     "source": "Appel (1979); trend ailəsi; tək başına sübutu zəifdir."},
    {"id": "TA-BB-1", "area": "Texniki", "name": "Bollinger sıxılması və açılışı", "detector": True,
     "how": "Bollinger (20, 2) eni son 100 şamın ən dar 10 %-indədir (sıxılma), sonra şam bantdan kənarda bağlanır.",
     "signal": "Yuxarı bantdan kənar → yuxarı; aşağı bantdan kənar → aşağı.",
     "void": "Sıxılma olmadan bantdan çıxış — dönüş də ola bilər, qayda susur.",
     "source": "Bollinger (2001); dəyişkənliyin dəstə-dəstə gəlməsi güclü sübutludur (GARCH), istiqaməti zəif."},
    # ---------------- Fibonacci ----------------
    {"id": "TA-FIB-1", "area": "Fibonacci", "name": "Trend içində 38,2–61,8 % geri çəkilmə", "detector": True,
     "how": "1) Dalğa seçimi: son 100 şamda ən əhəmiyyətli dalğa — yerli dibdən (və ya zirvədən) sonrakı ən böyük "
            "hərəkət, ATR-in ən azı 3 qatı. 2) Səviyyələr: dalğanın 23,6 / 38,2 / 50 / 61,8 / 78,6 %-i. 3) Giriş zonası: "
            "38,2–61,8 % arası, xüsusən başqa səviyyə ilə üst-üstə düşürsə (dəstək, EMA50, dəyirmi rəqəm). "
            "4) Təsdiq: zonada dönüş şamı.",
     "signal": "Yüksələn dalğanın geri çəkilməsində zonada dönüş → yuxarı; enən dalğada → aşağı.",
     "void": "Qiymət 78,6 %-dən o tərəfdə bağlanırsa — dalğa pozulub, səviyyələr etibarsızdır.",
     "source": "Praktikada çox yayılmış; akademik sübutu zəifdir (öz-özünü doğruldan səviyyə ola bilər). Hakim ayrıca "
               "ölçür; birləşmə (confluence) olmadan çəkisi azdır."},
    {"id": "TA-FIB-2", "area": "Fibonacci", "name": "Dayaz geri çəkilmə (güclü trend)", "detector": True,
     "how": "Güclü trenddə (TA-TREND-1 tam düzülüş) qiymət yalnız 23,6–38,2 %-ə qədər geri çəkilib davam edir.",
     "signal": "Trend istiqamətində.",
     "void": "50 %-dən dərin geri çəkilmə — artıq «güclü trend» deyil, TA-FIB-1 qaydası işləyir.",
     "source": "Peşəkar praktika; sübutu zəif."},
    {"id": "TA-FIB-EXT", "area": "Fibonacci", "name": "Uzanma hədəfləri 127,2 / 161,8 %", "detector": False,
     "how": "Geri çəkilmədən sonra yeni dalğanın ehtimal olunan hədəfi: əvvəlki dalğanın 127,2 və 161,8 %-i. Yalnız "
            "hədəf/aralıq kimi istifadə olunur, istiqamət vermir.",
     "signal": "İstiqamət vermir; mümkün dayanma yerləri.",
     "void": "Dalğa düzgün seçilməyibsə.",
     "source": "Praktika; sübutu zəif."},
    # ---------------- şam və qrafik fiqurları ----------------
    {"id": "TA-CDL-1", "area": "Texniki", "name": "Udma / çəkic / atan ulduz səviyyədə", "detector": True,
     "how": "Fiqur yalnız səviyyədə (dəstək, müqavimət, Fibonacci zonası) və hərəkətdən sonra sayılır.",
     "signal": "Yuxarı fiqur → yuxarı; aşağı fiqur → aşağı.",
     "void": "Səviyyədən uzaqda və ya yatay bazarda fiqur.",
     "source": "Nison (1991); akademik sübutu zəif və bazardan asılıdır (Marshall-Young-Rose 2006)."},
    {"id": "TA-PAT-1", "area": "Texniki", "name": "Qrafik fiqurları (baş-çiyinlər, ikiqat zirvə/dib, üçbucaq)",
     "detector": False,
     "how": "Qrafik analitiki şamlarda görür: boyun xəttinin qırılması ilə təsdiqlənir; hədəf fiqurun hündürlüyü qədər.",
     "signal": "Qırılma istiqamətində.",
     "void": "Boyun xətti qırılmayıbsa fiqur yoxdur.",
     "source": "Lo-Mamaysky-Wang (2000): bəzi fiqurlar əlavə məlumat daşıyır; təsiri kiçikdir."},
    # ---------------- dəyişkənlik və risk ----------------
    {"id": "TA-ATR-1", "area": "Texniki", "name": "Dəyişkənliyə görə aralıq və stop", "detector": False,
     "how": "ATR 14 gözlənilən hərəkətin ölçüsüdür: stop girişdən 1,5–2 ATR, hədəf ən azı 1,5 qat stop.",
     "signal": "İstiqamət vermir; aralıq və risk ölçüsü.",
     "void": "Böyük xəbər ərəfəsində ATR keçmişi əks etdirir, gələcəyi yox.",
     "source": "Wilder; risk idarəsində standart."},
    # ---------------- Fundamental: qızıl ----------------
    {"id": "FA-RY-1", "area": "Fundamental", "name": "Real faiz (10 illik TIPS)", "detector": False,
     "how": "Real faiz qızıl saxlamağın alternativ xərcidir. Həftəlik dəyişməyə baxılır (FRED DFII10).",
     "signal": "Real faiz düşür → qızıl yuxarı; qalxır → aşağı.",
     "void": "2022-dən sonra mərkəzi bank alışları bu əlaqəni zəiflədib: tək başına həlledici deyil.",
     "source": "Erb-Harvey (2013); WGC modeli; əlaqə uzun müddət güclü, son illərdə zəifləyib."},
    {"id": "FA-USD-1", "area": "Fundamental", "name": "Dollar", "detector": False,
     "how": "Qızıl dollarla qiymətlənir: dollar indeksi (DXY) və EUR/USD hərəkəti.",
     "signal": "Dollar zəifləyir → qızıl yuxarı; güclənir → aşağı.",
     "void": "Böhran anında ikisi birlikdə qalxa bilər (hər ikisi sığınacaqdır).",
     "source": "Geniş sübut; qısa müddətdə güclü əks əlaqə."},
    {"id": "FA-FED-1", "area": "Fundamental", "name": "Fed gözləntisi", "detector": False,
     "how": "Faiz endirimi ehtimalının dəyişməsi (Kalshi, açıqlamalar). Mühüm olan səviyyə yox, GÖZLƏNTİNİN dəyişməsidir.",
     "signal": "Endirim ehtimalı artır → yuxarı; azalır → aşağı.",
     "void": "Bazar dəyişikliyi artıq qiymətə salıbsa (xəbər gözlənilən kimi çıxdı).",
     "source": "Pul siyasəti şokları ədəbiyyatı; FOMC sürprizləri qızılda güclü reaksiya yaradır."},
    {"id": "FA-SURP-1", "area": "Fundamental", "name": "ABŞ rəqəmi sürprizi", "detector": False,
     "how": "Fakt ilə gözlənti fərqi (CPI, qeyri-kənd iş yerləri, işsizlik, ÜDM, PCE). Reaksiyanın çoxu 90 saniyədə bitir.",
     "signal": "Zəif iqtisadiyyat / aşağı inflyasiya sürprizi → qızıl yuxarı; güclü → aşağı.",
     "void": "Gözlənti məlumatı yoxdursa — uydurulmur, qayda susur.",
     "source": "Smales-Yang (2015); Elder-Miao-Ramchander (2012)."},
    {"id": "FA-COT-1", "area": "Fundamental", "name": "Fondların mövqeyi (COT) ifrat halda", "detector": False,
     "how": "CFTC: idarə olunan fondların xalis mövqeyi son 3 ilin aralığında ən yüksək və ya ən aşağı 20 %-də "
            "(kodda «COT» üsulu eyni həddi işlədir).",
     "signal": "İfrat uzun mövqe → aşağı risk (əks fikir); ifrat qısa → yuxarı.",
     "void": "Həftəlik məlumat: qısa üfüq üçün deyil.",
     "source": "Sanders-Irwin-Merrin; sübutu qarışıqdır."},
    {"id": "FA-CB-1", "area": "Fundamental", "name": "Mərkəzi bank və ETF axını", "detector": False,
     "how": "Mərkəzi bankların alışı (WGC, aylıq) və ETF ehtiyatları uzun müddətli dəstəkdir.",
     "signal": "Güclü alış → uzun üfüqdə yuxarı.",
     "void": "Gün içi və saatlıq proqnoz üçün istifadə olunmur.",
     "source": "WGC hesabatları; 2022-2025 alışları qiymətin əsas dayağı olub."},
    {"id": "FA-GEO-1", "area": "Fundamental", "name": "Geosiyasi risk", "detector": False,
     "how": "Müharibə, sanksiya, böhran xəbərləri (Oxuyucu güc 3). Sığınacaq tələbi.",
     "signal": "Yeni risk → yuxarı; risk azalır → aşağı.",
     "void": "Təkrar yayılan köhnə xəbər (hadisə birləşdiricisi) yeni risk deyil.",
     "source": "Baur-Lucey (2010): qızıl böhranda sığınacaqdır; təsir qısa ömürlü ola bilər."},
    {"id": "FA-SEAS-1", "area": "Fundamental", "name": "Mövsümilik", "detector": False,
     "how": "Eyni ayın keçmiş illərdəki istiqaməti: ən azı 5 il və illərin 70 %-i eyni istiqamətdədirsə meyl verilir "
            "(kodda «Mövsümilik» üsulu).",
     "signal": "Tarixən güclü ay → yuxarı meyl.",
     "void": "Zəif sübut: yalnız kiçik çəki.",
     "source": "Baur (2013) qızılda mövsümilik."},
    {"id": "FA-PGM-1", "area": "Fundamental", "name": "Platin və palladium: sənaye və təklif", "detector": False,
     "how": "Avtomobil satışı və katalizator tələbi; Cənubi Afrika (platin) və Rusiya (palladium) hasilatı və sanksiyalar.",
     "signal": "Təklif pozulur / tələb artır → yuxarı.",
     "void": "Məlumat aylıqdır; gün içi üçün deyil.",
     "source": "Johnson Matthey PGM hesabatları."},
    # ---------------- Bazarlar arası ----------------
    {"id": "IM-RATIO-1", "area": "Bazarlar arası", "name": "Metal nisbəti ifrat halda", "detector": True,
     "how": "Qızıl/gümüş və platin/palladium nisbətinin z-dəyəri son 100 şamda |z| > 2.",
     "signal": "Bahalanmış metal → aşağı, ucuzlaşmış → yuxarı.",
     "void": "Nisbət struktur dəyişirsə (yeni rejim), orta qayıdış gec gəlir.",
     "source": "Cüt ticarəti (pairs trading), Gatev-Goetzmann-Rouwenhorst (2006)."},
    {"id": "IM-RISK-1", "area": "Bazarlar arası", "name": "Risk əhvalı (VIX, səhm)", "detector": False,
     "how": "VIX sıçrayır, S&P düşür: likvidlik satışı qızılı da qısa müddət endirə bilər, sonra sığınacaq tələbi.",
     "signal": "Böhranın ilk saatları → qeyri-müəyyən; sonra → yuxarı.",
     "void": "Sakit bazarda əlaqə zəifdir.",
     "source": "2008, 2020 epizodları; sübutu epizodikdir."},
]

BY_ID = {r["id"]: r for r in RULES}
AREAS = ("Texniki", "Fibonacci", "Fundamental", "Bazarlar arası")


def text_for(areas: tuple[str, ...], records: dict | None = None, extra: list[dict] | None = None) -> str:
    """The rules of some areas as compact text for a brain, with each rule's measured record when there is one."""
    lines = [f"BİLİK KİTABI v{VERSION} — bu qaydalara əsaslan, istifadə etdiyin qaydanın id-sini 'rules' sahəsində yaz."]
    for r in RULES + list(extra or []):
        if r["area"] not in areas:
            continue
        rec = (records or {}).get(r["id"])
        tail = f" [Hakim: {rec}]" if rec else ""
        lines.append(f"- {r['id']} {r['name']}: {r['how']} SİQNAL: {r['signal']} LƏĞV: {r['void']}{tail}")
    return "\n".join(lines)
