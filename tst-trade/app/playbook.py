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

VERSION = "2026-11-25.3"

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
    {"id": "TA-FIB-EXT", "area": "Fibonacci", "name": "Uzanma hədəfləri 127,2 / 161,8 %", "detector": True,
     "how": "Dalğa (dib → zirvə), geri çəkilmə, sonra yeni dalğa. Hədəf zonası: geri çəkilmənin dibindən əvvəlki "
            "dalğanın 127,2–161,8 %-i qədər. Qiymət bu zonaya çatıb əks şam bağlayanda mənfəət götürülür.",
     "signal": "Yuxarı dalğa zonada satıcı şamı → aşağı (düzəliş); aşağı dalğada alıcı şamı → yuxarı.",
     "void": "Dalğa düzgün seçilməyibsə.",
     "source": "Praktika; sübutu zəif."},
    # ---------------- şam və qrafik fiqurları ----------------
    {"id": "TA-CDL-1", "area": "Texniki", "name": "Udma / çəkic / atan ulduz səviyyədə", "detector": True,
     "how": "Fiqur yalnız səviyyədə (dəstək, müqavimət, Fibonacci zonası) və hərəkətdən sonra sayılır.",
     "signal": "Yuxarı fiqur → yuxarı; aşağı fiqur → aşağı.",
     "void": "Səviyyədən uzaqda və ya yatay bazarda fiqur.",
     "source": "Nison (1991); akademik sübutu zəif və bazardan asılıdır (Marshall-Young-Rose 2006)."},
    {"id": "TA-PAT-1", "area": "Texniki", "name": "İkiqat zirvə / ikiqat dib", "detector": True,
     "how": "Son 40 şamda iki təsdiqlənmiş zirvə (və ya dib) arası ən azı 5 şam, hündürlük fərqi ≤ 0,5 ATR, aralarındakı "
            "dib (boyun xətti) ən azı 2 ATR aşağıda. Şam boyun xəttindən o tərəfdə bağlananda fiqur tamamlanır; hədəf "
            "fiqurun hündürlüyü qədər.",
     "signal": "İkiqat zirvə → aşağı; ikiqat dib → yuxarı.",
     "void": "Boyun xətti qırılmayıbsa fiqur yoxdur; qırılandan sonra qiymət yenidən zirvədən yuxarı çıxarsa ləğv.",
     "source": "Bulkowski (2005); Lo-Mamaysky-Wang (2000): bəzi fiqurlar əlavə məlumat daşıyır; təsiri kiçikdir."},
    {"id": "TA-PAT-HS", "area": "Texniki", "name": "Baş-çiyinlər / tərs baş-çiyinlər", "detector": True,
     "how": "Üç ardıcıl zirvə: ortadakı (baş) ikisindən ən azı 0,5 ATR yüksək, çiyinlər bir-birindən ≤ 1 ATR fərqli. "
            "Boyun xətti — aralarındakı ən aşağı dib. Şam boyun xəttinin altında bağlananda tamamlanır.",
     "signal": "Baş-çiyinlər → aşağı; tərs baş-çiyinlər → yuxarı.",
     "void": "Boyun xətti qırılmayıbsa; qırılmadan sonra sağ çiyin yuxarı keçilərsə.",
     "source": "Edwards-Magee (1948); Lo-Mamaysky-Wang (2000), Osler (2000): təsiri kiçik, bazardan asılı."},
    {"id": "TA-PAT-TRI", "area": "Texniki", "name": "Üçbucaq (sıxılan aralıq)", "detector": True,
     "how": "Son 60 şamda iki zirvə enir, iki dib qalxır (xətlər yaxınlaşır). Şam yuxarı və ya aşağı xəttdən kənarda "
            "bağlananda qırılma.",
     "signal": "Qırılma istiqamətində.",
     "void": "Qırılmadan sonra qiymət üçbucağın içinə qayıdırsa — yalançı qırılma.",
     "source": "Edwards-Magee; Bulkowski: üçbucaqlarda yalançı qırılma tez-tez olur."},
    {"id": "TA-PAT-WEDGE", "area": "Texniki", "name": "Paz (yüksələn / enən)", "detector": True,
     "how": "Zirvələr də, diblər də eyni tərəfə gedir, amma xətlər yaxınlaşır (hərəkət zəifləyir). Yüksələn paz aşağı "
            "xəttdən, enən paz yuxarı xəttdən qırılır.",
     "signal": "Yüksələn paz qırıldı → aşağı; enən paz qırıldı → yuxarı.",
     "void": "Qırılma olmadan paz davam edirsə.",
     "source": "Edwards-Magee; Bulkowski; sübutu zəif."},
    {"id": "TA-PAT-FLAG", "area": "Texniki", "name": "Bayraq (güclü hərəkətdən sonra fasilə)", "detector": True,
     "how": "6 şamda ən azı 3 ATR güclü hərəkət (dirək), sonra 4–15 şamlıq dar fasilə (dirəyin yarısından dar, "
            "yarısından az geri çəkilmə). Fasilənin sərhədi hərəkət istiqamətində qırılanda.",
     "signal": "Dirəyin istiqamətində.",
     "void": "Fasilə dirəyin yarısından çox geri çəkilirsə — bayraq deyil.",
     "source": "Bulkowski: davam fiqurlarının ən etibarlısı sayılır; akademik sübutu orta."},
    {"id": "TA-LDN-1", "area": "Texniki", "name": "London aralığının qırılması (OCO)", "detector": True,
     "how": "1 saatlıq qrafikdə Asiya saatlarının (London vaxtı 00:00–07:00, yay vaxtı nəzərə alınır) aralığı — 7 şamın "
            "hamısı olmalı, eni ən azı 0,3 ATR. London və Nyu-York saatlarında (07:00–16:00) şam aralıqdan 0,1 ATR "
            "o tərəfdə ilk dəfə bağlananda. Gündə yalnız birinci qırılma; bir şam hər iki tərəfi keçərsə — qeyri-müəyyən, "
            "siqnal yoxdur.",
     "signal": "Zirvə qırıldı → yuxarı; dib qırıldı → aşağı.",
     "void": "Böyük xəbərdən əvvəl yalançı qırılma olur; bazar bağlı gün və natamam seans siqnal vermir.",
     "source": "Radar Gold dizaynı (gold-breakout-lab, OCO); sessiya aralığı qırılması — gündəlik treyderlərin klassik "
               "qurulumu; müəllifin gəlir iddiaları yoxlanmayıb, Hakim ölçür."},
    {"id": "TA-TL-1", "area": "Texniki", "name": "Trend xətti (maili)", "detector": True,
     "how": "Yüksələn xətt son iki təsdiqlənmiş yüksələn dibdən, enən xətt son iki enən zirvədən çəkilir. Qiymət xəttə "
            "toxunub trend istiqamətində şam bağlayır (sıçrayış) və ya xəttin o tərəfində 0,2 ATR-dən çox bağlanır "
            "(qırılma).",
     "signal": "Xəttdən sıçrayış → trend istiqamətində; xəttin qırılması → əks istiqamətdə.",
     "void": "Xətt yalnız iki nöqtəyə söykənir; üçüncü toxunuş olmadan etibarı azdır.",
     "source": "Edwards-Magee, Murphy (1999); sübutu zəif, praktikada çox yayılmış."},
    {"id": "TA-ICHI-1", "area": "Texniki", "name": "İçimoku buludu", "detector": True,
     "how": "Tenkan (9), Kijun (26), bulud (Senkou A/B, 26 şam irəli çəkilmiş). Qiymət buluddan yuxarı və Tenkan > Kijun "
            "— yüksələn; buluddan aşağı və Tenkan < Kijun — enən. Qayda vəziyyət bu şamda dəyişəndə işə düşür.",
     "signal": "Yüksələn vəziyyətə keçid → yuxarı; enən vəziyyətə keçid → aşağı.",
     "void": "Qiymət buludun içindədirsə və ya xətlər ziddirsə.",
     "source": "Hosoda (1969); trend izləmənin bir forması, sübutu orta-zəif. 2026-11-25-ə qədər ayrıca proqnoz üsulu idi, "
               "bloka köçürüldü."},
    {"id": "TA-ADX-1", "area": "Texniki", "name": "ADX: trendin gücü", "detector": True,
     "how": "ADX 14 (Wilder) trendin gücünü ölçür, istiqamətini yox: 20-dən aşağı — trend yoxdur (yan-yana bazar), "
            "20–25 — formalaşır, 25-dən yuxarı — güclü trend. İstiqaməti +DI və −DI verir. Qayda: ADX 25-i aşağıdan "
            "yuxarı keçəndə. Hakim əlavə olaraq HƏR qaydanı üç ADX rejimində ayrıca ölçür (süzgəc): trend qaydaları "
            "güclü trenddə, dönüş qaydaları trendsiz bazarda daha yaxşı olmalıdır; «Qaydalar» analitiki qaydanın "
            "çəkisini indiki rejimdəki nəticəsindən götürür.",
     "signal": "ADX 25-i keçdi, +DI > −DI → yuxarı; −DI > +DI → aşağı.",
     "void": "ADX gec gələn göstəricidir: trendin sonunda da yüksək qala bilər.",
     "source": "Wilder (1978); trend süzgəci kimi geniş işlənir, sübutu orta."},
    {"id": "TA-STOCH-1", "area": "Texniki", "name": "Stoxastik (14, 3)", "detector": True,
     "how": "%K son 14 şamın aralığında bağlanışın yeri, %D onun 3 şamlıq ortası. 20-dən aşağıda %K %D-ni yuxarı "
            "kəsir — həddən artıq satılmışdan çıxış; 80-dən yuxarıda aşağı kəsir — həddən artıq alınmışdan çıxış.",
     "signal": "Aşağı zonada yuxarı kəsişmə → yuxarı; yuxarı zonada aşağı kəsişmə → aşağı.",
     "void": "Güclü trenddə osilyator uzun müddət ifrat zonada qalır — trendə qarşı siqnal zəifdir.",
     "source": "Lane (1950-ci illər); RSI ilə çox oxşardır; sübutu zəif."},
    {"id": "TA-PIVOT-1", "area": "Texniki", "name": "Pivot nöqtələri (S1 / R1)", "detector": True,
     "how": "Əvvəlki günün (gündəlik qrafikdə əvvəlki həftənin) zirvə H, dib L, bağlanış C: P = (H+L+C)/3, R1 = 2P − L, "
            "S1 = 2P − H. Qiymət S1-ə toxunub alıcı şamı ilə bağlanır və ya R1-ə toxunub satıcı şamı ilə bağlanır.",
     "signal": "S1-dən dönüş → yuxarı; R1-dən dönüş → aşağı.",
     "void": "Böyük xəbər günü səviyyələr asan qırılır.",
     "source": "Gündəlik treyderlərin standart səviyyəsi; öz-özünü doğruldan səviyyə ola bilər, sübutu zəif."},
    # ---------------- Nəzəriyyələr ----------------
    {"id": "TH-DOW-1", "area": "Nəzəriyyə", "name": "Dow: zirvə-dib quruluşu", "detector": True,
     "how": "Son iki təsdiqlənmiş zirvə və iki dib: hər ikisi yüksəlirsə yüksələn trend, hər ikisi enirsə enən trend. "
            "Trend əks siqnal gələnə qədər davam edir.",
     "signal": "Yüksək zirvə + yüksək dib → yuxarı; alçaq zirvə + alçaq dib → aşağı.",
     "void": "Zirvə və dib fərqli tərəfə gedirsə (qarışıq quruluş).",
     "source": "Dow, Hamilton, Rhea (1900–1932); trend izləmənin kökü, müasir sübutu trend araşdırmaları ilə ortaqdır."},
    {"id": "TH-ELL-1", "area": "Nəzəriyyə", "name": "Elliott: 3-cü dalğanın başlanğıcı", "detector": True,
     "how": "Dib → zirvə (1-ci dalğa) → dib (2-ci dalğa: 1-cinin 38,2–78,6 %-i, başlanğıcdan aşağı enmir). Qiymət 1-ci "
            "dalğanın zirvəsini keçəndə 3-cü dalğa (adətən ən güclüsü) başlayır.",
     "signal": "Yuxarı quruluşda → yuxarı; aşağı quruluşda → aşağı.",
     "void": "2-ci dalğa 1-cinin başlanğıcından o tərəfə keçərsə, sayım səhvdir.",
     "source": "Elliott (1938), Frost-Prechter; dalğa sayımı subyektivdir — burada yalnız yoxlanıla bilən an götürülüb. "
               "Akademik sübutu yoxdur, Hakim ölçür."},
    {"id": "TH-ELL-2", "area": "Nəzəriyyə", "name": "Elliott: 5 dalğa tamamlandı", "detector": True,
     "how": "Beş ardıcıl dalğa üç qaydaya uyğundur: 2-ci başlanğıcdan aşağı enmir, 3-cü ən qısa deyil, 4-cü 1-cinin "
            "zirvəsinə girmir. 5-ci dalğa 3-cünün zirvəsini keçib əks şamla geri bağlananda düzəliş gözlənir.",
     "signal": "Yuxarı 5 dalğadan sonra → aşağı; aşağı 5 dalğadan sonra → yuxarı.",
     "void": "Qiymət 5-ci dalğanın ucundan o tərəfdə möhkəmlənirsə — dalğa uzanır.",
     "source": "Elliott; subyektivdir, akademik sübutu yoxdur. Hakim ölçür."},
    {"id": "TH-WYC-1", "area": "Nəzəriyyə", "name": "Wyckoff: spring / upthrust", "detector": True,
     "how": "Son 40 şam yatay aralıqdır (EMA-lar qarışıq, aralıq ≤ 8 ATR). Qiymət aralığın dibinin altına düşüb geri "
            "qayıdır (spring — böyük alıcı satışları udur) və ya zirvənin üstünə çıxıb geri qayıdır (upthrust).",
     "signal": "Spring → yuxarı; upthrust → aşağı.",
     "void": "Qiymət aralıqdan kənarda möhkəmlənirsə — əsl qırılmadır.",
     "source": "Wyckoff (1930-cu illər); praktikada məşhur, akademik sübutu yoxdur."},
    # ---------------- Price action / smart money ----------------
    {"id": "PA-LIQ-1", "area": "Price action", "name": "Likvidlik toplanması (stop ovu)", "detector": True,
     "how": "Qiymət son təsdiqlənmiş zirvənin üstünə (dibin altına) çıxır, oradakı stopları işə salır, sonra geri "
            "qayıdıb uzun kölgə ilə səviyyənin bu tərəfində bağlanır (kölgə şamın yarısından çox).",
     "signal": "Zirvə üstündə toplanma → aşağı; dib altında → yuxarı.",
     "void": "Növbəti şam yenidən səviyyənin o tərəfində bağlanırsa.",
     "source": "ICT / «smart money» praktikası; Osler (2003): stop sifarişləri dəyirmi səviyyələrdə toplanır. Sübutu zəif."},
    {"id": "PA-BOS-1", "area": "Price action", "name": "Quruluşun qırılması (BOS / CHoCH)", "detector": True,
     "how": "Şam son təsdiqlənmiş zirvənin üstündə (dibin altında) bağlanır. Əgər əvvəlki quruluş əks idisə (alçaq "
            "zirvələr), bu «xarakter dəyişməsi» (CHoCH) sayılır.",
     "signal": "Zirvə qırıldı → yuxarı; dib qırıldı → aşağı.",
     "void": "Qırılmadan dərhal sonra geri qayıdış (yalançı qırılma, bax PA-LIQ-1).",
     "source": "Dow quruluşunun müasir adı; «smart money» praktikası; sübutu zəif."},
    {"id": "PA-OB-1", "area": "Price action", "name": "Order block (ilk qayıdış)", "detector": True,
     "how": "3 şamda ən azı 2 ATR güclü hərəkət (son 10 şamın ucunu qırır). Ondan əvvəlki son əks şam «order block» "
            "zonasıdır. Qiymət sonra ilk dəfə bu zonaya qayıdıb hərəkət istiqamətində şam bağlayanda.",
     "signal": "Alıcı bloku → yuxarı; satıcı bloku → aşağı.",
     "void": "Zona bir dəfə istifadə olunub və ya qiymət zonanın o tərəfində bağlanıb.",
     "source": "ICT / «smart money» praktikası; akademik sınağı yoxdur. Hakim ölçür."},
    # ---------------- Həcm ----------------
    {"id": "VOL-SPIKE-1", "area": "Həcm", "name": "Böyük həcmlə qırılma (böyük oyunçu)", "detector": True,
     "how": "Şamın tik həcmi son 100 şamın ortasından ≥ 2 qat, şam ATR-dən böyük və 20 şamın zirvəsini (dibini) qırır.",
     "signal": "Zirvə qırıldı → yuxarı; dib qırıldı → aşağı.",
     "void": "Həcm məlumatı yoxdursa qayda susur (tik həcmi 2026-11-25-dən sayılır).",
     "source": "Granville, Wyckoff; tik həcmi brokerin qiymət dəyişmə sayıdır — real birja həcminin təxmini əvəzi."},
    {"id": "VOL-OBV-1", "area": "Həcm", "name": "OBV divergensiyası", "detector": True,
     "how": "OBV (On-Balance Volume): qalxan şamın həcmi əlavə, düşənin çıxılır. Qiymət 20 şamın yeni zirvəsində, OBV isə "
            "yox — alış zəifdir; qiymət yeni dibdə, OBV yox — satış zəifdir.",
     "signal": "Zirvədə təsdiq yoxdur → aşağı; dibdə təsdiq yoxdur → yuxarı.",
     "void": "Həcm məlumatı yoxdursa.",
     "source": "Granville (1963); sübutu zəif."},
    {"id": "VOL-VWAP-1", "area": "Həcm", "name": "VWAP keçidi", "detector": True,
     "how": "VWAP — həcmlə çəkili orta qiymət (1 saatlıqda son 24 şam, 4 saatlıqda 6, gündəlikdə 5). Qiymət VWAP-ı "
            "ortadan böyük həcmlə keçir.",
     "signal": "Yuxarı keçid → yuxarı; aşağı keçid → aşağı.",
     "void": "Həcm məlumatı yoxdursa; fyuçers sınağımızda (2 il, Databento) VWAP qaydası işləmədi.",
     "source": "Kurumsal icra standartı; proqnoz gücü zəif."},
    {"id": "VOL-POC-1", "area": "Həcm", "name": "Həcm profili: POC səviyyəsi", "detector": True,
     "how": "Son 100 şamın həcmi qiymət pillələrinə (0,25 ATR) bölünür; ən çox həcm olan qiymət — POC. Qiymət yuxarıdan "
            "POC-a enib alıcı şamı ilə bağlanır (dəstək) və ya aşağıdan qalxıb satıcı şamı ilə bağlanır (müqavimət).",
     "signal": "POC dəstək → yuxarı; POC müqavimət → aşağı.",
     "void": "Həcm məlumatı yoxdursa.",
     "source": "Steidlmayer (Market Profile, 1980-ci illər); sübutu zəif."},
    # ---------------- dəyişkənlik və risk ----------------
    {"id": "TA-ATR-1", "area": "Texniki", "name": "Dəyişkənliyə görə aralıq və stop", "detector": False,
     "how": "ATR 14 gözlənilən hərəkətin ölçüsüdür: stop girişdən 1–2 ATR, hədəf ən azı 2 qat stop. Hakim hər qaydanı "
            "belə də ölçür: stop 1 ATR, hədəf 2 ATR, ən çox 20 şam — nəticə R ilə (1 R = stop qədər risk).",
     "signal": "İstiqamət vermir; aralıq və risk ölçüsü.",
     "void": "Böyük xəbər ərəfəsində ATR keçmişi əks etdirir, gələcəyi yox.",
     "source": "Wilder; risk idarəsində standart."},
    # ---------------- Fundamental: qızıl ----------------
    {"id": "FA-RY-1", "area": "Fundamental", "name": "Real faiz (10 illik TIPS), 5 gün", "detector": True,
     "how": "Real faiz qızıl saxlamağın alternativ xərcidir (GRAM: fürsət xərci). 10 illik TIPS gəlirinin (FRED DFII10) "
            "son 5 müşahidədəki dəyişməsi ±0,10 pp-dən böyükdürsə (yalnız dərc olunmuş dəyərlər, 2 gün gecikmə ilə).",
     "signal": "Real faiz düşür → qızıl yuxarı; qalxır → aşağı.",
     "void": "2022-dən sonra mərkəzi bank alışları bu əlaqəni zəiflədib: tək başına həlledici deyil.",
     "source": "Erb-Harvey (2013); WGC modeli; əlaqə uzun müddət güclü, son illərdə zəifləyib."},
    {"id": "FA-USD-1", "area": "Fundamental", "name": "Dollar (geniş indeks), 5 gün", "detector": True,
     "how": "Qızıl dollarla qiymətlənir. Geniş dollar indeksinin (FRED DTWEXBGS, həftəlik dərc: 10 gün gecikmə ilə) son 5 "
            "müşahidədəki dəyişməsi ±1 %-dən böyükdürsə. Gün içi dollar hərəkəti «Bazarlar arası» blokundadır.",
     "signal": "Dollar zəifləyir → qızıl yuxarı; güclənir → aşağı.",
     "void": "Böhran anında ikisi birlikdə qalxa bilər (hər ikisi sığınacaqdır).",
     "source": "Geniş sübut; qısa müddətdə güclü əks əlaqə."},
    {"id": "FA-FED-1", "area": "Fundamental", "name": "Fed gözləntisi (2 illik faiz), 5 gün", "detector": True,
     "how": "2 illik ABŞ istiqraz gəliri (FRED DGS2) bazarın Fed faiz yolunu gözləməsini əks etdirir. Son 5 müşahidədə "
            "±0,15 pp-dən çox dəyişmə: bazar daha çox (düşür) və ya daha az (qalxır) endirim gözləyir. Mühüm olan "
            "GÖZLƏNTİNİN dəyişməsidir. Kalshi ehtimalları da toplanır (AI analitik mətn kimi oxuyur).",
     "signal": "Endirim ehtimalı artır → yuxarı; azalır → aşağı.",
     "void": "Bazar dəyişikliyi artıq qiymətə salıbsa (xəbər gözlənilən kimi çıxdı).",
     "source": "Pul siyasəti şokları ədəbiyyatı; FOMC sürprizləri qızılda güclü reaksiya yaradır."},
    {"id": "FA-SURP-1", "area": "Fundamental", "name": "ABŞ sürpriz indeksi, 14 gün", "detector": True,
     "how": "Fakt ilə gözlənti fərqi (CPI, qeyri-kənd iş yerləri, işsizlik, ÜDM, PCE): son 14 gündəki rəqəmlərin qızıl "
            "üçün işarəsi və təsir çəkisi ilə cəmi (ən azı 3 rəqəm, |cəm| ≥ 2). Citi sürpriz indeksi fikri. Rəqəmin ilk "
            "dəqiqələri «Hadisə sürprizi» üsulundadır.",
     "signal": "Zəif iqtisadiyyat / aşağı inflyasiya sürprizi → qızıl yuxarı; güclü → aşağı.",
     "void": "Gözlənti məlumatı yoxdursa — uydurulmur, qayda susur.",
     "source": "Smales-Yang (2015); Elder-Miao-Ramchander (2012)."},
    {"id": "FA-COT-1", "area": "Fundamental", "name": "Fondların mövqeyi (COT) ifrat halda", "detector": True,
     "how": "CFTC: idarə olunan fondların xalis mövqeyi son 3 ilin aralığında ən yüksək və ya ən aşağı 20 %-də "
            "(kodda «COT» üsulu eyni həddi işlədir).",
     "signal": "İfrat uzun mövqe → aşağı risk (əks fikir); ifrat qısa → yuxarı.",
     "void": "Həftəlik məlumat: qısa üfüq üçün deyil.",
     "source": "Sanders-Irwin-Merrin; sübutu qarışıqdır."},
    {"id": "FA-RY-2", "area": "Fundamental", "name": "Real faiz trendi, 20 gün", "detector": True,
     "how": "DFII10-un son 20 müşahidədəki dəyişməsi ±0,25 pp-dən böyükdürsə: fürsət xərcinin trendi.",
     "signal": "Real faiz trendlə düşür → yuxarı; qalxır → aşağı.",
     "void": "Mərkəzi bank alışları güclü olanda (2022-dən sonra) əlaqə zəifləyib.",
     "source": "Erb-Harvey (2013); WGC GRAM."},
    {"id": "FA-BE-1", "area": "Fundamental", "name": "İnflyasiya gözləntisi, 5 gün", "detector": True,
     "how": "10 illik inflyasiya gözləntisi (FRED T10YIE) son 5 müşahidədə ±0,08 pp-dən çox dəyişəndə.",
     "signal": "Gözlənti artır → yuxarı (inflyasiyadan qorunma); azalır → aşağı.",
     "void": "Böhrandan sonra bu əlaqənin işarəsi dəyişib (Invesco): Hakim ölçür.",
     "source": "Invesco «What is driving gold»; WGC."},
    {"id": "FA-COT-2", "area": "Fundamental", "name": "Fondların axını (COT), 3 həftə", "detector": True,
     "how": "İdarə olunan fondların xalis mövqeyi 3 həftədir ardıcıl eyni tərəfə dəyişir və cəmi adi həftəlik dəyişmənin "
            "3 qatından böyükdür.",
     "signal": "Fondlar ardıcıl alır → yuxarı; satır → aşağı.",
     "void": "Mövqe artıq ifrat haldadırsa (FA-COT-1 əks deyir).",
     "source": "Sanders-Irwin-Merrin (2009); sübutu qarışıqdır."},
    {"id": "FA-FED-2", "area": "Fundamental", "name": "Fed ehtimalları (Kalshi), 3 gün", "detector": True,
     "how": "Kalshi proqnoz bazarında növbəti Fed iclası üçün beş nəticənin ehtimalı (artım >25, 25, dəyişməz, endirim "
            "25, >25 bp): gözlənilən faiz dəyişməsi bp ilə. Son 3 gündə ±5 bp-dən çox dəyişəndə.",
     "signal": "Bazar daha çox endirim gözləməyə başlayır → yuxarı; daha az → aşağı.",
     "void": "İclas günü və ondan sonra nəticə məlumdur; bazar nazikdirsə ehtimallar səs-küylüdür.",
     "source": "Pul siyasəti şokları ədəbiyyatı; proqnoz bazarlarının dəqiqliyi (Wolfers-Zitzewitz 2004)."},
    {"id": "FA-SGE-1", "area": "Fundamental", "name": "Şanxay premiumu (Çinin fiziki tələbi)", "detector": True,
     "how": "Şanxay Qızıl Birjasında Au99.99-un gündəlik qiyməti (yuan/qram) yuan/dollar məzənnəsi (FRED DEXCHUS) ilə "
            "dollar/unsiyaya çevrilir və eyni günün beynəlxalq qiyməti ilə müqayisə edilir. 5 günlük orta premium ilin "
            "ən yuxarı (≥ 80-ci faiz) və ya ən aşağı (≤ 20-ci faiz) hissəsində olanda.",
     "signal": "Yüksək premium (Çin tələbi güclü) → yuxarı; endirim (tələb zəif) → aşağı.",
     "void": "Çinin idxal kvotaları və valyuta nəzarəti premiumu süni saxlaya bilər.",
     "source": "WGC Çin bazarı hesabatları (Şanxay premiumu Çin tələbinin əsas göstəricisi kimi); SGE rəsmi məlumatı."},
    {"id": "FA-GROW-1", "area": "Fundamental", "name": "İqtisadi böyümə (Çikaqo Fed fəallıq indeksi)", "detector": True,
     "how": "CFNAI-MA3 (85 ABŞ göstəricisinin 3 aylıq orta indeksi, FRED). +0,2-dən yuxarı — böyümə ortadan güclü; "
            "−0,7-dən aşağı — tənəzzül həddi. Hər ay ay bitəndən 60 gün sonra «məlum» sayılır.",
     "signal": "GRAM-a görə böyümə tələbi (zərgərlik, sənaye) artırır → yuxarı; tənəzzül → aşağı. Diqqət: tənəzzül "
               "eyni zamanda faiz endirimi və qorxu ilə qızılı qaldıra bilər — Hakim hansı təsirin güclü olduğunu ölçür.",
     "void": "Gecikmə ilə gəlir: həftəlik üfüqdən qısa üçün deyil.",
     "source": "WGC GRAM («iqtisadi genişlənmə» amili); Chicago Fed CFNAI."},
    {"id": "FA-ETF-1", "area": "Fundamental", "name": "ETF axını (GLD), 5 gün", "detector": True,
     "how": "Dünyanın ən böyük qızıl ETF-i GLD-nin fondda saxladığı qızıl (ton, emitentin gündəlik rəsmi arxivi, 2004-dən). "
            "5 günlük dəyişmə ilin 5 günlük dəyişmələri arasında ən yuxarı 20 %-də (giriş) və ya ən aşağı 20 %-də (çıxış). "
            "Rəqəm ertəsi gün «məlum» sayılır.",
     "signal": "Güclü giriş → yuxarı; güclü çıxış → aşağı.",
     "void": "Axın çox vaxt qiymətin ardınca gəlir (Invesco, Banque de France): Hakim irəlidəmi, gecikirmi — ölçür.",
     "source": "SPDR Gold Trust rəsmi arxivi; WGC ETF hesabatları."},
    {"id": "FA-ETF-2", "area": "Fundamental", "name": "ETF axını (GLD), 20 gün", "detector": True,
     "how": "Eyni ölçü 20 günlük pəncərədə: investorların davamlı alışı və ya satışı.",
     "signal": "Davamlı giriş → yuxarı; davamlı çıxış → aşağı.",
     "void": "Eyni.",
     "source": "SPDR Gold Trust; WGC."},
    {"id": "FA-IND-1", "area": "Fundamental", "name": "Hindistan premiumu (həftəlik)", "detector": True,
     "how": "Hindistan dilerlərinin rəsmi daxili qiymətə görə premiumu (+) və ya endirimi (−), $/unsiya, həftəlik xəbər "
            "hesabatlarından (Reuters «Asia Gold»). Bazar müxbiri iki beyinlə tapır: rəqəm və dövr üst-üstə düşəndə qəbul "
            "olunur. Son iki hesabat arasında ±5 $-dan çox dəyişəndə; son hesabat 14 gündən köhnə olmamalıdır.",
     "signal": "Premium artır (endirim azalır) → yuxarı; azalır → aşağı.",
     "void": "Qiymətin özü kəskin dəyişəndə dilerlər endirimi genişləndirir: bu, tələbdən çox qiymət reaksiyasıdır.",
     "source": "WGC Hindistan hesabatları; Reuters həftəlik Asiya fiziki bazar icmalı."},
    {"id": "FA-IND-2", "area": "Fundamental", "name": "Hindistanın qızıl ETF axını (aylıq)", "detector": True,
     "how": "AMFI-nin dərc etdiyi aylıq xalis axın (krore rupi), xəbərlərdən; |axın| ≥ 500 krore və rəqəm 45 gündən köhnə "
            "deyilsə.",
     "signal": "Giriş → yuxarı; çıxış → aşağı.",
     "void": "Aylıq və gecikmə ilə: yalnız uzun üfüq üçün.",
     "source": "AMFI aylıq hesabatları; WGC."},
    {"id": "FA-CB-1", "area": "Fundamental", "name": "Mərkəzi bankların alışı (IMF), 3 ay", "detector": True,
     "how": "IMF-in rəsmi statistikası (International Liquidity, qızıl ehtiyatının həcmi): 25 mərkəzi bankın (Çin, "
            "Hindistan, Türkiyə, Polşa, Rusiya, Qazaxıstan, Özbəkistan, Çexiya, Qətər, Sinqapur və b.) aylıq xalis alışı "
            "tonla. Son 3 ayın cəmi son 3 ilin 3 aylıq cəmləri arasında ən yuxarı (≥ 80-ci faiz) və ya ən aşağı "
            "(≤ 20-ci faiz) olanda. Hər ay ay bitəndən 45 gün sonra «məlum» sayılır.",
     "signal": "Güclü alış → yuxarı; zəif alış / satış → aşağı.",
     "void": "Uzun müddətli dayaqdır: gün içi və saatlıq proqnoz üçün istifadə olunmur. Bəzi ölkələr gec və ya natamam "
             "bildirir.",
     "source": "WGC GRAM (mərkəzi bank tələbi amili); Banque de France 2024: 2021-dən qiymətin əsas sürücüsü; IMF IL."},
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
    # ---------------- Xəbər bloku (app/newsblock.py) ----------------
    {"id": "NW-SENT-1", "area": "Xəbər", "name": "Xəbər əhvalı (asimmetrik, sönən)", "detector": True,
     "how": "Oxuyucunun son 6 saatda qiymətləndirdiyi başlıqlar (hər hadisənin yalnız birinci başlığı): istiqamət × güc "
            "(0–3); mənfi xəbər 1,5 qat ağır; hər başlığın təsiri 2 saatda yarıya sönür. Cəm ±3-dən böyükdürsə.",
     "signal": "Müsbət əhval → yuxarı; mənfi → aşağı.",
     "void": "Xəbər artıq qiymətdədirsə (bazar əvvəlcədən gözləyirdi).",
     "source": "Smales (2014, 2015): mənfi xəbər qızılda daha güclü təsir edir; təsirin saatlarla sönməsi."},
    {"id": "NW-FED-1", "area": "Xəbər", "name": "Fed xəbərləri, 4 saat", "detector": True,
     "how": "Mövzusu Fed/faiz olan başlıqların son 4 saatdakı sönən cəmi ±2-dən böyükdürsə.",
     "signal": "Yumşaq (endirim) xəbər → yuxarı; sərt → aşağı (Oxuyucunun istiqaməti).",
     "void": "FOMC qərarı dəqiqəsi «Hadisə sürprizi» üsulundadır.",
     "source": "Awartani-Hussain-Virk (2024): qızıl FOMC sürprizlərinə güclü reaksiya verir."},
    {"id": "NW-DATA-1", "area": "Xəbər", "name": "ABŞ rəqəmi xəbərləri, 4 saat", "detector": True,
     "how": "Mövzusu inflyasiya, iş yerləri, ÜDM olan başlıqların son 4 saatdakı sönən cəmi ±2-dən böyükdürsə.",
     "signal": "Oxuyucunun istiqaməti.",
     "void": "Rəqəmin özü (fakt − gözlənti) «Hadisə sürprizi» və FA-SURP-1-dədir.",
     "source": "Elder-Miao-Ramchander (2012); Smales-Yang (2015)."},
    {"id": "NW-GEO-1", "area": "Xəbər", "name": "Geosiyasi xəbərlər, 4 saat", "detector": True,
     "how": "Mövzusu geosiyasət, müharibə, sanksiya olan başlıqların son 4 saatdakı sönən cəmi ±2-dən böyükdürsə.",
     "signal": "Gərginlik artır → yuxarı (sığınacaq); azalır → aşağı.",
     "void": "Likvidlik böhranının ilk saatlarında qızıl da satıla bilər.",
     "source": "Baur-Smales (2020); Apergis-Hayat-Saeed (2021): geosiyasi xəbərin təsiri daha güclüdür."},
    {"id": "NW-FLOW-1", "area": "Xəbər", "name": "Tələb-təklif xəbərləri, 4 saat", "detector": True,
     "how": "Mövzusu tələb və ya təklif (mərkəzi bank, ETF, Çin/Hindistan, mədən, tətil) olan başlıqların cəmi ±2-dən böyükdürsə.",
     "signal": "Oxuyucunun istiqaməti.",
     "void": "Rəqəmlər fundamental blokda (FA-CB-1, FA-ETF, FA-SGE-1) daha dəqiqdir.",
     "source": "WGC tələb hesabatları."},
    {"id": "NW-SURGE-1", "area": "Xəbər", "name": "Xəbər axınının sıçrayışı", "detector": True,
     "how": "Son 2 saatda qiymətləndirilmiş başlıq sayı ən azı 4 və son həftənin adi 2 saatlıq sayından 3 qat çox.",
     "signal": "Sıçrayışdakı xəbərlərin əhvalı istiqamətində.",
     "void": "Bir hadisənin çoxlu surəti sayılmır (yalnız birinci başlıq qiymətləndirilir).",
     "source": "Diqqət (attention) ədəbiyyatı: xəbər axını dəyişkənliyi və davamı artırır."},
    {"id": "NW-SHOCK-1", "area": "Xəbər", "name": "Böyük xəbər (güc 3)", "detector": True,
     "how": "Son 1 saatda Oxuyucunun «böyük bazar hadisəsi» (güc 3) dediyi başlıq.",
     "signal": "Onun istiqaməti.",
     "void": "Başlıq qeyri-müəyyəndirsə Oxuyucu neytral deyir.",
     "source": "Hadisə araşdırmaları."},
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
AREAS = ("Texniki", "Fibonacci", "Nəzəriyyə", "Price action", "Həcm", "Fundamental", "Xəbər", "Bazarlar arası")
TA_AREAS = ("Texniki", "Fibonacci", "Nəzəriyyə", "Price action", "Həcm", "Bazarlar arası")
CHART_AREAS = ("Texniki", "Fibonacci", "Nəzəriyyə", "Price action", "Həcm", "Bazarlar arası", "Öyrənilmiş")


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
