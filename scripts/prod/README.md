# Prod operasyon script'leri

## backup_db.sh — gecelik Postgres yedeği

**Gerekçe:** tüm kimlikler/ilişkiler/metadata tek Postgres'te; SharePoint yalnız
belge binary'si tutar. DB kaybı = "hangi belge hangi davanın" bilgisinin kaybı.

**Tasarım:** gecelik `pg_dump -Fc` (custom format, `pg_restore` ile seçmeli geri
dönüş) → boyut kontrolü (1 MB altı hata; dolu dump 2026-08-05'te 1.7 MB —
sıkıştırmalı, DB disk boyutu 65 MB ama çoğu index) → SharePoint
`02_YEDEK_ARSIV` klasörüne `db_backup_YYYY-MM-DD.dump` olarak kopya (backend
konteynerinin mevcut app-only Graph kimliğiyle, `backend/scripts/upload_db_backup.py`)
→ yerelde son 14 gün saklanır. Başarı/hata logu `~/backups/backup.log`.

Dump kişisel veri içerir — SharePoint klasörü zaten app-only erişimlidir; dump'ı
başka yere kopyalamayın.

### Kurulum (sunucuda bir kez)

```bash
# 1. Script'i sunucuya kopyala (repo'dan; sunucunun GitHub erişimi yok)
scp scripts/prod/backup_db.sh hukukoid:~/backup_db.sh
ssh hukukoid chmod +x ~/backup_db.sh

# 2. upload_db_backup.py imajda yoksa (deploy henüz almadıysa) konteynere kopyala:
scp backend/scripts/upload_db_backup.py hukukoid:~/upload_db_backup.py
ssh hukukoid docker cp ~/upload_db_backup.py hukdok_backend:/app/scripts/upload_db_backup.py
# (kalıcı çözüm: sıradaki normal deploy — dosya repo'da backend/scripts/ altında)

# 3. Elle bir kez koştur + doğrula
ssh hukukoid ~/backup_db.sh
ssh hukukoid 'ls -lh ~/backups/ && tail ~/backups/backup.log'
ssh hukukoid 'docker exec -i hukudok-postgres pg_restore --list < ~/backups/hukudok_$(date +%F).dump | head'

# 4. Zamanlayıcı: sunucuda cron YOK — systemd timer kullanılır (net-watchdog /
#    mem-watch ile aynı desen). 00:30 UTC = 03:30 TR.
#    /etc/systemd/system/db-backup.service:
#      [Unit]
#      Description=HukuDok gecelik Postgres yedegi (pg_dump + SharePoint kopyasi)
#      After=docker.service
#      [Service]
#      Type=oneshot
#      User=luciferandlucius
#      ExecStart=/home/luciferandlucius/backup_db.sh
#      TimeoutStartSec=900
#    /etc/systemd/system/db-backup.timer:
#      [Unit]
#      Description=HukuDok gecelik Postgres yedegini 00:30 UTC (03:30 TR) kostur
#      [Timer]
#      OnCalendar=*-*-* 00:30:00
#      Persistent=true
#      AccuracySec=5min
#      [Install]
#      WantedBy=timers.target
ssh hukukoid 'sudo systemctl daemon-reload && sudo systemctl enable --now db-backup.timer'

# 5. Ertesi gün çıktıyı kontrol et
ssh hukukoid 'tail ~/backups/backup.log; systemctl status db-backup.service --no-pager -n 10'
```

### Geri dönüş

```bash
# Seçmeli veya tam restore (boş DB'ye):
pg_restore --list hukudok_YYYY-MM-DD.dump            # içeriği gör
createdb -U hukudok_user hukudok_restore
pg_restore -U hukudok_user -d hukudok_restore hukudok_YYYY-MM-DD.dump
psql -U hukudok_user -d hukudok_restore -c "SELECT count(*) FROM cases;"
```

SharePoint kopyaları `02_YEDEK_ARSIV` kökünde `db_backup_*.dump` desenindedir
(teknik loglarla aynı klasör; arama endpoint'i geride kalabilir, children ile
listeleyin).
