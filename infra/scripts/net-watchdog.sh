#!/bin/bash
# Ag nobetcisi - metadata erisimini olcer, sorun YEREL agda ise ens4'u toparlar.
# Gerekce ve kurulum: docs/sunucu-sertlestirme-plani-2026-07-30.md (Madde 1)
#
# Tasarim notlari:
#  - Bu kutuda 'ping' kurulu DEGIL. Erisilebilirlik uc yapisal sinyalle olculuyor:
#    global IPv4 adresi, default route, networkd'nin 'routable' gorusu.
#    2026-07-29 arizasinda ('Could not set DHCPv4 address' + 'ens4: Failed')
#    ucu de basarisiz olurdu.
#  - Metadata erisilemez ama yerel ag saglikli ise MUDAHALE EDILMEZ. Aksi halde
#    Google tarafindaki bir metadata kesintisinde calisan siteyi dakikada bir
#    networkd restart'iyla sarsardik.
#  - Uzun arizada mudahale backoff'a giriyor: ilk turlarda her tur, sonra 10 turda bir.
set -u

IFACE="ens4"
URL="http://169.254.169.254/computeMetadata/v1/instance/id"
STATE="/run/net-watchdog.fails"
LOG="/var/log/net-watchdog.log"

log() { printf '%s %s\n' "$(date -Is)" "$*" >> "$LOG"; }

probe() {
    curl -sf -m 5 -H "Metadata-Flavor: Google" "$URL" >/dev/null 2>&1
}

# Uc sinyalin hepsi saglamsa yerel ag ayakta demektir.
local_net_healthy() {
    ip -4 addr show "$IFACE" scope global 2>/dev/null | grep -q 'inet ' || return 1
    [ -n "$(ip route show default dev "$IFACE" 2>/dev/null)" ] || return 1
    [ "$(networkctl --no-legend list "$IFACE" 2>/dev/null | awk '{print $4}')" = "routable" ] || return 1
    return 0
}

# Ariza anindaki durumu log'a bas - dun tam bu goruntu eksikti.
snapshot() {
    log "  durum addr      : $(ip -br -4 addr show "$IFACE" 2>/dev/null | tr -s ' ' | tr -d '\n')"
    log "  durum default   : $(ip route show default dev "$IFACE" 2>/dev/null | tr -s ' ' | tr -d '\n')"
    log "  durum networkctl: $(networkctl --no-legend list "$IFACE" 2>/dev/null | tr -s ' ' | tr -d '\n')"
}

if probe; then
    if [ -f "$STATE" ]; then
        log "TOPARLANDI: metadata erisimi geri geldi (basarisiz tur sayisi: $(cat "$STATE" 2>/dev/null))"
        rm -f "$STATE"
    fi
    exit 0
fi

fails=$(cat "$STATE" 2>/dev/null || echo 0)
case "$fails" in ''|*[!0-9]*) fails=0 ;; esac
fails=$((fails + 1))
echo "$fails" > "$STATE"

# Tek seferlik dalgalanmada mudahale yok: iki tur (~2 dk) sart.
if [ "$fails" -lt 2 ]; then
    log "probe basarisiz (${fails}/2) - bekliyorum"
    exit 0
fi

# Yerel ag saglamsa sorun bizde degil. Sarsmadan sadece raporla.
if local_net_healthy; then
    log "metadata ${fails} turdur erisilemez, yerel ag SAGLIKLI - mudahale yok (metadata tarafi)"
    if [ "$fails" -eq 5 ]; then
        log "KRITIK: metadata 5 turdur erisilemez, yerel ag saglikli"
        snapshot
    fi
    exit 0
fi

# Backoff - uzun arizada dakikada bir networkd restart'i olmasin.
if [ "$fails" -gt 6 ] && [ $((fails % 10)) -ne 0 ]; then
    log "yerel ag BOZUK, ${fails}. tur - backoff, bu turda mudahale yok"
    exit 0
fi

log "yerel ag BOZUK (${fails}. tur) - ${IFACE} yeniden yapilandiriliyor"
snapshot
networkctl reconfigure "$IFACE" || log "  networkctl reconfigure hata verdi"
sleep 5

if probe; then
    log "TOPARLANDI: reconfigure yeterli oldu"
    rm -f "$STATE"
    exit 0
fi

log "hala erisilemez - systemd-networkd yeniden baslatiliyor"
systemctl restart systemd-networkd
sleep 10

if probe; then
    log "TOPARLANDI: networkd restart sonrasi"
    rm -f "$STATE"
else
    log "KRITIK: mudahalelere ragmen ag yok - reset gerekebilir"
    snapshot
fi
