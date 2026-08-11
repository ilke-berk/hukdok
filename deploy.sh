#!/usr/bin/env bash
# HukuDok prod deploy (Faz 1-C).
#
# Kullanım (sunucuda, mesai dışı):   cd ~/hukdok && ./deploy.sh
#
# Akış: önkoşullar → git pull --ff-only → pre-deploy pg_dump → build (eski
# stack ÇALIŞIRKEN) → imajlara git-SHA etiketi → up -d (frontend, backend
# healthy olana dek bekler) → /healthz kapısı (120 sn) → etiket bakımı (son 3)
# + dangling temizliği.
#
# Eski deploy.sh'tan bilinçli farklar (guvenilirlik-sertlestirme-plani Faz 1.4):
#  - 'down' YOK: build çalışan stack'i etkilemez, kesinti yalnız up'taki
#    konteyner değişimi (dakikalar → saniyeler)
#  - git pull --ff-only BAŞARISIZSA DEPLOY DURUR (eskiden hata yutulup
#    ESKİ kodla sessizce devam ediliyordu)
#  - sağlık kapısı gerçek: /healthz 120 sn poll, başarısızsa exit 1 +
#    rollback komutu basılır (eskiden sleep 5 + docker ps)
#  - imajlar SHA ile etiketlenir; 'docker image prune -f' artık rollback
#    hedeflerini silemez (etiketli imaj dangling olmaz)
#
# Ortam düğmeleri (varsayılanlar prod içindir):
#   MIN_DUMP_BYTES=1048576   pre-deploy dump alt sınırı (lokal prova: 1)
#   PRUNE=1                  dangling imaj temizliği (lokal prova: 0)
set -euo pipefail
cd "$(dirname "$0")"

C_G='\033[0;32m'; C_Y='\033[1;33m'; C_R='\033[0;31m'; C_N='\033[0m'
say()  { echo -e "${C_Y}$*${C_N}"; }
ok()   { echo -e "${C_G}$*${C_N}"; }
fail() { echo -e "${C_R}$*${C_N}" >&2; exit 1; }

HEALTH_URL="http://localhost:8001/healthz"
FRONT_URL="http://localhost:8080/"
BACKUP_DIR="${HOME}/backups"
KEEP_TAGS=3
MIN_DUMP_BYTES="${MIN_DUMP_BYTES:-1048576}"
PRUNE="${PRUNE:-1}"

# ── 1. Önkoşullar ────────────────────────────────────────────────────────────
say "🔎 Önkoşullar denetleniyor..."
docker compose version >/dev/null 2>&1 || fail "docker compose (v2) bulunamadı"
[ -f .env ] || fail ".env yok — deploy iptal"

REQUIRED_KEYS=(POSTGRES_PASSWORD DATABASE_URL GEMINI_API_KEY AZURE_CLIENT_ID
               ALLOWED_TENANTS SHAREPOINT_TENANT_ID SHAREPOINT_CLIENT_ID
               SHAREPOINT_CLIENT_SECRET)
for k in "${REQUIRED_KEYS[@]}"; do
    # `|| true` şart: anahtar HİÇ yoksa grep 1 döner, `set -e`+pipefail altında
    # script aşağıdaki açıklayıcı fail mesajını basmadan sessizce çıkardı.
    v=$(grep -E "^${k}=" .env | head -1 | cut -d= -f2-) || true
    [ -n "$v" ] || fail ".env zorunlu anahtarı boş/yok: ${k}"
done

if ! docker network inspect hukuk_shared >/dev/null 2>&1; then
    say "⚠️  hukuk_shared network yok — oluşturuluyor (hukukbot bu ağdan bağlanır)"
    docker network create hukuk_shared
fi

# İmaj adları proje adına göre değişir (sunucuda hukdok-*, lokalde farklı)
# `|| true`: eşleşme yoksa grep 1 döner; boşluğu aşağıdaki fail mesajı bildirsin.
BACKEND_IMG=$(docker compose config --images | grep -- '-backend$' | head -1) || true
FRONTEND_IMG=$(docker compose config --images | grep -- '-frontend$' | head -1) || true
{ [ -n "$BACKEND_IMG" ] && [ -n "$FRONTEND_IMG" ]; } || fail "imaj adları compose config'ten çözülemedi"

# ── 2. Kod güncelle ──────────────────────────────────────────────────────────
OLD_SHA=$(git rev-parse --short HEAD)
say "🔄 git pull --ff-only (mevcut: ${OLD_SHA})..."
git pull --ff-only || fail "git pull başarısız — çakışma çözülmeden deploy YOK"
NEW_SHA=$(git rev-parse --short HEAD)
ok "Kod: ${OLD_SHA} → ${NEW_SHA}"

# ── 3. Pre-deploy DB yedeği ──────────────────────────────────────────────────
# Migration'lar açılışta otomatik koşar; kötü bir migration'ın tek geri yolu
# bu dump'tır (rollback.sh imaj döndürür, DB'yi DÖNDÜRMEZ).
DUMP="(alınmadı)"
if docker ps --format '{{.Names}}' | grep -q '^hukudok-postgres$'; then
    mkdir -p "$BACKUP_DIR"
    DUMP="${BACKUP_DIR}/predeploy_${NEW_SHA}_$(date +%Y%m%d-%H%M%S).dump"
    say "🗄  pg_dump alınıyor: ${DUMP}"
    docker exec hukudok-postgres pg_dump -U hukudok_user -Fc hukudok > "$DUMP"
    SIZE=$(stat -c%s "$DUMP")
    [ "$SIZE" -ge "$MIN_DUMP_BYTES" ] || fail "pre-deploy dump şüpheli küçük (${SIZE} B < ${MIN_DUMP_BYTES}) — deploy iptal"
    ok "Yedek OK ($((SIZE / 1024)) KB)"
