#!/usr/bin/env bash
# Prod Postgres gecelik yedeği — kurulum: infra/README.md (sunucu hedefi:
# /home/luciferandlucius/backup_db.sh, db-backup.service bu yolu bekler)
#
# Akış: pg_dump (custom format) → boyut kontrolü → SharePoint 02_YEDEK_ARSIV'e
# kopya (backend konteynerinin app-only Graph kimliğiyle) → 14 günden eski
# yerel dump'ların temizliği. Dump kişisel veri içerir; SharePoint klasörü
# app-only erişimlidir, dump'ı başka yere kopyalamayın.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
DATE="$(date +%F)"
DUMP="$BACKUP_DIR/hukudok_${DATE}.dump"
LOG="$BACKUP_DIR/backup.log"
# Dolu dump ~1.7 MB (2026-08-05, 14k dava; -Fc sıkıştırır; DB disk boyutu 65 MB
# ama çoğu index). Boş/yarım dump ~100 KB olur; 1 MB altı hata sayılır.
MIN_BYTES=$((1024 * 1024))

mkdir -p "$BACKUP_DIR"
log() { echo "$(date '+%F %T') $*" >>"$LOG"; }

# 1. Custom-format dump — pg_restore ile seçmeli geri dönüş mümkün
docker exec hukudok-postgres pg_dump -U hukudok_user -Fc hukudok >"$DUMP"

SIZE=$(stat -c%s "$DUMP")
if [ "$SIZE" -lt "$MIN_BYTES" ]; then
    log "HATA: dump şüpheli küçük ($SIZE bayt): $DUMP — SharePoint'e yüklenmedi"
    exit 1
fi
log "OK: dump alındı ($SIZE bayt): $DUMP"

# 2. VM dışına kopya: SharePoint 02_YEDEK_ARSIV (db_backup_YYYY-MM-DD.dump)
REMOTE_NAME="db_backup_${DATE}.dump"
docker cp "$DUMP" "hukdok_backend:/tmp/${REMOTE_NAME}"
docker exec hukdok_backend python scripts/upload_db_backup.py "/tmp/${REMOTE_NAME}"
# docker cp kökten (root) yazar; konteynerin normal kullanıcısı silemez → -u 0
docker exec -u 0 hukdok_backend rm -f "/tmp/${REMOTE_NAME}"
log "OK: SharePoint'e yüklendi: ${REMOTE_NAME}"

# 3. Yerel saklama: son 14 gün
find "$BACKUP_DIR" -name 'hukudok_*.dump' -mtime +14 -delete
