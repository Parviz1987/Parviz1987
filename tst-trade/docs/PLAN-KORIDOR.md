# Koridor planı — fiziki qızıl və fyuçers (sahib 28.11: «hər ikisi olmalıdır, birinci koridoru düzəlt»)

Bu fayl 28.11-dən sonrakı əsas iş planıdır. Jurnal və yoxlama siyahısı: `docs/PLAN-27.11.md` (dördüncü hissə).

## Niyə bu yol
- 8 ideya (Fed, ABŞ rəqəmləri, COT, dollar, neft, müharibə, böyük oyunçu, CME açıq mövqe) və koridor kənarında alqı-satqı
  (geri dönüş və qırılma) Hakimin sınağında sübut vermədi. Dostun sistemi və elmi ədəbiyyat eyni şeyi deyir: qısa müddətli
  yön təxmin edilmir; **dəyişkənlik və koridor təxmin edilir** (ən güclü sübut).
- Bizim koridor artıq kalibrlidir (1 gün 80 % → 80,5 % / 1 964 gün; 1 həftə 79,6 %). Qazanc iki yerdədir: koridoru **daha
  dar və dəqiq** etmək, ondan **düzgün istifadə** etmək (fiziki alış-satışda qiymət qənaəti; fyuçersdə risk və ölçü).

## Mərhələlər (ardıcıl; hər mərhələ ölçülür, sübut verməyən sistemə qoşulmur)

### 1. Koridor mühərriki v2 — `app/corridor.py`
- Dəyişkənlik: günün ən yüksək / ən aşağı qiymətindən (Parkinson) gündəlik, həftəlik, aylıq qatlar (HAR); qızılda GVZ
  (opsionların gözlədiyi dəyişkənlik); horizontda qabaqcadan bilinən ABŞ rəqəmi / Fed günlərinin sayı.
- Koridor: dəyişkənliyə bölünmüş keçmiş nəticələrin aşağı və yuxarı kənarı AYRICA (empirik), sonra adaptiv düzəliş
  (qaçırma çoxdursa genişlənir, azdırsa daralır).
- Qəbul (qabaqcadan yazılıb, koddadır): tutma 80 % ± 2,5, 50 % ± 3; bal (en + qaçırma cəriməsi) indiki koridordan aşağı,
  Diebold–Mariano p < 0,01; qaçırmalar topa deyil. Qızıl 1 gün və 1 həftə qərar verir.
- Keçsə: sistemin koridoru v2 olur (panel, proqnoz kartları, Hakim). Keçməsə: indiki qalır, nəticə yazılır.

### 2. Fiziki qızıl — alış və satış planı
- Sual: «N gün ərzində qızıl almalıyam» — koridorun aşağı hissəsinə limit sifariş, dolmasa müddətin sonunda bazar qiyməti.
  Satış — güzgü kimi. Hakim ölçür: adi alışa (müddətin əvvəli / sonu) qarşı orta qənaət, dolma faizi, ən pis hal.
- Səhifə: bu gün və bu həftə üçün alış limiti, satış limiti, dolma ehtimalı, dolmasa nə etmək — sadə dillə.

### 3. Fyuçers — ticarət planı
- Yön yalnız Hakimin sübutu ilə (indi heç biri yoxdur → «GÖZLƏ»). Koridor: zərəri dayandırma, hədəf, və kapital / risk
  faizinə görə müqavilə sayı (GC 100 unsiya, MGC 10 unsiya). Hakim ölçür: zərəri dayandırmaya çatma tezliyi koridorun
  dediyi ehtimala uyğundurmu (risk vədi düzdürmü).

### 4. Karkas
- Sübutsuz yön blokları proqnozun səsindən çıxır (səhifələrdə məlumat kimi qalır); beyin xərcləri azalır.
- Hakim: bütün sınaqların reyestri (çoxlu sınaq düzəlişi), üst-üstə düşən proqnozların düzgün sayılması.
- Tarixçə: gündəlik ~20 il, saatlıq daha uzun (Hakimin keçmiş rəqəmlərini dəyişir — sahib «nə lazımdırsa» dedi, edilərkən
  əvvəl/sonra rəqəmləri yazılır).

## Qayda
Hər qayda nəticədən əvvəl yazılır (fayl + git); pul xərclənmir; qiymət heç vaxt LLM-dən; hər mərhələ bitəndə sahibə sadə
dillə: nə edildi, necə yoxlandı, nə qaldı.