else
    say "⚠️  hukudok-postgres çalışmıyor — pre-deploy dump ATLANDI (ilk kurulum senaryosu)"
fi

# ── 4. Rollback hedefini koru + build ────────────────────────────────────────
# Build :latest'i hemen yeni imaja taşır; eski imaj SHA etiketi taşımıyorsa
# ÖNCE etiketle ki rollback hedefi dangling'e düşmesin.
for img in "$BACKEND_IMG" "$FRONTEND_IMG"; do
    if docker image inspect "${img}:latest" >/dev/null 2>&1 \
       && ! docker image inspect "${img}:${OLD_SHA}" >/dev/null 2>&1; then
        docker tag "${img}:latest" "${img}:${OLD_SHA}"
        say "  rollback hedefi etiketlendi: ${img}:${OLD_SHA}"
    fi
done

# Sürümü imajlara göm: login rozeti + /healthz "version" alanı bu SHA'yı
# gösterir (compose build args → Dockerfile ARG APP_VERSION).
export APP_VERSION="$NEW_SHA"

say "🏗  docker compose build (eski stack çalışmaya devam ediyor)..."
docker compose build

docker tag "${BACKEND_IMG}:latest"  "${BACKEND_IMG}:${NEW_SHA}"
docker tag "${FRONTEND_IMG}:latest" "${FRONTEND_IMG}:${NEW_SHA}"
ok "İmajlar etiketlendi: ${NEW_SHA}"

# ── 5. Up (yalnız değişen konteynerler yeniden yaratılır) ────────────────────
say "🚀 docker compose up -d..."
if ! docker compose up -d --remove-orphans; then
    docker compose ps
    fail "up başarısız (backend healthy olamadı?) — geri dönüş: ./rollback.sh ${OLD_SHA} · DB dump: ${DUMP}"
fi

# ── 6. Sağlık kapısı ─────────────────────────────────────────────────────────
say "🧪 /healthz kapısı (120 sn'ye kadar)..."
deadline=$((SECONDS + 120))
until curl -fsS --max-time 5 "$HEALTH_URL" >/dev/null 2>&1; do
    if [ "$SECONDS" -ge "$deadline" ]; then
        docker compose ps
        docker logs hukdok_backend --tail 30 2>&1 || true
        fail "❌ Backend 120 sn'de sağlıklı olmadı — geri dönüş: ./rollback.sh ${OLD_SHA} · DB dump: ${DUMP}"
    fi
    sleep 3
done
# Çalışan sürümü doğrula: /healthz'in version alanı yeni SHA'yı göstermeli.
# Uyarı olarak bırakıldı (fail değil): lokal mount/elle build senaryolarında
# meşru sapma olabilir; prod'da bu uyarı bayat imaj işaretidir.
RUNNING_VER=$(curl -fsS --max-time 5 "$HEALTH_URL" 2>/dev/null | grep -o '"version":"[^"]*"' | cut -d'"' -f4 || true)
if [ "$RUNNING_VER" = "$NEW_SHA" ]; then
    ok "Backend sağlıklı (${SECONDS} sn, sürüm: ${RUNNING_VER})"
else
    say "⚠️  Çalışan sürüm '${RUNNING_VER:-?}' ≠ beklenen '${NEW_SHA}' — bayat imaj olabilir"
fi
# Frontend'e de kısa poll: konteyner "Started" ile nginx'in porta geçmesi
# arasında 1-2 sn yarış var — Deploy #2'de tek atımlık curl buna yakalandı
# (deploy sağlıklıydı, kapı erken pes etti).
say "🧪 Frontend kontrolü (30 sn'ye kadar)..."
fdeadline=$((SECONDS + 30))
until curl -fsS --max-time 5 "$FRONT_URL" >/dev/null 2>&1; do
    if [ "$SECONDS" -ge "$fdeadline" ]; then
        docker logs "$(docker compose ps -q frontend)" --tail 15 2>&1 || true
        fail "Frontend :8080 30 sn'de yanıt vermedi — geri dönüş: ./rollback.sh ${OLD_SHA}"
    fi
    sleep 2
done
ok "Frontend yanıt veriyor"

# ── 7. Gecelik yedek timer'ı yerinde mi? (uyarı — deploy'u durdurmaz) ────────
if command -v systemctl >/dev/null 2>&1; then
    if systemctl is-active --quiet db-backup.timer 2>/dev/null; then
        ok "db-backup.timer aktif"
    else
        say "⚠️  db-backup.timer AKTİF DEĞİL — sudo bash infra/install.sh koşun"
    fi
fi

# ── 8. Etiket bakımı: son ${KEEP_TAGS} SHA kalır, dangling temizlenir ────────
prune_tags() {
    local img="$1"
    docker images "$img" --format '{{.Tag}}#{{.CreatedAt}}' \
        | grep -v '^latest#' | sort -t'#' -k2 -r \
        | awk -F'#' -v keep="$KEEP_TAGS" 'NR > keep {print $1}' \
        | while read -r t; do
              docker rmi "${img}:${t}" >/dev/null 2>&1 \
                  && say "  eski etiket silindi: ${img}:${t}" \
                  || say "  silinemedi (kullanımda?): ${img}:${t}"
          done
}
say "🧹 Etiket bakımı..."
prune_tags "$BACKEND_IMG"
prune_tags "$FRONTEND_IMG"
if [ "$PRUNE" = "1" ]; then
    docker image prune -f >/dev/null
    say "  dangling imajlar temizlendi"
fi

echo
docker compose ps
ok "✅ Deploy tamam: ${NEW_SHA} · rollback: ./rollback.sh ${OLD_SHA} · DB dump: ${DUMP}"
