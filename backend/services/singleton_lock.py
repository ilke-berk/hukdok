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

# Süreç yaşadıkça açık kalmalı: GC handle'ı kapatırsa kilit düşer.
_handle: Optional[IO[bytes]] = None


def _try_lock_file(path: Path) -> Optional[IO[bytes]]:
    """Dosyayı non-blocking kilitlemeyi dener; başarıda açık handle döner.

    Handle çağıranda YAŞAMALI — kapanırsa kilit bırakılır. Test edilebilirlik
    için modül global'inden ayrık tutuldu.
    """
    fh: Optional[IO[bytes]] = None
    try:
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
    except OSError as e:
        # Kilit dosyası açılamadı (izin/disk) — lider seçimi yapılamıyor.
        # None döndürmek İKİ worker'da da "lider değil" demek olurdu ve
        # arkaplan işleri hiç koşmazdı; güvenli taraf "lider varsay"dır:
        # en kötü durum bugünkü (tekli) davranışın N kopyası.
        if fh is not None:
            try:
                fh.close()
            except OSError:
                pass
        logger.warning(f"Lider kilidi dosyası açılamadı ({path}): {e} — lider varsayılıyor")
        return open(os.devnull, "rb")


def try_acquire_leader() -> bool:
    """Bu süreci lider yapmayı dener (idempotent; handle süreçte tutulur).

    True → süreç-tekil arkaplan işleri bu worker'da başlamalı.
    """
    global _handle
    if _handle is not None:
        return True
    fh = _try_lock_file(Path(tempfile.gettempdir()) / _LOCK_FILE_NAME)
    if fh is None:
        return False
    _handle = fh
    return True
