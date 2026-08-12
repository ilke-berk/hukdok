#!/usr/bin/env bash
# HukuDok prod deploy (Faz 1-C).
#
# Kullanım (sunucuda, mesai dışı):   cd ~/hukdok && ./deploy.sh
#   Yalnız test kapısını koş (pull/dump/build/up YOK):  ./deploy.sh --gate-only
#
# Akış: önkoşullar → git pull --ff-only → pre-deploy pg_dump → build (eski
# stack ÇALIŞIRKEN) → imajlara git-SHA etiketi → TEST KAPISI (yeni imajdan
# tek seferlik konteyner) → up -d (frontend, backend healthy olana dek bekler)
# → /healthz kapısı (120 sn) → etiket bakımı (son 3) + dangling temizliği.
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
#  - TEST KAPISI (G038): build'den SONRA, up'tan ÖNCE koşar. Testler kalırsa
#    deploy DURUR ve çalışan stack'e hiç dokunulmaz (kırık kod prod'a çıkamaz).
#    Kapı, YENİ imajdan tek seferlik bir konteyner kaldırır; çalışan stack'e
#    ve prod DB'ye dokunmaz. 'docker compose run' BİLEREK kullanılmaz: compose
#    servisi .env'i (gerçek DATABASE_URL) beraberinde getirir ve
#    tests/test_migration_path.py ulaştığı Postgres'te scratch DB yaratıp
#    düşürür — yani kapı prod postgres'e DDL koşturabilirdi.
#    Test kodu imajda YOKTUR (backend/.dockerignore:35 tests/ dışlar), bu yüzden
#    çalışma ağacındaki backend/ salt-okunur mount edilir: kütüphane ortamı yeni
#    imajdan, test kodu git pull'un getirdiği ağaçtan — ikisi de AYNI commit.
#  - KAPININ KENDİ POSTGRES'İ (G050): temiz ortamın bedeli, DB gerektiren
#    testlerin SKIP olmasıydı — kapı 29 testi koşmadan yeşil diyordu (SKIP
#    yeşildir; ölçüm 2026-08-12: kapıda 1158 passed/32 skipped, çalışan
#    konteynerde 1187 passed/3 skipped). Kapı kendi Postgres'ini kaldırır: kendi
#    ağı, yayınlanmamış port, rastgele ad, kapı biter bitmez konteyner + ağ
#    silinir. Prod DB'ye temas yok, 'docker compose run' hâlâ kullanılmıyor.
#
# Ortam düğmeleri (varsayılanlar prod içindir):
#   MIN_DUMP_BYTES=1048576   pre-deploy dump alt sınırı (lokal prova: 1)
#   PRUNE=1                  dangling imaj temizliği (lokal prova: 0)
#   SKIP_TESTS=0             1 → test kapısı atlanır (gürültülü uyarı basar)
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
# Git Bash (Windows) MSYS yol dönüşümü docker'ın '-w /app' argümanını
# 'C:/Program Files/Git/app' yapar → kapı imaj bile çalıştıramaz (çıkış 125).
# Lokal kuru koşu (./deploy.sh --gate-only) bu yüzden dönüşümü kapatır;
# Linux'ta (prod) bu değişken hiçbir şey yapmaz — davranış değişmez.
export MSYS_NO_PATHCONV=1
# Konteyner İÇİ özel çıkış kodu: dev bağımlılıkları KURULAMADI (pip ağ erişimi
# yok). Test başarısızlığından ayırt edilmeli — pytest 0..5 döner, 91 çakışmaz.
GATE_SKIP_EXIT=91
# Aynı gerekçeyle: şema migrasyonu boş DB'de kaldı (G050). Bu bir test
# başarısızlığı DEĞİLDİR ama deploy'u durdurur — prod'da aynı migrasyon
# entrypoint'te koşacak ve konteyner hiç kalkmayacaktı.
GATE_MIGRATE_EXIT=92

