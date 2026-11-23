# Ehtiyat nüsxələr (geri qayıtmaq üçün)

Hər böyük dəyişiklikdən əvvəl işlək versiyanın nömrəsi bura yazılır. Git tarixçəsi heç nəyi silmir: aşağıdakı
nömrələr həmişə GitHub-da, `claude/amazing-keller-c4hwfl` budağında qalır.

| Tarix (NY) | İşlək versiya | Nədən əvvəl |
|---|---|---|
| 23.11.2026 | `e69623c` | Kölgə ticarəti simulyatoru, uğur xəritəsi, 12 aylıq trend üsulu |

## Geri qayıtmaq
Server bu budaqdan özü yenilənir, ona görə geri qayıtmaq = budağı köhnə versiyaya qaytaran yeni bir commit:

```bash
git revert --no-edit e69623c..HEAD
git push origin claude/amazing-keller-c4hwfl
```

5 dəqiqə ərzində server köhnə versiyaya keçir. Məlumat bazası (açarlar, şamlar, proqnozlar) toxunulmaz qalır.
Bundan əlavə, server yeni versiyanı yalnız `/healthz` cavab verəndə saxlayır; cavab verməsə özü köhnəsinə qayıdır.
