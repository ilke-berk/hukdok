#!/usr/bin/env bash
# HukuDok geri dönüş (Faz 1-C) — deploy.sh'ın SHA-etiketli imajlarına döner.
#
# Kullanım:  ./rollback.sh <git-kısa-sha>
#            ./rollback.sh            → mevcut geri dönüş etiketlerini listeler
#
# NOT: Yalnız İMAJLARI döndürür; git checkout'a ve DB'ye DOKUNMAZ.
#  - Kötü migration durumunda ~/backups/predeploy_*.dump'tan restore gerekir
#    (adımlar: infra/README.md "Yedekten geri dönüş").
#  - Rollback sonrası :latest etiketi git HEAD'den farklı imajı gösterir;
#    sonraki ./deploy.sh bunu yeniden hizalar.
set -euo pipefail
cd "$(dirname "$0")"

C_G='\033[0;32m'; C_Y='\033[1;33m'; C_R='\033[0;31m'; C_N='\033[0m'
say()  { echo -e "${C_Y}$*${C_N}"; }
ok()   { echo -e "${C_G}$*${C_N}"; }
fail() { echo -e "${C_R}$*${C_N}" >&2; exit 1; }

HEALTH_URL="http://localhost:8001/healthz"

BACKEND_IMG=$(docker compose config --images | grep -- '-backend$' | head -1)
FRONTEND_IMG=$(docker compose config --images | grep -- '-frontend$' | head -1)
{ [ -n "$BACKEND_IMG" ] && [ -n "$FRONTEND_IMG" ]; } || fail "imaj adları compose config'ten çözülemedi"

if [ $# -lt 1 ]; then
    echo "Kullanım: ./rollback.sh <git-kısa-sha>"
    echo "Mevcut geri dönüş etiketleri:"
    docker images "$BACKEND_IMG"  --format '  {{.Repository}}:{{.Tag}}  ({{.CreatedAt}})' | grep -v ':latest '
    exit 1
fi
SHA="$1"

docker image inspect "${BACKEND_IMG}:${SHA}"  >/dev/null 2>&1 || fail "${BACKEND_IMG}:${SHA} yok — ./rollback.sh ile listeye bakın"
docker image inspect "${FRONTEND_IMG}:${SHA}" >/dev/null 2>&1 || fail "${FRONTEND_IMG}:${SHA} yok — ./rollback.sh ile listeye bakın"

say "⏪ ${SHA} imajlarına dönülüyor (DB migration geri ALINMAZ)..."
docker tag "${BACKEND_IMG}:${SHA}"  "${BACKEND_IMG}:latest"
docker tag "${FRONTEND_IMG}:${SHA}" "${FRONTEND_IMG}:latest"

if ! docker compose up -d --no-build; then
    docker compose ps
    fail "up başarısız — docker logs hukdok_backend ile inceleyin"
fi

say "🧪 /healthz kapısı (120 sn'ye kadar)..."
deadline=$((SECONDS + 120))
until curl -fsS --max-time 5 "$HEALTH_URL" >/dev/null 2>&1; do
    if [ "$SECONDS" -ge "$deadline" ]; then
        docker compose ps
        docker logs hukdok_backend --tail 30 2>&1 || true
        fail "❌ Rollback sonrası da sağlıksız — migration şüphesi: predeploy dump'tan restore düşünün (infra/README.md)"
    fi
    sleep 3
done
ok "✅ Rollback tamam: ${SHA} çalışıyor · not: sonraki deploy :latest'i yeniden hizalar"