# ── Kapının tek kullanımlık Postgres'i (G050) ────────────────────────────────
# Kapı temiz ortamda koştuğu için DATABASE_URL yoktu ve DB gerektiren testler
# (migrasyon yolu, index envanteri, esas tarihçesi) SKIP oluyordu — SKIP yeşil
# sayıldığı için kapı onları KOŞMADAN geçiyordu. Çözüm prod DB'ye bağlanmak
# DEĞİL (o yol tam olarak G038'in reddettiği yoldur): kapı kendi postgres'ini
# kaldırır. Kısıtlar: port YAYINLANMAZ, prod ağlarına (hukuk_shared, compose
# ağı) BAĞLANMAZ, adı rastgeledir, kapı biter bitmez konteyner+ağ silinir.
GATE_PG_IMAGE="postgres:15-alpine"
GATE_DB_USER="gate"
GATE_DB_PASS="gate"
GATE_DB_NAME="gatedb"
GATE_PG_NAME=""
GATE_NET_NAME=""
GATE_RUN_NAME=""

# Her yolda koşar: başarı, test başarısızlığı (fail→exit), pip 91, migrasyon 92,
# Ctrl-C/kill. İçeride hiçbir komut script'i düşürmemeli → hepsi `|| true`,
# sonu `return 0`. Sızıntı SESSİZ kalmaz: silinemeyen kalem uyarıyla bildirilir.
#
# SIRA ÖNEMLİ: önce test konteyneri, sonra postgres, en sonda ağ. Script
# dışarıdan öldürüldüğünde `docker run --rm`in İSTEMCİSİ ölür ama konteyner
# ayakta kalabilir; ağ o yüzden "active endpoints" ile reddedilirdi (ölçüldü:
# G050, TERM yolu). Test konteyneri bu yüzden adlandırılır ve önce silinir;
# ağ silme ayrıca 5×1 sn yeniden denenir (endpoint teardown asenkrondur).
gate_db_down() {
    if [ -n "${GATE_RUN_NAME}" ]; then
        docker rm -f "$GATE_RUN_NAME" >/dev/null 2>&1 || true
        GATE_RUN_NAME=""
    fi
    if [ -n "${GATE_PG_NAME}" ]; then
        # -v: postgres imajının anonim data volume'ü de gitsin
        docker rm -fv "$GATE_PG_NAME" >/dev/null 2>&1 || true
        if docker container inspect "$GATE_PG_NAME" >/dev/null 2>&1; then
            say "⚠️  kapı postgres'i silinemedi: ${GATE_PG_NAME} (elle: docker rm -fv ${GATE_PG_NAME})"
        fi
        GATE_PG_NAME=""
    fi
    if [ -n "${GATE_NET_NAME}" ]; then
        for _ in 1 2 3 4 5; do
            docker network rm "$GATE_NET_NAME" >/dev/null 2>&1 && break
            sleep 1
        done
        if docker network inspect "$GATE_NET_NAME" >/dev/null 2>&1; then
            say "⚠️  kapı ağı silinemedi: ${GATE_NET_NAME} (elle: docker network rm ${GATE_NET_NAME})"
        fi
        GATE_NET_NAME=""
    fi
    return 0
}

# Kendi kendini toparlama: önceki koşulardan artmış kapı ağlarını siler.
# GÜVENLİ, çünkü `docker network rm` KULLANIMDAKİ ağı reddeder — aynı anda
# koşan başka bir deploy'un ağına dokunulmaz. Konteynerler bilinçli olarak
# süpürülmez: ayakta bir kapı postgres'i canlı bir deploy'a ait olabilir.
gate_sweep_orphan_networks() {
    local n
    for n in $(docker network ls --filter "name=^hukdok_gate_net_" --format '{{.Name}}' 2>/dev/null); do
        if docker network rm "$n" >/dev/null 2>&1; then
            say "  artık kalmış kapı ağı silindi: ${n}"
        fi
    done
    return 0
}
trap gate_db_down EXIT
trap 'gate_db_down; exit 130' INT TERM

