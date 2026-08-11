"""Worker süreçleri arasında "tek koşucu" (lider) seçimi (Faz 3-E).

uvicorn --workers N her worker sürecinde lifespan'i AYRI koşar; süreç-tekil
kalması gereken arkaplan işleri — APScheduler günlük raporu, catch-up
thread'i, upload-outbox worker'ı — yalnız kilidi alan worker'da başlar
(yoksa aynı outbox satırı N kez yüklenir, günlük rapor N kez üretilir).

Mekanizma: dosya kilidi (flock LOCK_EX | LOCK_NB). Kilit süreç yaşadıkça
tutulur; süreç ölünce çekirdek kilidi bırakır → uvicorn'un yeniden doğurduğu
worker kendi lifespan'inde kilidi devralır (kendi kendini onarır — liderlik
sabit bir worker'a bağlı değildir).

Dosya konteyner-YEREL dizindedir (tempfile.gettempdir()): volume'e bilerek
KONMAZ — kilit süreç yaşamına bağlıdır, konteynerler/restart'lar arası anlam
taşımaz. Ad, api.py'deki KVKK temp süpürgesinin desenlerine (tmp*.pdf vb.)
uymaz; süpürülmez.

Yol adayları sırayla denenir (_lock_path_candidates): birincil gettempdir(),
sonra sabit yedekler (/dev/shm, /var/tmp — konteyner-yerel, tüm worker'larda
AYNI mutlak yol; yol worker'a göre değişseydi lider seçimi bölünürdü).
Yedeklerin gerekçesi: birincil yol izin/disk/read-only arızasıyla AÇILAMAZSA
kilit hiç kurulamaz ve fail-open yüzünden her worker lider olur (günlük rapor
e-postası N kopya). "Kilit başkasında" ile "yol kullanılamıyor" ayrı şeylerdir:
ilkinde bu worker lider DEĞİLdir ve sonraki aday DENENMEZ (yoksa aynı anda iki
lider çıkar), yalnız ikincisinde sıradaki adaya geçilir.

Hiçbir aday açılamazsa davranış fail-open kalır (arıza günü arkaplan işleri
tamamen durmasın — bilinçli takas) ama SESSİZ değildir: tek satır CRITICAL
basılır (izlemenin hata-oranı alarmı yakalasın). Bu bir deneme-düzeyi hata
değil, nihai bir arıza bildirimidir; log sözleşmesiyle uyumludur.

fcntl yoksa (Windows host-run) msvcrt.locking denenir; ikisi de yoksa tek
süreç varsayılır ve True dönülür (python api.py zaten tek worker'dır).

ÖNEMLİ: dosya lifespan sırasında (fork/spawn SONRASI) açılır. Import
zamanında açılsaydı fork'ta çocuklar aynı open-file-description'ı paylaşır,
flock hepsinde "alınmış" görünür ve hepsi lider olurdu.
"""
import logging
import os
import tempfile
from pathlib import Path
from typing import IO, Optional

logger = logging.getLogger(__name__)

_LOCK_FILE_NAME = "hukdok-worker-leader.lock"

# Birincil yol açılamazsa denenecek sabit dizinler. İkisi de konteyner-yerel ve
# sticky-yazılabilir (1777) tmpfs/disk: TMPDIR bozuk ya da /tmp read-only/dolu
# olduğunda ikinci şans verirler.
_FALLBACK_LOCK_DIRS = ("/dev/shm", "/var/tmp")

# Süreç yaşadıkça açık kalmalı: GC handle'ı kapatırsa kilit düşer.
_handle: Optional[IO[bytes]] = None


def _lock_path_candidates() -> list[Path]:
    """Kilit dosyası için sırayla denenecek yollar (birincil önce).

    Aynı dizin iki kez denenmez: POSIX'te TMPDIR yokken gettempdir() zaten
    "/tmp"dir; yedeklerin ondan FARKLI olması yedek olmalarının şartıdır.
    """
    paths = [Path(tempfile.gettempdir()) / _LOCK_FILE_NAME]
    for directory in _FALLBACK_LOCK_DIRS:
        candidate = Path(directory) / _LOCK_FILE_NAME
        if candidate not in paths:
            paths.append(candidate)
    return paths


def _try_lock_file(path: Path) -> Optional[IO[bytes]]:
    """Dosyayı non-blocking kilitlemeyi dener; başarıda açık handle döner.

    None → dosya açıldı ama kilit BAŞKA süreçte (bu worker lider değil).
    Dosya hiç açılamazsa OSError yukarı fırlar; "yol kullanılamıyor" ile "kilit
    başkasında" karışmasın diye burada yutulmaz — aday sırasını çağıran yürütür.

    Handle çağıranda YAŞAMALI — kapanırsa kilit bırakılır. Test edilebilirlik
    için modül global'inden ayrık tutuldu.
    """
    fh = open(path, "a+b")
    try:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fh
    except ImportError:
        pass  # Windows — msvcrt'ye düş
    except OSError:
        fh.close()
        return None

    try:
        import msvcrt
        # locking bölge tabanlıdır; dosya boş olsa da 1 baytlık bölge
        # kilitlenebilir. Konum başa alınır ki iki süreç aynı bölgeyi yarışsın.
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        return fh
    except ImportError:
        # Ne fcntl ne msvcrt (beklenmez) — tek süreç varsay, kilitsiz kabul.
        return fh
    except OSError:
        fh.close()
        return None


def try_acquire_leader() -> bool:
    """Bu süreci lider yapmayı dener (idempotent; handle süreçte tutulur).

    True → süreç-tekil arkaplan işleri bu worker'da başlamalı.
    """
    global _handle
    if _handle is not None:
        return True
    for path in _lock_path_candidates():
        try:
            fh = _try_lock_file(path)
        except OSError as e:
            # Yol kullanılamıyor (izin/disk/read-only) — deneme-düzeyi hata: WARNING.
            logger.warning(f"Lider kilidi yolu kullanılamıyor ({path}): {e} — sıradaki aday deneniyor")
            continue
        if fh is None:
            return False  # yol çalışıyor, kilit başka worker'da
        _handle = fh
        return True

    # Hiçbir aday açılamadı — lider seçimi yapılamıyor. None dönmek İKİ worker'da
    # da "lider değil" demek olurdu ve arkaplan işleri hiç koşmazdı; güvenli taraf
    # "lider varsay"dır: en kötü durum tekli davranışın N kopyası. Sessiz kalmaz —
    # nihai arıza bildirimi olarak TEK satır CRITICAL.
    logger.critical(
        "Lider kilidi hiçbir yolda kurulamadı — her worker lider varsayıyor; "
        "süreç-tekil işler (günlük rapor, upload outbox) MÜKERRER koşabilir"
    )
    try:
        # Handle'ı yine de tut: aynı süreçte her çağrıda yeniden denenip CRITICAL
        # tekrarlanmasın (idempotency sözleşmesi).
        _handle = open(os.devnull, "rb")
    except OSError:
        pass
    return True
