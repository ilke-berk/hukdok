#!/usr/bin/env bash
# HukuDok host-seviyesi konfig kurulumu (Faz 1-B) — infra/ ağacını sunucuya işler.
#
# Kullanım (sunucuda):  sudo bash infra/install.sh
#
# Idempotent: içerik aynıysa dosyaya dokunmaz. nginx yalnızca config değiştiyse
# ve `nginx -t` geçerse reload edilir. Docker daemon'ı YENİDEN BAŞLATMAZ
# (daemon.json değiştiyse etkisi için mesai dışı elle `systemctl restart docker`).
set -euo pipefail

cd "$(dirname "$0")"

if [ "$(id -u)" -ne 0 ]; then
    echo "HATA: root gerekli — sudo bash infra/install.sh" >&2
    exit 1
fi

# db-backup.service ExecStart bu yolu bekler (User= de bu kullanıcı)
BACKUP_USER="luciferandlucius"
BACKUP_HOME="/home/${BACKUP_USER}"
changed_nginx=0

inst() {  # inst <kaynak> <hedef> <mod> [sahip:grup]
    local src="$1" dst="$2" mode="$3" owner="${4:-root:root}"
    if [ -f "$dst" ] && cmp -s "$src" "$dst"; then
        echo "aynı     $dst"
    else
        install -o "${owner%%:*}" -g "${owner##*:}" -m "$mode" "$src" "$dst"
        echo "YAZILDI  $dst"
        case "$dst" in /etc/nginx/*) changed_nginx=1 ;; esac
    fi
}

echo "== systemd unit'leri =="
for f in systemd/*; do
    inst "$f" "/etc/systemd/system/$(basename "$f")" 0644
done

echo "== watchdog / bellek kayıtçısı =="
inst scripts/net-watchdog.sh /usr/local/sbin/net-watchdog.sh 0755
inst scripts/mem-watch.sh    /usr/local/sbin/mem-watch.sh    0755

echo "== gecelik yedek script'i =="
if ! id "$BACKUP_USER" >/dev/null 2>&1; then
    echo "HATA: '$BACKUP_USER' kullanıcısı yok — yeni VM'de önce kullanıcıyı kurun" >&2
    exit 1
fi
inst scripts/backup_db.sh "${BACKUP_HOME}/backup_db.sh" 0755 "${BACKUP_USER}:${BACKUP_USER}"

echo "== docker daemon.json =="
inst docker/daemon.json /etc/docker/daemon.json 0644

echo "== nginx site'ları =="
inst nginx/sites-available/default /etc/nginx/sites-available/default 0644
inst nginx/sites-available/hukbot  /etc/nginx/sites-available/hukbot  0644
ln -sf /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/hukbot  /etc/nginx/sites-enabled/hukbot
if [ "$changed_nginx" -eq 1 ]; then
    # -t başarısızsa set -e burada durdurur; çalışan nginx eski config'le kalır
    nginx -t
    systemctl reload nginx
    echo "nginx yeniden yüklendi"
else
    echo "nginx değişmedi — reload yok"
fi

echo "== timer'lar =="
systemctl daemon-reload
systemctl enable --now db-backup.timer mem-watch.timer net-watchdog.timer

echo "== durum =="
systemctl is-active db-backup.timer mem-watch.timer net-watchdog.timer
systemctl list-timers --no-pager | grep -E 'db-backup|mem-watch|net-watchdog' || true
echo "TAMAM"