# Boş bir Postgres kaldırır ve TCP'den yanıt verene dek bekler.
gate_db_up() {
    local suffix="" deadline
    gate_sweep_orphan_networks
    # Çakışma dayanıklılığı: ad PID+RANDOM'dan türer, üstelik kullanımda
    # olmadığı doğrulanır. Aynı anda iki deploy ya da kalıntı bir konteyner
    # kapıyı kilitlemesin (kalıntıyı SİLMEYİZ — başka bir koşunun canlı
    # konteyneri olabilir; biz başka ad seçeriz).
    for _ in 1 2 3 4 5; do
        suffix="$$_${RANDOM}"
        if ! docker container inspect "hukdok_gate_pg_${suffix}" >/dev/null 2>&1 \
           && ! docker container inspect "hukdok_gate_run_${suffix}" >/dev/null 2>&1 \
           && ! docker network inspect "hukdok_gate_net_${suffix}" >/dev/null 2>&1; then
            break
        fi
        suffix=""
    done
    [ -n "$suffix" ] || { say "  boşta kapı konteyneri adı bulunamadı"; return 1; }

    GATE_NET_NAME="hukdok_gate_net_${suffix}"
    docker network create "$GATE_NET_NAME" >/dev/null 2>&1 \
        || { GATE_NET_NAME=""; say "  kapı ağı yaratılamadı"; return 1; }

    # Test konteynerinin adı da şimdiden belli olsun: script öldürülürse
    # gate_db_down onu adıyla bulup silebilsin (bkz. gate_db_down sıra notu).
    GATE_RUN_NAME="hukdok_gate_run_${suffix}"
    GATE_PG_NAME="hukdok_gate_pg_${suffix}"
    # Ne -p ne --network host: konteyner YALNIZ kendi ağından erişilebilir.
    docker run -d --name "$GATE_PG_NAME" --network "$GATE_NET_NAME" \
        -e POSTGRES_USER="$GATE_DB_USER" -e POSTGRES_PASSWORD="$GATE_DB_PASS" \
        -e POSTGRES_DB="$GATE_DB_NAME" \
        "$GATE_PG_IMAGE" >/dev/null 2>&1 \
        || { say "  kapı postgres'i başlatılamadı (${GATE_PG_IMAGE} var mı?)"; return 1; }

    # pg_isready'i -h 127.0.0.1 ile sor: initdb sırasında sunucu yalnız unix
    # soketten yanıt verir, TCP'yi sormak "erken hazır" yanılgısını keser.
    deadline=$((SECONDS + 60))
    until docker exec "$GATE_PG_NAME" \
              pg_isready -h 127.0.0.1 -U "$GATE_DB_USER" -d "$GATE_DB_NAME" >/dev/null 2>&1; do
        if [ "$SECONDS" -ge "$deadline" ]; then
            docker logs "$GATE_PG_NAME" --tail 20 2>&1 || true
            say "  kapı postgres'i 60 sn'de hazır olmadı"
            return 1
        fi
        sleep 1
    done
    return 0
}

GATE_ONLY=0
for arg in "$@"; do
    case "$arg" in
        --gate-only) GATE_ONLY=1 ;;
        *) fail "bilinmeyen argüman: ${arg} (kullanım: ./deploy.sh [--gate-only])" ;;
    esac
done

