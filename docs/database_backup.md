# Veritabanı Yedekleme ve Geri Yükleme Prosedürü

Bu dokümanda, canlı ortamdan (VPS) güncel veritabanını alıp yerel ortama aktarma prosedürü açıklanmaktadır.

## Uzak Sunucuda (Canlı Ortamda) Yedek Alma

PostgreSQL için:

```bash
pg_dump -U hukudok_user hukudok > backup.sql
```

MySQL için (eğer kullanılıyorsa):

```bash
mysqldump -u hukudok_user -p hukudok > backup.sql
```

## Yerel Makinenize İndirin (scp/sftp ile)

```bash
scp hukudok_user@35.234.119.194:/path/to/backup.sql ~/Downloads/
```

*Not: Bu örnekte canlı VPS IP'si `35.234.119.194` olarak kullanılmıştır. `/path/to/backup.sql` yerine yedek dosyasının uzak sunucudaki tam yolunu yazın.*

## Yerel Veritabanınıza Import Edin

PostgreSQL için:

```bash
psql -U postgres hukudok < backup.sql
```

MySQL için:

```bash
mysql -u root -p hukudok < backup.sql
```

*Not: Yerel veritabanınızın adı `hukudok` olarak varsayılmıştır. Farklıysa değiştirin.*

## Güvenlik Notları

- Şifreleri komut satırında yazmayın, interaktif olarak girin.
- Yedek dosyalarını güvenli bir şekilde saklayın.
- Canlı ortamda yedek alırken sistem yükünü göz önünde bulundurun.</content>
<parameter name="filePath">c:\Users\ilkeb\OneDrive\Masaüstü\hukudok-automator-main\docs\database_backup.md