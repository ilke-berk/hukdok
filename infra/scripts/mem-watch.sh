#!/bin/bash
# Bellek kayitcisi - her 5 dk sistem ve konteyner bellegini yazar.
#
# Amac: 2026-07-29'daki OOM'un (backend anon 3.57 GB, global_oom) tekrarinda
# kok nedeni tahminle degil veriyle yakalamak. O gece elimizde egilim verisi
# olmadigi icin sizintinin nerede oldugunu kod okuyarak bulamadik.
# Gerekce: docs/arsiv/sunucu-sertlestirme-plani-2026-07-30.md (Madde 6)
#
# 'anon'  = gercek bellek (sizinti buradan gorulur)
# 'file'  = sayfa onbellegi (baski altinda kendiliginden birakilir, zararsiz)
set -u

LOG="/var/log/mem-watch.log"
# Backend bu esigi gecerse KRITIK satiri yazilir. Makine 3.8 GB; 1500 MB
# tavanin yarisi demek, OOM'a saatler var ama egilim zaten belli olur.
WARN_MB=1500

ts=$(date -Is)

avail=$(awk '/^MemAvailable:/{printf "%d", $2/1024}' /proc/meminfo)
swtot=$(awk '/^SwapTotal:/{print $2+0}' /proc/meminfo)
swfree=$(awk '/^SwapFree:/{print $2+0}' /proc/meminfo)
swused=$(( (swtot - swfree) / 1024 ))

line="$ts sys_avail_mb=${avail} swap_mb=${swused}"
backend_anon=0

while read -r id name; do
    [ -n "${id:-}" ] || continue
    st="/sys/fs/cgroup/system.slice/docker-${id}.scope/memory.stat"
    [ -r "$st" ] || continue
    a=$(awk '/^anon /{printf "%d", $2/1048576}' "$st")
    f=$(awk '/^file /{printf "%d", $2/1048576}' "$st")
    line="${line} ${name}=${a}a/${f}f"
    [ "$name" = "hukdok_backend" ] && backend_anon="${a:-0}"
done < <(docker ps --no-trunc --format '{{.ID}} {{.Names}}' 2>/dev/null)

printf '%s\n' "$line" >> "$LOG"

if [ "${backend_anon:-0}" -ge "$WARN_MB" ]; then
    printf '%s KRITIK: hukdok_backend anon=%s MB (esik %s MB) - OOM yolunda\n' \
        "$ts" "$backend_anon" "$WARN_MB" >> "$LOG"
fi