# ── 0. Test kapısı ───────────────────────────────────────────────────────────
# Verilen imajdan tek seferlik bir konteyner kaldırıp testleri koşar. Çalışan
# stack'e DOKUNMAZ. Dönüş 0 = deploy devam edebilir; başarısızlıkta fail ile
# script'i durdurur (up -d hiç çalışmaz). Gerekçeler dosya başındaki yorumda.
test_gate() {
    local img="$1" t0=$SECONDS rc=0 dt
    if [ "${SKIP_TESTS:-0}" = "1" ]; then
        say "════════════════════════════════════════════════════════════"
        say "  ⚠️  SKIP_TESTS=1 — TEST KAPISI ATLANDI (bilinçli tercih)"
        say "  Prod'a TEST EDİLMEMİŞ kod çıkıyor."
        say "════════════════════════════════════════════════════════════"
        return 0
    fi
    say "🧪 Test kapısı: ${img} (tek seferlik konteyner; çalışan stack'e dokunulmaz)..."
    # Kapının kendi DB'si kalkmazsa DURUR: sessizce DB'siz koşmak, tam da bu
    # görevin kapattığı deliği (29 test SKIP → kapı yeşil) geri açardı.
    # Bilinçli atlamak isteyen SKIP_TESTS=1 kullanır.
    gate_db_up || { gate_db_down; fail "❌ Test kapısı KURULAMADI: geçici Postgres kalkmadı — deploy DURDU. Bilinçli atlamak için: SKIP_TESTS=1 ./deploy.sh"; }
    # DATABASE_URL kapının KENDİ postgres'ini gösterir; testler scratch
    # veritabanlarını orada yaratıp düşürür (conftest setdefault ile bu URL'i
    # korur). Prod DB'sinin adresi bu konteynere hiç girmez.
    # migrate.py: şemayı boş DB'de kurar — hem prod entrypoint'inin koştuğu
    # yolun provası, hem de "kolon yok → SKIP" diyen testlerin (g046) önkoşulu.
    # -rs: kalan SKIP'ler sebepleriyle basılır — kapının neyi koşmadığı görünür kalsın.
    docker run --rm --name "$GATE_RUN_NAME" --entrypoint bash --user root \
        --network "$GATE_NET_NAME" \
        -v "${PWD}/backend:/app:ro" -w /app \
        -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp \
        -e DATABASE_URL="postgresql://${GATE_DB_USER}:${GATE_DB_PASS}@${GATE_PG_NAME}:5432/${GATE_DB_NAME}" \
        "$img" -c "pip install --no-cache-dir -q -r requirements-dev.txt || exit ${GATE_SKIP_EXIT}
                   python migrate.py || exit ${GATE_MIGRATE_EXIT}
                   python -m pytest -p no:cacheprovider -rs" || rc=$?
    gate_db_down          # trap yedektir; normal yolda konteyner hemen silinir
    dt=$((SECONDS - t0))
    if [ "$rc" -eq 0 ]; then
        ok "✅ Test kapısı GEÇTİ (${dt} sn)"
        return 0
    fi
    if [ "$rc" -eq "$GATE_MIGRATE_EXIT" ]; then
        fail "❌ Test kapısı KALDI: şema migrasyonu BOŞ veritabanında koşmadı (${dt} sn) — bu kod prod'da entrypoint'te de düşerdi, konteyner kalkmazdı. Deploy DURDU."
    fi
    if [ "$rc" -eq "$GATE_SKIP_EXIT" ]; then
        # Sessiz atlama YASAK: erişim yoksa uyar ama deploy'u bloke etme.
        say "⚠️  Test kapısı ATLANDI: dev bağımlılıkları kurulamadı (pip ağ erişimi yok?)."
        say "    Kod TEST EDİLMEDEN deploy ediliyor — kapı bunu bilerek durdurmuyor (${dt} sn)."
        return 0
    fi
    fail "❌ Test kapısı KALDI (çıkış ${rc}, ${dt} sn) — deploy DURDU, çalışan stack'e dokunulmadı. Bilinçli atlamak için: SKIP_TESTS=1 ./deploy.sh"
}

# --gate-only: kapıyı deploy akışından bağımsız koş. git pull'dan ÖNCE döner —
# pull / dump / build / up -d hiç çalışmaz. Henüz build yok, o yüzden mevcut
# :latest imajı üzerinden koşar. Çıkış kodu doğrudan kapının kararıdır.
if [ "$GATE_ONLY" = "1" ]; then
    say "🚪 --gate-only: YALNIZ test kapısı koşulacak (pull/dump/build/up YOK)"
    # `|| true`: eşleşme yoksa grep 1 döner; boşluğu aşağıdaki fail bildirsin.
    GATE_IMG=$(docker compose config --images | grep -- '-backend$' | head -1) || true
    [ -n "$GATE_IMG" ] || fail "backend imaj adı compose config'ten çözülemedi"
    test_gate "${GATE_IMG}:latest"
    ok "🚪 --gate-only bitti"
    exit 0
fi

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

# ── 4b. Test kapısı (up'tan ÖNCE — kırık kod çalışan stack'i devralmasın) ────
test_gate "${BACKEND_IMG}:${NEW_SHA}"

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
