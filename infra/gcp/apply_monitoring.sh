#!/usr/bin/env bash
# GCP log tabanlı alarm kurulumu (Faz 2-C) — LOKAL makineden koşulur
# (gcloud auth'lu hesapla; sunucudan DEĞİL — VM service account'unda
# monitoring admin yetkisi yok ve olmamalı).
#
# Idempotent: API enable no-op'tur; metrik varsa filtre/description
# güncellenir (yakınsama); politika displayName ile aranır, varsa atlanır
# (politika İÇERİĞİ değiştiyse: GCP Console'dan veya
# `gcloud alpha monitoring policies update <NAME> --policy-from-file=...`
# ile elle güncelleyin — displayName'den policy adı çözmek için list).
#
# Git Bash notu: / ile başlayan argümanlar MSYS yol çevirisine takılır
# (gerekirse // ikile); bu script'te / ile başlayan argüman yok.
set -euo pipefail
cd "$(dirname "$0")"

PROJECT="gen-lang-client-0074242743"

echo "== API'ler =="
gcloud services enable logging.googleapis.com monitoring.googleapis.com --project "$PROJECT"

echo "== Log tabanlı metrik: hukdok_backend_error_count =="
FILTER='resource.type="gce_instance" AND logName="projects/gen-lang-client-0074242743/logs/docker_json" AND severity>=ERROR'
DESC="Backend konteyner loglarinda (docker_json) ERROR+ satir sayisi — ERROR-orani alarminin kaynagi (Faz 2-C)"
if gcloud logging metrics describe hukdok_backend_error_count --project "$PROJECT" >/dev/null 2>&1; then
    gcloud logging metrics update hukdok_backend_error_count --project "$PROJECT" \
        --log-filter="$FILTER" --description="$DESC" --quiet
    echo "aynı/güncellendi  hukdok_backend_error_count"
else
    gcloud logging metrics create hukdok_backend_error_count --project "$PROJECT" \
        --log-filter="$FILTER" --description="$DESC"
    echo "YAZILDI  hukdok_backend_error_count"
fi

echo "== Alarm politikaları =="
existing=$(gcloud alpha monitoring policies list --project "$PROJECT" --format="value(displayName)")
for f in policy-*.json; do
    # Üst-seviye displayName dosyada koşul displayName'lerinden ÖNCE gelir
    name=$(sed -n 's/.*"displayName": *"\([^"]*\)".*/\1/p' "$f" | head -1)
    if printf '%s\n' "$existing" | grep -Fxq "$name"; then
        echo "aynı     $name"
    else
        gcloud alpha monitoring policies create --project "$PROJECT" --policy-from-file="$f" >/dev/null
        echo "YAZILDI  $name"
    fi
done

echo "TAMAM — bildirimler: lexis@lexis.com.tr + luciferandlucius@gmail.com (kanal adları policy JSON'larında)"
