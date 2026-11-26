# Təkliflər (sahib qərar verir)

## 2026-11-24
1. **FMP Starter (~29 $/ay, 1 ay sınaq).** Səbəb: «Hadisə sürprizi» 0 istiqamət verir, çünki faktiki ABŞ rəqəmi yoxdur (HTTP 402). Gözlənti: 2 illik təqvimlə üsul keçmişdə bir neçə günə yoxlanır. Uğursuz olsa: abunə ləğv, rəqəm ovçusu qalır.
2. **Əlaqəli bazarların axını (Blok 2).** Səbəb: 8 bazardan 3-ü gəlmir və hər yoxlamada başqa 3-ü (DXY, Brent, VIX / istiqraz). Dollar və neft üsulları yarımçıq işləyir. Xərc: yoxdur. Gözlənti: 8/8 canlı.
3. **İkinci beyin proqnozu (Blok 1-in davamı).** Strateqin ehtimal proqnozu işləyir; eyni faktlarla OpenAI-dan ayrıca ehtimal almaq və razılaşanda ayrıca hesab. Xərc: ayda ~1-3 $ (nano model). Uğursuz olsa: söndürülür.

## 2026-11-24 (NY 07:50) — sahib qərar verir, heç biri həyata keçirilməyib

1. **Platin və palladium impulsu (H11) çox güman ki, işləməyəcək.**
   - Sübut: Databento 2 illik fyuçers sınağında PL və PA impulsları 15 dəqiqədə 45–47 % davam edib, böyük həcmlə də. Bu, 50 %-dən aşağıdır, yəni hətta bir az geri dönür.
   - Təklif: H11-i öz qaydası ilə canlı yoxlamağa davam etmək, amma ondan nəticə gözləməmək. Növbəti qeyd dövründə onun yerinə «xəbər dəqiqəsi» (H13) üzərində dayanmaq.
2. **Xəbər dəqiqəsi üçün canlı üsul (göstərici kimi).**
   - Sübut: qızılda 08:30, 10:00 və 14:00 NY dəqiqələrindəki impuls 60 dəqiqədə 63,5 % davam edib. 104 hal, iki ildə də müsbət, Capital-da xərcdən sonra da müsbət.
   - Təklif: H13 canlıda ilk 30 halı yığanda bunu Hakimin ölçdüyü ayrıca üsula çevirmək. Bu, qərar deyil, göstərici olacaq.
3. **Verilənlər bazasının böyüməsi.**
   - Sübut: baza 24 saatda 567 MB-dan 792 MB-a çatıb. Səbəblər: fyuçers şamları, yeni üsulların tarixçəsi, qayda siqnalları.
   - Təklif: fyuçers sınaqları hesablandıqdan sonra dəqiqəlik fyuçers şamlarını sıxışdırılmış fayla köçürmək, yaxud qayda siqnallarının köhnə tarixçəsini 90 günlə məhdudlaşdırmaq. Hər ikisi geri qaytarıla bilir.

## 2026-11-25 (NY 04:47) — sahib qərar verir, həyata keçirilməyib
1. **Bazanın ölçüsü üçün saxlama müddəti.**
   - Sübut: baza 24 noyabrda 567 → 792 → 999 MB, bu gün 1014 MB. Böyümə yavaşlayıb (8 saatda +15 MB), amma 500 MB həddindən iki dəfə böyükdür; gündəlik ehtiyat nüsxə də bu qədər böyüyür.
   - Təklif: `rule_signals`-in köhnə tarixçəsini qayda versiyası dəyişəndə silmək (yenisi onsuz da yenidən hesablanır) və kağız ticarətin rədd edilmiş təkliflərini 90 gün saxlamaq. Geri qaytarıla bilir: tarixçə hər an yenidən hesablanır.

### 2026-11-26
1. **/api/diag cavabı 63–64 saniyə çəkir** (bu gün iki ölçü: 63,7 s və 60 s-də kəsildi). Növbətçi yoxlama və gələcək kənar
   izləmə (plan A1) üçün bu çox uzundur. Təklif: ağır hissələri (cədvəl ölçüləri, proqnoz sayları) 10 dəqiqəlik keşdən vermək.
   Sübut: `curl -w %{time_total}` ölçüləri. Həyata keçirilməyib — sahib qərar verir (plan B2 ilə birlikdə etmək olar).
