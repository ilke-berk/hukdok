# Sunucu Sertleştirme Planı

*Tarih: 2026-07-30 · Tetikleyici: 2026-07-29'daki üç kesinti · Son güncelleme: 2026-07-30 02:35*

## Durum özeti

| Madde | Durum | Not |
|---|---|---|
| 0 — SSH erişimi | ✅ bitti | `ssh hukukoid` + `ssh hukukoid-cc`, ikisi de kalıcı |
| 1 — Ağ nöbetçisi | ✅ kuruldu | Karar mantığı test edildi; gerçek onarım ilk arızada sınanacak |
| 4 — Log rotasyonu | ✅ uygulandı | 50m × 3, altı konteynerde doğrulandı |
| 5 — Konteyner limitleri | ✅ uygulandı | Backend 2 GiB, swap kapalı; 40 sn kesinti |
| 6 — Bellek kayıtçısı | ✅ kuruldu | `/var/log/mem-watch.log`, 5 dk'da bir + KRITIK eşiği |
| 7 — Dosya sistemi | ✅ gerek kalmadı | cloud-init `sda1`'i 199 GB yapmış |
| 8 — Static IP | ✅ risk yoktu | Adres 29 Mart'tan beri ayrılmış (`hukukoid`) |
| 3 — Seri konsol | ✅ uygulandı | Politika engeli yoktu; erişim okunarak doğrulandı |
| 2 — Uptime alert | ✅ kuruldu | 60 sn, 3 bölge, 2 e-posta kanalı; arıza testi geçti |
| 6 — Sızıntının kendisi | ✅ **KÖK NEDEN BULUNDU (2026-07-30)** | TIFF/UDF dönüşüm tepe tahsisi + glibc arena tutması; reprodüksiyonla kanıtlandı, düzeltmeler yazıldı (bkz. Madde 6 → Kök neden) |
| Makine 4→8 GB | ⏳ açık | Artık güvenle yapılabilir (IP static) |
| SCREENSHOT | ⏳ açık | Display device gerektiriyor → stop/start |

**Açık duran asıl risk:** kök neden (backend bellek büyümesi) hâlâ orada. Limitler artık makinenin tamamının gitmesini engelliyor ama sızıntıyı durdurmuyor.

**Tek elle doğrulanacak şey:** alert e-postasının gelen kutusuna düştüğü. GCP incident'ları public API ile sorgulanamıyor.

## Bağlam: dün ne oldu

Üç kesinti yaşandı, **iki farklı kök nedenden**. Ayırt edici imzaları bilmek önemli, çünkü müdahale farklı:

> ### ⚠️ TEŞHİS REVİZYONU — 2026-07-30 02:10
> Bu bölümün ilk hâli üç kesintiyi **iki ayrı kök nedene** bağlıyordu (disk I/O + DHCP) ve 1 ile 2'yi "disk yükseltmesiyle çözüldü" işaretliyordu. **Journal kanıtı bunu çürüttü.** Üç kesintinin de tek bir kök nedeni var: **backend'in anonim bellek büyümesi.** Disk hiçbir kesintinin sebebi değildi. Aşağıdaki tablo düzeltilmiş hâlidir; eski gerekçe [Çürütülen teşhis](#çürütülen-teşhis-disk-io) başlığında duruyor.

| # | Saat (yerel) | İmza | Kök neden | Durum |
|---|---|---|---|---|
| 1 | 15:30–15:52 | ping ✅, TCP ✅, uygulama verisi ❌ | Bellek baskısı — backend şişmesi | ❌ **Çözülmedi** |
| 2 | 16:05–16:20 | Aynı | Aynı | ❌ **Çözülmedi** |
| 3 | 17:52–01:16 | ping ❌, TCP ❌, VM "Running" | Aynı; ağ kaybı ve OOM bunun sonucu | ❌ **Çözülmedi** |

3 numaralı kesintinin başlangıcı **18:49 değil 17:52**. 18:49 sadece fark edildiği an; ağ 57 dakika önce gitmişti.

### Kanıt

Boot -1'in ölçülen zaman çizgisi:
```
13:18:34 UTC (16:18 yerel)  [sda] 104857600 blok (50 GiB)   <- boot basliyor
13:31:06 UTC (16:31 yerel)  [sda] 419430400 blok (200 GiB)  <- DISK BUYUTULDU
14:52:16 UTC (17:52 yerel)  ens4: Could not set DHCPv4 address: Connection timed out
14:52:17 UTC (17:52 yerel)  ens4: Failed
15:33:34 UTC (18:33 yerel)  Out of memory: Killed process 1650 (uvicorn)
                            total-vm:6631540kB  anon-rss:3571008kB  file-rss:0kB
                            constraint=CONSTRAINT_NONE  global_oom
```

Bundan çıkan dört sonuç:

**1. Disk yükseltmesi kesintiyi önlemedi.** Disk 16:31'de 200 GiB oldu; sistem 17:52'de ağı kaybetti, 18:33'te OOM'a girdi. Yükseltme arızadan **81 dakika önceydi.**

**2. Hiçbir boot'ta I/O arızası imzası yok.** `hung_task`, `blocked for more than`, `soft lockup`, `I/O error` — boot -3, -2 ve -1'de hiçbiri geçmiyor. Disk doygunluğu teşhisi kanıtsız.

**3. Üç boot'un ortak imzası bellek baskısı:**

| Boot | Kesinti | `Under memory pressure` | OOM kill | I/O arızası |
|---|---|---|---|---|
| -3 | 1 | 12 kez | — | **yok** |
| -2 | 2 | 1 kez | — | **yok** |
| -1 | 3 | 27 kez | **var** | **yok** |

**4. `anon-rss 3571008kB` + `file-rss 0kB` — Madde 5'in açık sorusu kapandı.** Şişme sayfa önbelleği değil, **3.57 GB gerçek anonim bellek**. "3 GB'ın büyük kısmı geri kazanılabilir dosya önbelleği olabilir" hipotezi öldü. `global_oom`, yani konteyner limiti değil makinenin tamamı bitti.

### Ağ kaybı bağımsız bir arıza değil, muhtemelen sonuç

DHCP timeout'u OOM'dan 41 dakika önce geldi ve boot -1 o sırada 27 kez bellek baskısı bildiriyordu. Bellek baskısı altında `systemd-networkd`'nin DHCP işlemini tamamlayamaması beklenen bir davranış. Kesin kanıtlanmış değil ama en güçlü açıklama bu — "Google tarafında bir saniyelik dalgalanma" değil.

**Daha çarpıcı olan:** ağ 17:52'de gittikten sonra sunucuya hiç istek gelmedi, ama backend 18:33'e kadar büyümeye devam edip 3.57 GB'a ulaştı. Yani büyüme **istek kaynaklı değil** — arka planda çalışan bir iş ya da yenilenen bir önbellek. Bu, Madde 6'daki `MuvekkilMatcherV2` + `list_searcher` şüphesini doğrudan işaret ediyor.

### Şu anki durum (taze açılış, ~50 dk, hafif yük)

```
free -m        : total 3910 · used 898 · available 3011 · swap 0 kullanimda
backend cgroup : anon 91.5 MB · file 41.7 MB
```
Backend şu an 91 MB anon. OOM anında 3.57 GB'dı — **~39 kat**. Bu fark, kararlı hâl kullanımı değil birikme olduğunu gösteriyor.

### Çürütülen teşhis: disk I/O

İlk teşhis şuydu: "50 GB disk belge dönüşümü yükünü kaldırmadı → I/O doygunluğu; `docker logs`'un log dosyasını okuması tetikledi." Yanlış olduğu kanıtlandı ama tamamen mantıksız değildi — mekanizması şöyle kurulabilir: bellek tükenir → çekirdek agresif swap'lar → 2 GB swap dolar → swap thrashing sürekli disk I/O üretir → yavaş diskte bu I/O doygunluğu gibi görünür. Yani gözlenen I/O yükü **belleğin semptomuydu.** Planın kendisi de Madde 5'te bunu sezmiş ("konteynerin swap'a taşması, I/O fırtınasının mekanizmasıydı") ama sonra diski kök neden sayıp 1 ve 2'yi çözüldü işaretlemişti.

Disk yükseltmesi yine de zararsız ve faydalı: swap thrashing daha hızlı diskte daha az acı verir, `sda1` de artık 199 GB. Ama **kök nedene dokunmadı.**

### Bunun diğer maddelere etkisi

- **Madde 5 + 6 artık en yüksek öncelik.** Sıralamada 7, 8, 9. basamaktaydılar; gerçek çözüm onlar ve gereken veri zaten elde.
- **Madde 1 (nöbetçi) tek başına yetmez.** DHCP arızası bellek baskısının sonucuysa, aynı baskı altında `networkctl reconfigure` da başarısız olur. Nöbetçinin garanti getirisi onarım değil, `KRITIK` + Madde 2 alert'i ile **6.5 saatlik sessizliği 2 dakikaya indirmesi.**
- **Madde 5'teki makine yükseltmesi** (4 → 8 GB) "ölçüm sonrası değerlendirilir" değil, ciddi bir aday: 3.8 GB'da iki stack + PDF/OCR çalıştırıyoruz ve OOM'u zaten gördük.
- **Madde 7 kendiliğinden bitti** — cloud-init `sda1`'i 199 GB'a genişletmiş.

## Ortam gerçekleri (2026-07-30 ölçümleri)

| | |
|---|---|
| Proje / zone / instance | `gen-lang-client-0074242743` / `europe-west3-a` / `instance-20260129-212613` |
| Makine | 2 vCPU, **3.8 GB RAM**, 2 GB swap — 2026-07-29'da global OOM yaşandı, yetersizlik kanıtlı |
| Boot disk | 200 GB Balanced PD · `sda1` **199 GB** (cloud-init son boot'ta genişletti; `df -h /` → 193 G, 19 G kullanımda) |
| Ağ | `ens4`, **DHCP** ile `10.156.0.2/32`, gateway `10.156.0.1`, kira `169.254.169.254`'ten |
| Dış IP | `35.234.119.194` — **kalıcı (static) olup olmadığı doğrulanmadı** |
| Docker | 29.2.0 · Compose v5.0.2 |
| Compose dizinleri | `~/hukdok` ve `~/hukukbot-ui` (iki ayrı stack, 6 konteyner) |
| Log rotasyonu | **YOK** — `/etc/docker/daemon.json` mevcut değil |
| Konteyner limitleri | **YOK** — hepsinde `HostConfig.Memory: 0` |
| Docker disk | İmajlar 8.77 GB · build cache 5.42 GB (3.5 GB geri kazanılabilir) |
| Seri konsol / SCREENSHOT | **Kapalı** — "instance does not have a display device enabled" |
| `ping` | **Kurulu değil** (`iputils-ping` yok) — kutunun içinden ICMP testi yapılamaz |
| Instance servis hesabı | `compute` scope'u **yok** → sunucu kendi metadata'sını yazamaz; konsol/gcloud şart |
| Saat | NTP `active`, senkron, `Etc/UTC` — kayma yok. Log damgaları yerel saatten 3 sa geride |

---

## Madde 0 — SSH erişimini kalıcı hale getir · ENGELLEYİCİ → **büyük ölçüde ÇÖZÜLDÜ (2026-07-30)**

### Teşhis düzeltmesi — ilk varsayım yanlıştı

Bu madde başlangıçta "guest agent elle eklenen satırı periyodik olarak siliyor" varsayımıyla yazıldı. **Ölçüm bunu çürüttü.** Agent hiçbir şey silmiyor; bozuk satırı sadakatle yazıyor. Instance metadata'sındaki `ssh-keys` değerinin ölçülen hali:

```
1) claude-code:ssh-ed25519 AAAAC3…kn2d claude-code@ilke-pc          ← GEÇERLİ
2) claude-code:luciferandlucius:ssh-ed25519 AAAAC3…kn2d claude-…    ← BOZUK, çift önek
3) luciferandlucius:ecdsa-sha2-nistp256 … google-ssh {"expireOn":"2026-07-29T22:30:13+0000"}
4) luciferandlucius:ssh-rsa … google-ssh {"expireOn":"2026-07-29T22:30:16+0000"}
```

2. satır, `luciferandlucius:ssh-ed25519 …` dizesinin konsolun **kendisi zaten `kullanıcı:` öneki ekleyen** "SSH Keys" kutusuna yapıştırılmasıyla oluşmuş. Sonuç: kullanıcı adı `claude-code`, anahtar gövdesi ise `luciferandlucius:ssh-ed25519 AAAA…`. Agent bunu `/home/claude-code/.ssh/authorized_keys`'e olduğu gibi yazıyor, sshd de `luciferandlucius:ssh-ed25519`'u bilinmeyen anahtar tipi sayıp yok sayıyor.

`/home/luciferandlucius/.ssh/authorized_keys` **hiç mevcut değil** — yani bu kullanıcının anahtarı hiçbir zaman yerleşmedi. Dün gece çalışan erişim 3. ve 4. satırlardaki tarayıcı SSH'ının geçici anahtarlarıydı; 22:30'da süreleri dolunca erişim bitti. "Eklendi, çalıştı, sonra silindi" gözlemi buydu.

### Ölçülen ortam gerçekleri

| Kontrol | Sonuç |
|---|---|
| `enable-oslogin` | 404 — ayarlı değil, metadata anahtarları geçerli yol |
| `block-project-ssh-keys` | 404 — ayarlı değil |
| Proje düzeyi `ssh-keys` | 404 — yok, tüm anahtarlar instance düzeyinde |
| `google-guest-agent` | `active` |
| Servis hesabı scope'ları | `compute` **YOK** → metadata sunucunun içinden yazılamaz, konsol şart |
| `gcloud` (ilke-pc) | kurulu değil |

### Çalışan erişim yolu — `claude-code@`

1. satır doğru kayıtlı olduğu için bu kullanıcı **kalıcı**: agent onu her senkronizasyonda yeniden yerleştiriyor. Yetkileri ölçüldü:

- Gruplar: `google-sudoers` → **şifresiz sudo var**
- `docker` grubunda **değil** → docker komutları `sudo` ile çalışır
- `sudo docker ps` ✅ altı konteyner · `sudo docker compose -f …/hukdok/docker-compose.yml config` ✅
- `/home/luciferandlucius/hukdok` ve `hukukbot-ui` sudo ile erişilebiliyor

Yani diğer maddelerin ön koşulu karşılandı. `~/.ssh/config`'e kalıcı alias eklendi:
```
Host hukukoid-cc
    HostName hukukoid.com
    User claude-code
    IdentityFile ~/.ssh/id_ed25519_hukukoid
```
Bu yolla çalışırken **her docker/compose komutunun başına `sudo`** gelmeli — deploy notlarındaki komutlar `luciferandlucius` varsayıyor.

### `ssh hukukoid` yolu onarıldı ✅ (2026-07-30 01:44 TR)

Konsolda bozuk kayıt silinip anahtar **önek yazılmadan**, yorum alanı `luciferandlucius` olacak şekilde eklendi:
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIImUrt7qhrreInaQJtzTrzcDsMSS6L2wSphrb9s0kn2d luciferandlucius
```

Metadata'nın ölçülen yeni hali — dört satır, hepsi geçerli, çift önek gitti:
```
claude-code       | ssh-ed25519 AAAAC3…
luciferandlucius  | ecdsa-sha2-nistp256 …   (google-ssh, tarayıcı SSH'ı yönetiyor)
luciferandlucius  | ssh-rsa …               (google-ssh, tarayıcı SSH'ı yönetiyor)
luciferandlucius  | ssh-ed25519 AAAAC3…     ← yeni
```

Guest agent `/home/luciferandlucius/.ssh/authorized_keys`'i kendisi oluşturdu (`# Added by Google`, mtime 22:44:28 UTC) ve `claude-code`'daki bozuk satırı temizledi. Anahtarı agent'ın *kendisi* yerleştirdiği için kalıcılık yapısal olarak kanıtlı; 10 dakikalık bekleme testi çürütülen eski teoriye aitti, artık gereksiz.

**Ölçülen yetkiler:** `luciferandlucius` hem `docker` hem `google-sudoers` grubunda → docker sudo'suz çalışıyor, sudo da şifresiz. (Planın ilk halinde ve eski notlarda "passwordless sudo'su YOK" yazıyordu — **yanlış**.) Deploy komutları olduğu gibi, `sudo`'suz çalışır.

**Sonuç:** iki erişim yolu da açık. `ssh hukukoid` birincil (sudo'suz docker), `ssh hukukoid-cc` yedek. Madde 0 kapandı.

### Yan bulgu — sunucu saati sağlam
`timedatectl`: NTP `active`, `System clock synchronized: yes`, saat dilimi `Etc/UTC`. Dosya zaman damgaları UTC olduğu için yerel saatle 3 saat geride görünüyor; kayma **yok**. Boot zamanı `2026-07-29 22:16 UTC` = `01:16 TR` — plandaki reset anıyla birebir örtüşüyor.

---

## Madde 1 — Ağ nöbetçisi · EN YÜKSEK ÖNCELİK → **KURULDU (2026-07-30 01:53 TR)**

6.5 saatlik kesintiyi 1–2 dakikaya indirir. Kritik tasarım gerekçesi: **DHCP'nin neden düştüğünü bilmeyi gerektirmez.** Asıl kusur Google tarafındaki bir saniyelik dalgalanma değil, sunucunun ondan geri dönememesi. Nöbetçi tam bu boşluğu kapatır.

### Kurulum öncesi ölçüm — planın ilk script'i iki yerden değişti

**1. `ping` bu kutuda kurulu değil.** Bağlam tablosundaki "ping ✅ / ping ❌" triyajı dışarıdan yapılmış; sunucunun içinde `ping` binary'si yok. Nöbetçi erişilebilirliği ping'le ölçemez. Yerine üç yapısal sinyal kullanılıyor:

| Sinyal | Komut | 2026-07-29 arızasında |
|---|---|---|
| Global IPv4 adresi var mı | `ip -4 addr show ens4 scope global` | ❌ (`Could not set DHCPv4 address`) |
| ens4 üzerinden default route var mı | `ip route show default dev ens4` | ❌ |
| networkd arayüzü `routable` görüyor mu | `networkctl list ens4` → 4. alan | ❌ (`ens4: Failed`) |

**2. Planın ilk script'i uzun arızada dakikada bir `systemctl restart systemd-networkd` çalıştırıyordu.** Risk bölümü "3 saniyelik yanlış pozitif"i tek seferlik varsayıp kabul etmişti; tekrarını hesaba katmamış. Metadata erişilemez ama yerel ağ sağlıklıysa (Google tarafında bir metadata kesintisi) bu, çalışan siteyi sonsuza kadar her dakika sarsardı. İki koruma eklendi:

- **Yanlış pozitif kapısı:** üç sinyal de sağlamsa ağ cerrahisi **yapılmaz**, sadece raporlanır. Sorun bizde değilse networkd'ye dokunmuyoruz.
- **Backoff:** müdahale 2–6. turlarda her tur, sonrasında 10 turda bir. 12 turluk bir arızada orijinal script 11 restart yapardı, bu sürüm 6 deneme yapıyor.

### Script: `/usr/local/sbin/net-watchdog.sh` (kurulu hâli)

```bash
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
```

Sağlıklı koşuda **hiçbir şey yazmaz** — log dosyasının varlığı zaten bir sinyaldir. Script repoda tutulmuyor; tek yetkili kopyalar sunucudaki `/usr/local/sbin/net-watchdog.sh` ve yukarıdaki blok. Değiştirilecekse ikisi birlikte güncellenmeli.

### Unit: `/etc/systemd/system/net-watchdog.service`
```ini
[Unit]
Description=Ag nobetcisi - metadata erisilemezse ens4'u toparlar
After=network.target
Documentation=file:///usr/local/sbin/net-watchdog.sh

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/net-watchdog.sh
TimeoutStartSec=120
```
`TimeoutStartSec` eklendi: script en kötü hâlde ~30 sn sürüyor (5+5+5+10+5), takılan bir `curl` timer'ı süresiz bloklamasın.

### Timer: `/etc/systemd/system/net-watchdog.timer`
```ini
[Unit]
Description=Ag nobetcisini dakikada bir calistir

[Timer]
OnBootSec=2min
OnUnitActiveSec=1min
AccuracySec=10s

[Install]
WantedBy=timers.target
```

### Kurulum — yapıldı ✅
```bash
# script CRLF'siz kurulmali, yoksa bash bozulur
tr -d '\r' < net-watchdog.sh | ssh hukukoid \
  "sudo install -m 0755 -o root -g root /dev/stdin /usr/local/sbin/net-watchdog.sh"
sudo bash -n /usr/local/sbin/net-watchdog.sh      # sozdizimi: OK
sudo systemctl daemon-reload
sudo systemctl enable --now net-watchdog.timer
```
Kurulum sonrası ölçülen durum: timer `enabled` + `active`, 60 saniyede bir tetikleniyor, üç ardışık koşu `Result=success`, `/var/log/net-watchdog.log` **oluşmadı** (sağlıklı koşuda yazmaz — doğru davranış), site `200`, altı konteyner ayakta, `ens4` hâlâ `routable/configured`.

**Tuzak:** `systemctl list-timers` tetiklemeden hemen sonra sorgulanırsa `NEXT` kolonu `-` gösterir ve timer ölü sanılır. Doğru kontrol `systemctl status net-watchdog.timer` içindeki `Trigger:` satırı ya da `systemctl show ... -p NextElapseUSecMonotonic`.

### Log rotasyonu — `/etc/logrotate.d/net-watchdog`
```
/var/log/net-watchdog.log {
    weekly
    rotate 8
    compress
    missingok
    notifempty
}
```
Nöbetçinin kendi log'unun sınırsız büyümesini engeller — Madde 4'teki hatanın tekrarı olmasın.

### Doğrulama — karar mantığı ✅, gerçek onarım ⏳

Karar mantığı gerçek script üzerinde test edildi. Yöntem: `sed` ile bir test kopyası üretilip `probe` daima başarısız kılındı, tüm ağ müdahaleleri stub'landı, log/state `/tmp`'ye yönlendirildi. **Ağa hiç dokunulmadı.**

| Test | Senaryo | Beklenen | Sonuç |
|---|---|---|---|
| A | Yerel ağ bozuk (stub) | 1. tur bekle · 2–6 müdahale · 7–9 backoff · 10 müdahale | ✅ 6 deneme, 5 atlama |
| B | Ağ sağlıklı, metadata erişilemez (gerçek sinyaller) | Ağ cerrahisi **yok**, 5. turda tek KRITIK | ✅ 0 müdahale, 1 KRITIK |
| C | Toparlanma: probe geri gelir | `TOPARLANDI` + sayaç silinir | ✅ |
| D | State dosyası bozuk (`COPCOP`) | Çökmeden 1'e döner | ✅ |

D testi planın ilk script'inde bir açık kapatıyor: orada `fails=$(cat ...)` çıktısı doğrulanmıyordu, bozuk state ile `$((fails + 1))` aritmetik hatası verirdi. Kurulu sürümde `case` ile temizleniyor.

**Test edilmeyen tek şey: gerçek onarımın işe yarayıp yaramadığı** — yani DHCP yapılandırması gerçekten kaybolduğunda `networkctl reconfigure ens4`'ün rotayı geri getirmesi. Bunun için ağı kasten bozmak gerekiyor ve o adım izin katmanı tarafından bloke edildi (prod ağına müdahale). Karar mantığı ve tetikleme kanıtlı; onarım eyleminin kendisi ilk gerçek arızada sınanacak.

**Planın orijinal test yöntemi ayrıca geçersiz.** Önerilen komut şuydu:
```bash
sudo ip route del 169.254.169.254 via 10.156.0.1 dev ens4
```
Ama ölçülen rota tablosunda default route **aynı gateway'e** gidiyor:
```
default          via 10.156.0.1 dev ens4 proto dhcp src 10.156.0.2 metric 100
169.254.169.254  via 10.156.0.1 dev ens4 proto dhcp src 10.156.0.2 metric 100
```
`/32` rotası silinince trafik default route'a düşer ve metadata'ya **aynı yoldan** ulaşır. Yani probe muhtemelen hiç başarısız olmaz, test de hiçbir şey kanıtlamaz. Gerçek arıza taklidi için `ip route add blackhole 169.254.169.254` gibi daha spesifik bir rota gerekir — ama o rotayı networkd'nin `reconfigure`'da temizleyip temizlemeyeceği belirsiz (`ManageForeignRoutes` varsayılan `yes`, systemd 255), yani temizlemezse nöbetçi hiç "TOPARLANDI" yazamaz ve blackhole elle silinmek zorunda kalır.

### Risk
`systemctl restart systemd-networkd` kısa bir ağ kesintisi yaratır (1–3 sn). İki turluk eşik + yanlış pozitif kapısı + backoff bu riski üç katmanda sınırlıyor: sağlıklı ağda hiç tetiklenmez, tetiklenirse en fazla 5 ardışık deneme yapar, sonra 10 turda bire düşer. Ölçüsü şu: 3 saniyelik yanlış pozitif mi, 6.5 saatlik sessiz kesinti mi.

Kalan asıl risk yanlış pozitif değil, **yanlış negatif**: üç sinyal de sağlam görünürken metadata'ya gerçekten bizim tarafımızdan ulaşılamaması. O durumda nöbetçi müdahale etmez, sadece KRITIK yazar — ve bunu duymanın tek yolu Madde 2'deki dışarıdan uptime check'i.

---

## Madde 2 — Uptime alert · **KURULDU ✅ (2026-07-30 03:00)**

Konsoldan değil `gcloud` + Monitoring REST API ile kuruldu.

**Uptime check** — `hukukoid-com-https-wuv_LieESrA`
```
host: hukukoid.com · HTTPS · path / · port 443 · validateSsl
period: 60s · timeout: 10s
bolgeler: EUROPE, USA, ASIA_PACIFIC  (5 checker konumu: eur-belgium,
          usa-virginia, usa-oregon, usa-iowa, apac-singapore)
```

**Bildirim kanalları** — iki adres, ki gece yarısı uyarı mutlaka birine ulaşsın:
`lexis@lexis.com.tr` ve `luciferandlucius@gmail.com`

**Alert politikası** — `alertPolicies/6982954504192974256`
```
kosul   : uptime_check/check_passed · REDUCE_COUNT_FALSE
          groupBy resource.label.host · alignment 300s
          COMPARISON_GT threshold 1 · duration 60s
autoClose: 1800s
```
Eşiğin `> 1` olması kritik: tek bir bölgeden gelen anlık dalgalanma uyarı üretmiyor, en az iki başarısız prob gerekiyor. Planın "tek bölgeden yanlış pozitif gelebilir" uyarısının karşılığı bu.

Politikaya müdahale talimatı gömüldü (`documentation.content`), uyarı e-postasında görünür: sırayla `ssh hukukoid` → `net-watchdog.log` → `mem-watch.log` → `docker ps`, nöbetçi toparlamadıysa konsoldan RESET.

### Test — "test edilmemiş alert, alert değildir"

Arıza kasten enjekte edildi, **siteye dokunulmadan**: check'in kabul ettiği yanıt kodu geçici olarak `500` yapıldı, böylece sitenin verdiği `200` başarısızlık sayıldı. 02:57:40'ta uygulandı, 03:01:55'te geri alındı.

Sonuç — beş checker konumunun **hepsi** başarısıza döndü (27 başarısız prob):
```
usa-virginia    000111111...   <- soldan saga YENI -> ESKI
usa-oregon      0000000111...
usa-iowa        000000111...
eur-belgium     00000111...
apac-singapore  000000111...
```
Koşul (`>1` başarısız) fazlasıyla sağlandı. Site test boyunca `200` dönmeye devam etti.

> **Yakalanan tuzak:** ilk enjeksiyon denemesi check'in yolunu var olmayan bir adrese çevirmekti (planın önerdiği mantık). **İşe yaramadı** — frontend bir SPA ve nginx `try_files` ile her yolu `index.html`'e düşürdüğü için 404 değil **200** döndü. Doğrulamasaydım test geçmiş sanılacaktı. `hukukoid.com` üzerinde 404 üretmek için yol değiştirmek yeterli değil; kabul edilen durum kodunu değiştirmek gerekiyor.

**Toparlanma da doğrulandı (03:07):** geri alma sonrası beş bölgenin hepsi tekrar geçti. Yani döngünün tamamı sınandı — arıza enjeksiyonu → beş bölgeden algılama → normale dönüş. Alert `autoClose: 1800s` ile kapanır, toparlanma da kapatır.

**Kalan tek adım:** e-posta kutusundan uyarının geldiğinin gözle teyidi. GCP Monitoring **incident**'ları public API ile sorgulanamıyor, o yüzden bu kısım otomatik doğrulanamıyor. Kanalların `verificationStatus` alanı boş dönüyor (UNSPECIFIED) — bu "doğrulanmadı" demek değil ama e-posta gelmediyse ilk bakılacak yer orası.

<details><summary>Planın orijinal konsol talimatı (referans)</summary>


Nöbetçi çoğu vakayı kendi toparlar; toparlayamadığında **haberimiz olması** gerekiyor. Dün gece kesinti 6.5 saat sürdü çünkü kimse bilmiyordu.

**Konsolda:** Monitoring → **Uptime checks** → CREATE UPTIME CHECK
- Protocol: **HTTPS** · Hostname: `hukukoid.com` · Path: `/`
- Check frequency: **1 minute**
- Regions: en az 2 bölge (tek bölgeden yanlış pozitif gelebilir)
- Alerting: **Duration 1 minute**, bildirim kanalı = e-posta

Yanına ikinci bir alert daha değerli olur — **nöbetçinin başarısız olduğu durum için**. Log-based alert:
- Monitoring → Logs-based metrics ya da Alerting → yeni policy
- Koşul: `/var/log/net-watchdog.log` içinde `KRITIK` görülmesi (Ops Agent log toplamayı gerektirir)

Basit alternatif: nöbetçi script'inin `KRITIK` durumunda e-posta atması. Ama sunucunun ağı yokken e-posta gidemez — bu yüzden **asıl güvence dışarıdan yapılan uptime check'tir.** Sunucunun kendi kendini ihbar etmesine güvenilemez.

</details>

---

## Madde 3 — Gözlemlenebilirlik: seri konsol · **UYGULANDI ✅ (2026-07-30 02:58)**

```bash
gcloud compute instances add-metadata instance-20260129-212613 \
  --zone europe-west3-a --metadata serial-port-enable=TRUE
```

**Kuruluş politikası endişesi yersizdi.** Ölçüm:
```
gcloud resource-manager org-policies describe compute.disableSerialPortAccess --effective
  booleanPolicy: {}          <- BOS = uygulanmiyor (uygulansaydi 'enforced: true')
gcloud projects describe ...
  (parent alani YOK)         <- proje bagimsiz, miras alinacak politika da yok
```
Dünkü "Connecting to serial ports is disabled" yazısının sebebi politika değil, sadece metadata'nın ayarlı olmamasıydı.

**Doğrulama — erişim gerçekten açıldı.** Metadata'yı ayarlamak yetmez, okuyabildiğimizi görmek gerekir:
```bash
gcloud compute instances get-serial-port-output instance-20260129-212613 --port 1
```
Çıktı geldi ve ilginç bir yan teyit sağladı — ağ nöbetçisinin koştuğunu bağımsız bir kanaldan doğruluyor:
```
2026-07-29T23:50:26Z ... Finished net-watchdog.service - Ag nobetcisi ...
```

`add-metadata` eklemeli çalışır, `ssh-keys` bozulmadı — sonrasında 4 satırın hepsi doğru önekle yerinde olduğu teyit edildi. (Madde 0'daki hatadan sonra bu kontrol şart.)

**SCREENSHOT** hâlâ kapalı; display device gerektiriyor, o da VM'i durdurmayı şart koşuyor. IP static olduğu için (Madde 8) artık risksiz yapılabilir, ama makine yükseltmesiyle birlikte tek stop/start'ta yapılmalı.

<details><summary>Planın orijinal notu (referans)</summary>


Dün üç kez kör kaldık. Seri konsol ve SCREENSHOT kapalı olduğu için ne panic mesajını ne de ağ hatasını arıza anında göremedik — kök nedeni ancak reset sonrası `journalctl -b -1` ile bulabildik ve o da şans eseri kalıcı log tutulduğu içindi.

```bash
# Seri porta erişimi ac (VM calisirken yapilabilir)
gcloud compute instances add-metadata instance-20260129-212613 \
  --zone europe-west3-a --metadata serial-port-enable=TRUE
```
Konsoldan da yapılabilir: VM → EDIT → Metadata → `serial-port-enable` = `TRUE`.

**Not:** Bu ayar bir kuruluş politikasıyla (`compute.disableSerialPortAccess`) engellenmiş olabilir. Dün "Connecting to serial ports is disabled" yazısını görmüştük; metadata denendikten sonra hâlâ kapalıysa sebep politikadır ve proje yöneticisi düzeyinde çözülmesi gerekir.

**SCREENSHOT** için display device gerekiyor, o ise VM'i durdurmayı şart koşuyor → Madde 7 ile birlikte, tek kesintide yapılmalı.

</details>

---

## Madde 4 — Docker log rotasyonu · **UYGULANDI ✅ (2026-07-30 02:29)**

`/etc/docker/daemon.json` yazıldı, docker daemon yeniden başlatıldı, iki stack recreate edildi. Altı konteynerin hepsinde doğrulandı:
```
log=map[max-file:3 max-size:50m]
```
Böylece tek bir konteynerin log dosyası en fazla 150 MB tutabilir. 2 numaralı kesintiyi mümkün kılan "tek log dosyasını okumak makineyi devirdi" durumu artık yapısal olarak imkânsız.


Loglar sınırsız büyüyor. 2 numaralı kesinti tam olarak bu yüzden mümkün oldu: tek bir konteynerin log dosyasını okumak makineyi devirdi.

### `/etc/docker/daemon.json`
```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "3"
  }
}
```

```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json > /dev/null <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "50m", "max-file": "3" }
}
EOF
sudo systemctl restart docker
```

### Kritik uyarı
Bu ayar **yalnızca yeni oluşturulan konteynerlere** uygulanır. Mevcut altı konteyner, yeniden **oluşturulana** kadar eski sınırsız ayarla çalışmaya devam eder — `restart` yetmez, `recreate` gerekir:
```bash
cd ~/hukdok        && docker compose up -d --force-recreate
cd ~/hukukbot-ui   && docker compose up -d --force-recreate
```
Bu yüzden Madde 5 ile birlikte yapılması mantıklı: zaten recreate gerekecek, tek kesintide ikisi de gider.

`systemctl restart docker` tüm konteynerleri kısa süre durdurur → **mesai dışı.**

### Mevcut şişmiş logları temizle
Rotasyon geçmişi silmez. Recreate işlemi eski log dosyalarını da götürür (yeni konteyner = yeni log dosyası), ama önce boyutu ölçmek faydalı:
```bash
sudo du -sh /var/lib/docker/containers/*/*-json.log | sort -h | tail
```

---

## Madde 5 — Konteyner kaynak limitleri

Şu an hiçbir konteynerde sınır yok. Disk hızlandı ama tek bir kaçak işin makinenin tamamını götürebilmesi ihtimali duruyor.

### ~~ÖNCE ÖLÇ~~ — soru zaten cevaplandı ✅

Bu bölüm "3 GB'ın sayfa önbelleği mi gerçek bellek mi olduğunu ölçmeden limit koymayalım" diyordu. **OOM log'u soruyu kapattı:**

```
anon-rss:3571008kB   file-rss:0kB
```

3.57 GB anonim, dosya destekli **sıfır**. Sayfa önbelleği hipotezi geçersiz; gerçek bellek büyümesi. "Birkaç saat belge işlendikten sonra ölçelim" beklemesine de gerek yok — kanıt elde.

Referans için taze açılış ölçümü (2026-07-30 02:05, ~50 dk uptime, hafif yük):
```
backend cgroup : anon 91.5 MB · file 41.7 MB · slab_reclaimable 8.0 MB
free -m        : used 898 · available 3011 · swap 0
```
OOM anındaki 3.57 GB ile şu andaki 91.5 MB arasında **~39 kat** fark var. Kararlı hâl kullanımı değil, birikme.

Karşılaştırma için ilerleyen ölçümler:
```bash
sudo docker exec hukdok_backend sh -c \
  "grep -E '^(anon|file|slab_reclaimable) ' /sys/fs/cgroup/memory.stat"
```

### Uygulanan limitler · **UYGULANDI ✅ (2026-07-30 02:29)**

Limitler `docker-compose.override.yml` dosyalarına yazıldı, `docker compose config` ile doğrulandı, recreate ile devreye alındı. Kesinti **40 saniye** (02:28:25 → 02:29:05).

Uygulama sonrası ölçüm — altı konteynerin hepsi:
```
hukdok_backend     mem=2147483648  swap=2147483648
hukudok-postgres   mem=536870912   swap=536870912
hukdok-frontend-1  mem=134217728   swap=134217728
hukukbot_api       mem=402653184   swap=402653184
hukukbot_db        mem=268435456   swap=268435456
hukukbot_frontend  mem=134217728   swap=134217728
```
cgroup seviyesinde de teyit edildi (backend):
```
memory.max      : 2147483648
memory.swap.max : 0          <- memswap_limit gercekten swap'i kapatti
```
Sağlık: site 200, backend `/docs` 200, altı konteyner ayakta, `OOMKilled=false`, `RestartCount=0`, backend logunda sıfır hata, 2013 müvekkil yüklendi, konteynerler arası çağrı (`hukukbot → hukdok /export/documents`) 200.

**Neden override dosyası, `docker-compose.yml` değil:** sunucudaki iki dizin de `main` dalında git checkout'u ve `docker-compose.yml` her ikisinde de **izleniyor**. Elle düzenlemek sonraki `git pull`'da çakışırdı. hukdok'ta override zaten `.gitignore:69`'da; hukukbot'ta izlenmiyor (untracked, pull'u engellemez).

| Konteyner | `mem_limit` | Ölçülen anon (02:20) | Pay |
|---|---|---|---|
| `hukdok_backend` | **2 g** | 87 MB | OOM'daki 3.57 GB'ın altında tavan |
| `hukudok-postgres` | 512 m | 8 MB | DB spike payı |
| `hukdok-frontend` | 128 m | 2 MB | nginx |
| `hukukbot_api` | 384 m | 108 MB | ~3.5× |
| `hukukbot_db` | 256 m | 7 MB | bol |
| `hukukbot_frontend` | 128 m | 2 MB | nginx |

Hepsinde `memswap_limit == mem_limit` → konteynere **swap yok**. Swap'a taşma, kesintilerdeki I/O fırtınasının mekanizmasıydı.

**CPU limiti bilinçli olarak konulmadı.** Planın ilk hâli `cpus` öneriyordu ama üç kesintide CPU açlığı kanıtı yok; üstelik backend'i throttle etmek dönüşümleri uzatır ve belleği daha uzun tutar — yani asıl sorunu kötüleştirebilir. Gerekirse sonradan eklenmesi tek satır.

**Toplam tavan 3456 MB / 3910 MB.** Limitler rezervasyon değil tavan olduğu için sorun değil (mevcut gerçek toplam ~214 MB), ama hepsi birden tavana çarparsa host'a ~450 MB kalır. Makine 8 GB'a çıkarsa bu payların tekrar gözden geçirilmesi gerekir.

### Uygulama komutu (tek kesinti penceresi, ~2-3 dk)
```bash
sudo systemctl restart docker                  # daemon.json devreye girer
cd ~/hukdok       && docker compose up -d --force-recreate
cd ~/hukukbot-ui  && docker compose up -d --force-recreate
```
Doğrulama:
```bash
for c in hukdok_backend hukudok-postgres hukdok-frontend-1 hukukbot_api hukukbot_db hukukbot_frontend; do
  docker inspect $c --format "$c mem={{.HostConfig.Memory}} log={{.HostConfig.LogConfig.Config}}"
done
curl -s -o /dev/null -w "site %{http_code}\n" https://hukukoid.com/
```

### Planın ilk önerisi (referans)

Toplam RAM 3.8 GB, altı konteyner, üstüne host işletim sistemi. Öneri:

| Konteyner | `mem_limit` | `cpus` | Gerekçe |
|---|---|---|---|
| `hukdok_backend` | `2g` | `1.5` | Ağır iş burada: PDF/OCR dönüşümü, Gemini, 2013 müvekkillik FlashText |
| `hukudok-postgres` | `512m` | `0.5` | Ölçülen kullanım 11 MB, bolca pay |
| `hukdok-frontend` | `128m` | `0.25` | nginx, ölçülen 2.5 MB |
| `hukukbot_api` | `512m` | `0.5` | Ölçülen 4 MB |
| `hukukbot_db` | `384m` | `0.5` | Ölçülen 17 MB |
| `hukukbot_frontend` | `128m` | `0.25` | Ölçülen 1 MB |

Compose'da (`~/hukdok/docker-compose.yml`):
```yaml
  backend:
    mem_limit: 2g
    memswap_limit: 2g      # swap'a taşmayı engeller - I/O firtinasi olusmasin
    cpus: 1.5
```
`memswap_limit` özellikle önemli: konteynerin swap'a taşması, 1 ve 2 numaralı kesintilerdeki I/O fırtınasının mekanizmasıydı.

### Kabul edilmesi gereken ödünç
Limit bir tavandır. Backend gerçekten 2 GB'ın üstüne çıkarsa **isteğin ortasında OOM ile öldürülür** — kullanıcı hata görür. Alternatifi ise tüm makinenin kilitlenmesi. Bilinçli tercih: bir isteği kaybetmek, sunucuyu kaybetmekten iyidir.

### Asıl soru: makine yeterli mi?
3.8 GB RAM'de iki stack + PDF/OCR dönüşümü çalıştırıyoruz. Sınırlar bunu yönetir ama genişletmez. Otonom dava açma sistemi devreye girdiğinde (toplu belge yüklemesi üzerine kurulu) talep artacak.

`e2-medium` (2 vCPU / 4 GB) → `e2-standard-2` (2 vCPU / 8 GB) yükseltmesi europe-west3'te kabaca **+$25/ay**. **Ama Madde 8 olmadan yapılmamalı** — makine tipi değişimi stop/start gerektirir ve dış IP kalıcı değilse değişir.

---

## Madde 6 — Backend bellek davranışını incele · **KÖK NEDEN BULUNDU ✅ (2026-07-30)**

> ### KÖK NEDEN — 2026-07-30 sabahı kapatıldı
>
> **DB kanıtı hacim hipotezini çürüttü:** boot -1 penceresinde yalnız 10 belge
> işlendi (7 UDF + 2 PDF + 1 TIF, `case_documents` sorgusu). Son belge (TIF,
> 14:07:47) işlendikten 8 dk sonra ilk bellek baskısı; son belgeden 86 dk sonra
> sıfır aktiviteyle OOM. Belge başına ~350 MB kalıcı tutulmuş.
>
> **Mekanizma:** ağır dönüşümler ana süreçte eşzamanlı koşuyor, tepe tahsis
> GB mertebesine çıkıyor ve glibc arena tutması yüzünden OS'a geri verilmiyor
> (cırcır etkisi). Klasik referans sızıntısı değil — kod okuması bu yüzden
> suçlu bulamadı.
>
> **Tepe tahsisi üreten kusur (reprodüksiyonla kanıtlı):**
> `pdf/format_converter.py::_normalize_frame` 1-bit G4 taramayı küçültme
> kontrolünden ÖNCE RGB'ye açıyordu (24× şişme, sayfa başına ~104 MB) ve
> `image_to_pdf` tüm kareleri listede tutuyordu. **Ölçüm (lokal konteyner):
> diskte 0.03 MB'lık 10 sayfalık 600 dpi G4 TIFF → eski kod tepe +1030 MB;
> düzeltilmiş kod → artış ölçülemedi.** 30 sayfa ≈ 3.1 GB = OOM'daki 3.57 GB.
> Üstelik dönüşüm belge başına iki kez koşuyor (/process + /confirm).
> İkincil: UDF inline/arkaplan görsel kopyaları, `TechnicalLogger._buffer`
> (repodaki tek sınırsız birikim), fitz doc'ların istisna yolunda açık kalması.
>
> **Uygulanan düzeltmeler:** (a) prod'a `MALLOC_ARENA_MAX=2` (override +
> recreate, 2026-07-30 00:42 UTC, site 200); (b) repo'da: normalize sırası
> düzeltildi + "1" modu korunuyor, image_to_pdf kare-kare akışlı, görüntü/UDF
> dönüşümüne Semaphore(1), TechnicalLogger deque(maxlen=2000) + ERROR flush
> thread'e + GS/LO stderr kırpma, fitz try/finally, e-posta tek encode +
> 50 MB limit, `async_cleanup` asyncio.sleep, soffice process-group kill,
> admin `/api/admin/debug/memory` endpoint'i. Kod deploy'u bekliyor.
>
> **Karar:** 2 GiB limit kalıyor (artık güvenlik ağı); 8 GB yükseltme acil
> değil — düzeltmeler deploy edilip 1 hafta mem-watch gözlendikten sonra
> otonom dava açma yüküne göre kararlaştırılacak.

### (Arşiv) İnceleme süreci — aşağıdaki bölümler bulgu öncesi yazıldı

Bu madde "Madde 5'in ölçümü `anon` yüksek çıkarsa açılır" diye koşula bağlanmıştı. **Koşul gerçekleşti:** OOM log'u `anon-rss 3571008kB · file-rss 0kB` gösteriyor. Üç kesintinin de kök nedeni burada.

### Ölçülen büyüme hızı

Boot -1'in bellek zaman çizgisi (UTC):
```
13:18:34  boot basliyor - backend taze
14:15:34  ILK "Under memory pressure" (tek olay)     <- ag hala saglam
14:52:16  ens4 Failed - ag gitti
15:06-15:33  kesintisiz baski, neredeyse her dakika (26 olay)
15:33:34  OOM - backend 3.57 GB anon
```

**Taze başlangıçtan OOM'a ~2 saat 15 dakika.** Aynı desen diğer boot'larda da var: boot -3 ~3 saat, boot -2 ~20 dakika sonra baskıya girmiş. Makine her açılışta birkaç saat dayanıyor.

İlk bellek baskısı ağ kaybından **37 dakika önce** geldi → birikme gün içinde, gerçek trafikle oldu.

> **Çürütülen ara çıkarım:** "Ağ 17:52'de gitti, sonra istek gelmedi, yine de büyüdü → büyüme istek kaynaklı değil, arka plan işi aramalıyız." Bu yanlıştı. 15:06–15:33 arasındaki kesintisiz baskı yeni tahsis kanıtı değil; tavana yaklaşıp swap dolarken çekirdek yeni bellek istenmeden de sürekli "flushing caches" bildirir. Ayrıca kodda o pencerede dönen bir arka plan işi yok: `refresh_lists_background` ve `catch_up_missed_reports` tek seferlik, APScheduler işi 00:00 cron'u. **Sızıntı istek yolunda aranmalı.**

### Elenen şüpheliler (kod okundu)

Planın orijinal üç şüphelisinin ikisi elendi:

- **`MuvekkilMatcherV2`** — `load_clients()` `self.clients` setini komple değiştiriyor, eski set GC'ye gidiyor. Birikme yok. (Ayrı bir israf var: `filtrele()` her çağrıda 2013 ismi yeniden normalize edip yeni set kuruyor — sızıntı değil ama gereksiz.)
- **`ListSearcher`** — `_load_data()` hem `client_map`'i hem `KeywordProcessor`'ı sıfırdan kuruyor. Birikme yok.
- **`PROCESS_CACHE`** — bellekte PDF **tutmuyor**; `{'path': ...}` yani disk yolu tutuyor (`routes/processing.py:32`, TTL 1800 sn). Planın "PDF'leri bellekte tutuyor" varsayımı yanlış. Disk sızıntısı olabilir, bellek sızıntısı değil.

Kalan şüpheli ve aranacak yer:


- **`PROCESS_CACHE`** — analiz edilen PDF'leri TTL ile bellekte tutuyor. TTL dolmadan biriken dosyalar şişme yaratabilir. Otonom dava açma planındaki `keepalive` mekanizması TTL'i *tazelediği* için bu riski artıracak; sihirbaz devreye girmeden önce bu davranışın anlaşılması gerekiyor.
- **`MuvekkilMatcherV2` + `list_searcher`** — 2013 müvekkil iki ayrı yapıya yükleniyor ve loglarda arka arkaya birkaç kez "yenilendi" görülüyor. Yenilemede eski yapı bırakılmıyorsa her turda birikir.
- **Ghostscript/LibreOffice alt süreçleri** — dönüşüm başına bellek, eşzamanlı istekle çarpılır. Eşzamanlılık sınırı var mı, kontrol edilmeli.

Ölçüm yolu:
```bash
# Zaman icinde egilim (birkac saat aralikli iki olcum)
docker exec hukdok_backend sh -c "grep -E '^(anon|file) ' /sys/fs/cgroup/memory.stat"
# PROCESS_CACHE'in tuttugu gecici dosyalar
docker exec hukdok_backend sh -c "ls -la /tmp | head -30; du -sh /tmp"
```
Yükselen bir `anon` eğilimi sızıntıyı doğrular. ("Sabit kalıyorsa sorun yok, gördüğüm 3 GB önbellekti" şıkkı artık geçerli değil — OOM log'u önbellek olmadığını kanıtladı.)

### Kod okuması sonucu — suçlu bulunamadı

Tüm modül seviyesi mutable yapılar tarandı (`^[A-Z_]+ = {}` / `[]` deseni): yalnızca `_MSAL_APPS` (auth_graph.py, istemci başına sınırlı) ve iki `TTLCache`. TTLCache küçük sözlükler tutuyor — 10.000 girdi bile birkaç MB. Modül seviyesinde 3.57 GB'ı açıklayacak birikme **yok**.

Bulunan iki gerçek kusur (düzeltilmeye değer ama bu ölçeği açıklamaz):

`pdf_utils.py` `load_and_analyze_pdf`'te `doc.close()` iki yolda atlanıyor:
- satır 33 — `total_pages == 0` erken dönüşü
- satır 101-103 — `except Exception` tüm hataları yakalayıp `doc` açık dönüyor

Aynı desen `extract_key_pages`'te de var: `_find_non_blank` hata atarsa (satır 163-165) `doc` kapanmadan yayılıyor. **Ama:** `doc` yerel değişken; fonksiyon dönünce CPython refcount'u sıfırlar ve MuPDF belleği serbest kalır. Yalnızca bir referans döngüsü oluşursa gecikir. Yani kusur gerçek, kalıcı sızıntı olduğu kanıtlı değil.

**Sonuç: sızıntı kod okuyarak bulunamadı. Çalışma zamanı ölçümü gerekiyor** — ve prod'da belge işleyip reprodüksiyon denemek gerçek kayıt üretir, o yüzden yapılmadı.

### Bunun yerine: bellek kayıtçısı kuruldu ✅

Bir sonraki nöbette tahmin değil veri olsun diye `/usr/local/sbin/mem-watch.sh` + `mem-watch.timer` kuruldu (5 dakikada bir, logrotate'li). Her satırda sistem boş belleği, swap ve altı konteynerin `anon`/`file` değeri. Backend `anon` 1500 MB'ı geçerse `KRITIK` satırı yazıyor — OOM'a saatler varken uyarı verir.

İlk kayıt (2026-07-30 02:21):
```
sys_avail_mb=3027 swap_mb=7 hukdok_backend=87a/37f hukukbot_api=108a/35f
hukudok-postgres=8a/41f hukukbot_db=7a/45f hukdok-frontend-1=2a/7f hukukbot_frontend=2a/7f
```

Sızıntı avının doğru sırası artık şu: bir iş günü veri biriksin → `anon` eğilimini `/var/log/mem-watch.log`'dan oku → hangi saatlerde ne kadar arttığını iş yüküyle eşleştir → o pencerede işlenen belge tipine göre kodu daralt.

Ayrıca boot 0'da (taze açılış, hafif yük, ~50 dk) `Under memory pressure` mesajı **zaten 4 kez** geçmiş. Sağlıklı bir makinede beklenmez; izlenmeli.

### Doğrulanan ama zararsız: üçlü liste yükleme

Planın "loglarda arka arkaya birkaç kez *yenilendi* görülüyor" gözlemi doğrulandı. Her açılışta 2013 müvekkil **üç kez** DB'den yükleniyor (02:29:00.267 / .450 / .564):

1. `ListSearcher.__init__` → `_load_data()`
2. `yenile_matcher()` → `yenile_list_searcher()` → `reload()` → `_load_data()`
3. `refresh_lists_background` sonundaki ek `get_list_searcher()` çağrısı

**Sızıntı değil** — her yükleme `client_map`'i ve `KeywordProcessor`'ı komple değiştiriyor, eskisi GC'ye gidiyor. Sadece boşa iş: her açılışta üç kez 2013 kayıt sorgusu + üç FlashText ağacı kurulumu. Düzeltilmesi kolay ve açılışı hızlandırır, ama OOM'la ilgisi yok — bellek avında bu izi takip etmek zaman kaybı olur.

---

## Madde 7 — Dosya sistemini genişlet · **GEREK KALMADI ✅**

Plan yazıldığında `sda1` 49 GB görünüyordu. Ölçüm (2026-07-30 02:05) artık şunu veriyor:
```
sda      200G
└─sda1   199G   /
df -h /  ->  193G toplam, 19G kullanimda, 175G bos
```
Beklenen alternatif gerçekleşmiş: Ubuntu'nun GCE imajı `01:16`'daki reset sonrası açılışta cloud-init ile bölümü kendiliğinden genişletti. `growpart`/`resize2fs` çalıştırmaya gerek yok.

Yanında ufak bir kazanç:
```bash
docker system prune -f        # ~3.5 GB build cache geri kazanilir
```
**`--volumes` KULLANMA** — veritabanı volume'larını siler.

---

## Madde 8 — Dış IP'yi kalıcı hale getir · **RİSK YOKTU ✅ (2026-07-30 02:55)**

Ölçüm: adres **zaten static.** `gcloud compute addresses describe hukukoid --region europe-west3`:
```yaml
address: 35.234.119.194
addressType: EXTERNAL
name: hukukoid
status: IN_USE
creationTimestamp: '2026-03-29T09:01:55-07:00'
users: [.../instances/instance-20260129-212613]
```
29 Mart'ta ayrılmış. Ephemeral adresler `gcloud compute addresses list` çıktısında **hiç görünmez**; bu adres görünüyor ve `IN_USE`. Yani planın "sessiz risk" olarak işaretlediği tehlike hiç var olmamış — stop/start IP'yi değiştirmez, makine yükseltmesinin önü açık. Yapılacak işlem yok.

<details><summary>Planın orijinal endişesi (referans)</summary>


Dün gece boyunca üzerimizde duran ve henüz doğrulanmamış bir tehlike. `35.234.119.194` **ephemeral (geçici)** ise, VM her stop/start'ta **yeni bir IP alır**. Namecheap'teki DNS eski IP'yi göstermeye devam eder ve site kapalı kalır — üstelik sunucu sapasağlam çalışırken.

Dün üç kez RESET kullandık ve şanslıydık: reset IP'yi korur. Ama **Stop/Start korumaz.** Makine tipi yükseltmesi, display device ekleme gibi işlerin hepsi stop/start gerektiriyor.

**Önce kontrol et:** VPC network → **IP addresses** listesinde `35.234.119.194` satırının **Type** sütunu:
- `Static` → sorun yok, geç
- `Ephemeral` → **hemen kalıcıya çevir:** satırın sağındaki **RESERVE** / "Promote to static" seçeneği

Kesintisiz bir işlem ve kullanılan static IP için ek ücret yok (yalnızca *ayrılmış ama kullanılmayan* IP'ler ücretlendirilir).

Bu madde küçük görünüyor ama sıralamada öndedir: Madde 3'ün SCREENSHOT kısmı ve olası makine yükseltmesi buna bağlı.

</details>

---

## Sıralama

Bağımlılıklara ve kesinti profiline göre:

| Sıra | Madde | Kesinti | Ne zaman | Neden bu sırada |
|---|---|---|---|---|
| 1 | ~~**0 — SSH erişimi**~~ ✅ | Yok | 2026-07-30 · **bitti** | Her iki yol da açık: `ssh hukukoid` (birincil, sudo'suz docker) + `ssh hukukoid-cc` (yedek). Engelleyici kalktı |
| 2 | ~~**7 — Dosya sistemi**~~ ✅ | Yok | kendiliğinden | cloud-init `sda1`'i 199 GB'a genişletmiş, iş kalmadı |
| 3 | **2 — Uptime alert** | Yok | **Hemen** | En yüksek getiri/emek oranı; 5 dakika. Kök neden çözülene kadar tek erken uyarımız |
| 4 | ~~**1 — Ağ nöbetçisi**~~ ✅ | Yok | 2026-07-30 · **kuruldu** | Dünkü 6.5 saatlik arızanın tekrarını engeller. Karar mantığı test edildi; gerçek onarım eylemi ilk arızada sınanacak |
| 5 | **6 — Bellek incelemesi** | Yok | **Hemen** | ⬆️ 9'dan yükseldi. **Üç kesintinin de kök nedeni burada.** Ölçüm beklemeye gerek yok, OOM kanıtı elde |
| 6 | ~~**4 + 5 — Log rotasyonu + limitler**~~ ✅ | **40 sn** | 2026-07-30 02:29 · **bitti** | Limitler OOM'un tüm makineyi götürmesini engelliyor; altı konteynerde doğrulandı |
| 7 | **8 — Static IP kontrolü** | Yok | 5–6'dan önce | ⬇️ Kendi başına acil değil ama makine yükseltmesi stop/start gerektirdiği için onun ön koşulu |
| 8 | **5 — Makine yükseltmesi** (4 → 8 GB) | stop/start | 8'den sonra | ⬆️ "Değerlendirilir"den ciddi adaya yükseldi: 3.8 GB'da OOM zaten gerçekleşti |
| 9 | **3 — Seri konsol** | Yok | Sonra | ⬇️ Faydalı ama kök nedene dokunmuyor |

**Sıralama değişti.** İlk hâli disk teşhisine dayanıyordu ve bellek işlerini (5, 6) en sona koymuştu. Teşhis revizyonundan sonra öncelik şu: önce **haberdar ol** (Madde 2), sonra **kök nedeni bul** (Madde 6), sonra **hasarı sınırla** (Madde 4+5), sonra **kapasiteyi büyüt** (makine yükseltmesi).

Madde 2 ve 6 kesintisiz, hemen yapılabilir. Madde 4+5 akşam penceresi, makine yükseltmesi ise static IP doğrulaması olmadan yapılmamalı.

## Doğrulama

Her madde bittiğinde tek tek kanıtlanmalı — "yapıldı" yetmez:

1. **Madde 0:** ✅ **Doğrulandı (2026-07-30).** `ssh hukukoid` → `luciferandlucius`, `docker ps` 6 konteyner (sudo'suz), `~/hukdok` ve `~/hukukbot-ui` erişilebilir. `ssh hukukoid-cc` → `claude-code`, `sudo docker ps` 6 konteyner. Metadata'daki dört satırın hepsi geçerli, çift önekli satır silindi, `authorized_keys` dosyalarını agent'ın kendisi yazdı.
2. **Madde 8:** IP addresses listesinde Type = `Static`.
3. **Madde 2:** uptime check'i kasten başarısız kıl (host adını geçici olarak bozarak) → e-posta geldiğini gör. Test edilmemiş alert, alert değildir.
4. **Madde 1:** ✅ **Kısmen doğrulandı (2026-07-30).** Timer `enabled`+`active`, 60 sn'de bir tetikleniyor, koşular `Result=success`, sağlıklı ağda log yazmıyor. Karar mantığının dört dalı (bozuk ağ / sağlıklı ağ / toparlanma / bozuk state) stub'lı test kopyasıyla kanıtlandı. **Eksik:** gerçek DHCP kaybında `networkctl reconfigure`'ün onardığının kanıtı — ağı kasten bozmak gerektiği için yapılmadı. Rota silme testi zaten geçersiz (bkz. Madde 1 → Doğrulama).
5. **Madde 3:** "Connect to serial console" butonu artık aktif ve terminal açılıyor.
6. **Madde 7:** `df -h /` ~197 GB gösteriyor.
7. **Madde 4:** recreate sonrası `docker inspect <konteyner> --format '{{.HostConfig.LogConfig}}'` → `max-size:50m` görünüyor.
8. **Madde 5:** `docker inspect <konteyner> --format '{{.HostConfig.Memory}}'` → 0'dan farklı; ardından **normal iş yükü altında bir gün izle**, OOM kill olmadığını doğrula (`docker inspect --format '{{.State.OOMKilled}}'`).

## Kapsam dışı

Bilinçli olarak bu plana alınmayanlar:
- **Yedeklilik / ikinci sunucu** — tek makine mimarisi duruyor. Bu, kesinti süresini kısaltmaz, ortadan kaldırır; ama ayrı bir tasarım işi ve maliyeti farklı bir mertebede.
- **Otomatik reset** — bir arıza durumunda VM'i kendiliğinden reset'leyen mekanizma. Cazip ama tehlikeli: yanlış pozitifte veri kaybı riski taşır. Nöbetçi + alert bu ihtiyacın büyük kısmını karşılıyor.
- **Belge dönüşümünü ayrı bir işçiye taşımak** — ağır işi ana API sürecinden ayırmak mimari olarak doğru yön, ama otonom dava açma planıyla birlikte değerlendirilmeli.
