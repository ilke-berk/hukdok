import os
import threading
import requests
import logging
from urllib.parse import urlparse, quote
from dotenv import load_dotenv
from pathlib import Path
from functools import lru_cache

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from sharepoint.auth_graph import get_graph_token

GRAPH = "https://graph.microsoft.com/v1.0"
logger = logging.getLogger("SharePointUploader")

# ── Faz 3-B: paylaşılan Session + transport-katmanı retry ────────────────────
# İki katmanlı retry mimarisi:
#   İÇ katman (bu modül, saniyeler): urllib3.Retry — 429/5xx ve bağlantı
#     hatalarında aynı yükleme denemesi içinde kısa tekrarlar (backoff 1-2-4 sn).
#   DIŞ katman (services/upload_queue.py, dakika-saat): outbox backoff, MAX 8.
# Outbox worker'ı tek thread ve satırları seri işlediği için iç bütçe bilerek
# küçük tutuldu; uzun kesintiyi dış katman karşılar.
#
# DİKKAT: Retry PUT/POST/PATCH'i de kapsar — bu modüldeki çağrılar idempotent
# (içerik PUT'u ve createUploadSession conflictBehavior=replace, metadata PATCH
# alan set'i) olduğu için güvenli. sendMail / SharePoint liste-item POST'u gibi
# idempotent OLMAYAN Graph çağrıları bu session'ı KULLANMAMALI (çift e-posta /
# çift kayıt riski) — onlar kendi modüllerinde düz requests ile kalır.
_RETRY_STATUS_CODES = (429, 500, 502, 503, 504)
_SMALL_FILE_LIMIT = 4 * 1024 * 1024  # altında tek PUT, üstünde chunk'lı upload session
_CHUNK_SIZE = 5 * 1024 * 1024  # 5 MiB = 16 × 320 KiB (Graph parça hizalama kuralı)
_CHUNK_RESUME_BUDGET = 3  # yükleme başına nextExpectedRanges ile devam hakkı

_session_lock = threading.Lock()
_shared_session: requests.Session | None = None


def _load_env():
    import sys
    if getattr(sys, 'frozen', False):
        env_path = Path(sys.executable).parent / ".env"
    else:
        env_path = Path(__file__).resolve().parent.parent / ".env"

    load_dotenv(dotenv_path=env_path, override=True)


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def get_ssl_verify_option():
    """Returns the SSL verification option (path to cert or True/False)."""
    ssl_cert = os.getenv("SSL_CERT_FILE")
    if ssl_cert and os.path.exists(ssl_cert):
        return ssl_cert
    return True


def _build_retry() -> Retry:
    return Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=list(_RETRY_STATUS_CODES),
        # urllib3 2.x varsayılanı idempotent-güvenli küçük kümedir (PUT/POST/
        # PATCH YOK) — açıkça izin verilmezse upload'lar hiç retry görmezdi.
        allowed_methods=frozenset({"GET", "HEAD", "PUT", "POST", "PATCH"}),
        # 429/503'te Graph'ın Retry-After başlığına uy (throttling sözleşmesi)
        respect_retry_after_header=True,
    )


def _build_session() -> requests.Session:
    session = requests.Session()
    session.verify = get_ssl_verify_option()
    adapter = HTTPAdapter(max_retries=_build_retry())
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _get_shared_session() -> requests.Session:
    """Süreç-tekil session: bağlantı havuzu (TLS el sıkışması) yeniden
    kullanılır, retry politikası tek yerde tanımlıdır. Kurulduktan sonra
    üzerinde state değiştirilmez — header'lar istek başına verilir; urllib3
    bağlantı havuzu thread-safe olduğundan thread'ler arası paylaşım güvenli.
    verify seçeneği ilk kullanımda donar: SSL_CERT_FILE süreç başında bellidir
    (compose env), çalışırken değişmez.
    """
    global _shared_session
    if _shared_session is None:
        with _session_lock:
            if _shared_session is None:
                _load_env()  # get_ssl_verify_option SSL_CERT_FILE env'ine bakar
                _shared_session = _build_session()
    return _shared_session


def _with_fresh_token_on_401(fn):
    """fn(token) çağrısını yapar; ilk 401'de token'ı ZORLA yenileyip bir kez
    daha dener. 401 transport retry'ına bırakılamaz: aynı Authorization
    başlığıyla tekrar denemek sonucu değiştirmez — MSAL cache'indeki token
    süresi dolmadan sunucuda geçersizleşmiş olabilir (secret rotasyonu, revoke).
    """
    token = get_graph_token(config_type="default")
    try:
        return fn(token)
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        if status != 401:
            raise
        logger.warning("Graph 401 döndü — token zorla yenilenip bir kez daha denenecek")
        token = get_graph_token(config_type="default", force_refresh=True)
        return fn(token)


@lru_cache(maxsize=1)
def _get_site_and_drive_id(token: str, config_type: str = "default") -> tuple[str, str]:
    """Site ve drive ID çözümü.

    lru_cache anahtarının token olması BİLİNÇLİ (Faz 3-B'de korundu): token
    ~saatte bir döndüğünde kayıt kendiliğinden tazelenir (bedava TTL) ve 401
    sonrası zorla yenilenen token yeni cache anahtarı üretip ID'leri yeni
    token'la yeniden çözer. Ayrı bir TTL cache aynı davranışa fazladan kod olurdu.
    """
    _load_env()
    session = _get_shared_session()

    # Always use the main SHAREPOINT_SITE_URL (Single-Site Mode)
    site_url = os.getenv("SHAREPOINT_SITE_URL")

    if config_type == "upload":
        logger.debug("Uploader: Using main site for upload (config='upload' -> default site).")

    drive_name = os.getenv(
        "SP_DRIVE_NAME", "Belgeler"
    )  # Default to "Belgeler" (Documents)

    if not site_url:
        raise RuntimeError(f"Missing env: SHAREPOINT_SITE_URL (config: {config_type})")

    u = urlparse(site_url)
    hostname = u.netloc
    site_path = u.path if u.path else "/"

    # 1. Get Site ID
    logger.debug(f"Fetching Site ID for {hostname} ({config_type})")
    r = session.get(
        f"{GRAPH}/sites/{hostname}:{site_path}", headers=_headers(token), timeout=(10, 60)
    )
    r.raise_for_status()
    site_id = r.json()["id"]

    # 2. Get Drives (Document Libraries)
    logger.debug(f"Fetching Drives for Site ID: {site_id}")
    r = session.get(
        f"{GRAPH}/sites/{site_id}/drives", headers=_headers(token), timeout=(10, 60)
    )
    r.raise_for_status()
    drives = r.json().get("value", [])
    if not drives:
        raise RuntimeError("No drives found on SharePoint site.")

    # 3. Find specific Drive (e.g. "Belgeler")
    for d in drives:
        # Check both 'name' (internal) and decoded name just in case
        if d.get("name") == drive_name or d.get("name") == "Documents":
            # Note: "Belgeler" usually maps to "Documents" (internal name) in some tenants, or stays localized.
            # We search for the drive name specified in ENV or fallback to checking the list.
            return site_id, d["id"]

    # If explicit name not found, try searching loosely or fallback
    names = [d.get("name") for d in drives]

    # Fallback: If drive_name is "Belgeler" but not found, look for "Documents"
    if drive_name == "Belgeler" and "Documents" in names:
        for d in drives:
            if d.get("name") == "Documents":
                return site_id, d["id"]

    raise RuntimeError(f"Drive '{drive_name}' not found. Available: {names}")


def _create_upload_session(
    session: requests.Session,
    token: str,
    drive_id: str,
    filename: str,
    folder_name: str,
) -> str:
    # Pattern: /drives/{id}/root:/{folder}/{filename}:/createUploadSession
    path = quote(f"{folder_name}/{filename}")
    url = f"{GRAPH}/drives/{drive_id}/root:/{path}:/createUploadSession"

    body = {"item": {"@microsoft.graph.conflictBehavior": "replace", "name": filename}}
    r = session.post(
        url,
        headers=_headers(token) | {"Content-Type": "application/json"},
        json=body,
        timeout=(10, 60),
    )
    r.raise_for_status()
    return r.json()["uploadUrl"]


def _next_expected_start(session: requests.Session, upload_url: str) -> int:
    """Upload session durumunu sorgular, sunucunun beklediği ofseti döndürür.

    uploadUrl ön-yetkilidir; chunk PUT'ları gibi durum sorgusu da Authorization
    başlığı taşımaz. nextExpectedRanges boşsa oturum sunucuda çoktan
    tamamlanmış demektir — çağıran nihai hataya düşer, dış katman baştan
    yükler (conflictBehavior=replace bunu güvenli kılar).
    """
    r = session.get(upload_url, timeout=(10, 60))
    r.raise_for_status()
    ranges = r.json().get("nextExpectedRanges") or []
    if not ranges:
        raise RuntimeError("Upload session durumunda nextExpectedRanges yok")
    return int(str(ranges[0]).split("-", 1)[0])


def _resume_offset(
    session: requests.Session,
    upload_url: str,
    target_filename: str,
    cause: Exception,
    resume_left: int,
) -> int:
    """Chunk hatasında devam ofsetini bulur.

    Bütçe bittiyse ya da durum sorgusu da düşerse nihai hata fırlatır; upload'ı
    baştan başlatmak bu katmanın işi değil (dış katman outbox'ı zaten yeniden
    dener). 45 MB'lık dosya tek ağ hıçkırığında sıfırdan başlamasın diye var.
    """
    if resume_left <= 0:
        raise RuntimeError(f"Chunk resume bütçesi tükendi; son hata: {cause}") from cause
    try:
        next_start = _next_expected_start(session, upload_url)
    except Exception as status_err:
        raise RuntimeError(
            f"Chunk hatası sonrası durum sorgusu da başarısız ({status_err}); ilk hata: {cause}"
        ) from status_err
    logger.warning(
        f"Chunk hatası ({cause}); {target_filename} yüklemesi {next_start}. bayttan sürdürülüyor"
    )
    return next_start


def _upload_chunks(
    session: requests.Session,
    upload_url: str,
    filepath: str,
    file_size: int,
    target_filename: str,
) -> dict:
    """Dosyayı upload session'a parça parça gönderir; hatada kaldığı yerden devam.

    Chunk gövdesi bytes (bellekte en çok _CHUNK_SIZE) — transport retry parçayı
    güvenle yeniden gönderebilir (stream olsaydı ikinci deneme boş giderdi).
    Parça tüm iç retry'lara rağmen düşerse nextExpectedRanges sorgulanıp o
    ofsetten sürülür (_CHUNK_RESUME_BUDGET kez).
    """
    start = 0
    resume_left = _CHUNK_RESUME_BUDGET
    with open(filepath, "rb") as f:
        while start < file_size:
            f.seek(start)
            chunk = f.read(_CHUNK_SIZE)
            if not chunk:
                raise RuntimeError(f"Dosya beklenenden kısa: {start}/{file_size} ({filepath})")

            length = len(chunk)
            end = start + length - 1
            headers = {
                "Content-Length": str(length),
                "Content-Range": f"bytes {start}-{end}/{file_size}",
            }

            try:
                # Chunk'ı gönder (Session Reuse; uploadUrl ön-yetkili, auth başlığı yok)
                r = session.put(upload_url, headers=headers, data=chunk, timeout=(10, 300))
            except requests.RequestException as e:
                start = _resume_offset(session, upload_url, target_filename, e, resume_left)
                resume_left -= 1
                continue

            if r.status_code in (200, 201):
                logger.info(f"✅ Upload Tamamlandı: {target_filename}")
                return r.json()

            if r.status_code == 202:
                # Parça kabul edildi; sıradaki ofsette otorite sunucunun yanıtı.
                try:
                    ranges = r.json().get("nextExpectedRanges") or []
                except ValueError:
                    ranges = []
                new_start = int(str(ranges[0]).split("-", 1)[0]) if ranges else end + 1
                if new_start <= start:
                    # 202 ilerleme demektir; ilerlemiyorsa sonsuz döngüye girme.
                    raise RuntimeError(
                        f"Upload ilerlemiyor (202 sonrası ofset {new_start} <= {start}): {target_filename}"
                    )
                start = new_start
                continue

            if r.status_code == 416:
                # Aralık zaten sunucuda (timeout sonrası yinelenen gönderim) —
                # gerçek ofseti sorup hizalan.
                cause = RuntimeError(f"416 invalidRange: {r.text[:200]}")
                start = _resume_offset(session, upload_url, target_filename, cause, resume_left)
                resume_left -= 1
                continue

            # Transport retry'ının ele almadığı durumlar (4xx vb.) nihaidir
            raise RuntimeError(f"Upload chunk failed: {r.status_code} {r.text}")

    raise RuntimeError("Upload session finished without 200/201 response.")


def _upload_with_token(
    session: requests.Session,
    token: str,
    filepath: str,
    target_filename: str,
    target_folder_name: str,
    content_type: str,
    metadata: "dict | None",
) -> dict:
    """Tek token'la tam yükleme akışı: ID çözümü → küçük PUT ya da chunk'lı yol."""
    # _get_site_and_drive_id is now Cached
    _site_id, drive_id = _get_site_and_drive_id(token, config_type="default")

    file_size = os.path.getsize(filepath)

    # --- SMALL FILE UPLOAD (< 4MB) ---
    if file_size < _SMALL_FILE_LIMIT:
        safe_path = quote(f"{target_folder_name}/{target_filename}")
        upload_url = f"{GRAPH}/drives/{drive_id}/root:/{safe_path}:/content"

        # Gövde BİLEREK belleğe okunur (üst sınır _SMALL_FILE_LIMIT): data=<dosya>
        # stream'i transport retry'ında geri sarılamaz, ikinci deneme boş gövde
        # gönderirdi. Büyük dosyalar chunk yoluna gider — bu okuma sınırsız değil.
        with open(filepath, "rb") as f:
            body = f.read()
        r = session.put(
            upload_url,
            headers=_headers(token) | {"Content-Type": content_type},
            data=body,
            timeout=(10, 180),
        )
        r.raise_for_status()
        data = r.json()
    else:
        # --- LARGE FILE UPLOAD (> 4MB) ---
        logger.info(f"📦 Büyük Dosya Modu (>4MB) - Chunk Upload: {target_filename}")
        upload_url = _create_upload_session(
            session, token, drive_id, target_filename, target_folder_name
        )
        data = _upload_chunks(session, upload_url, filepath, file_size, target_filename)

    if metadata:
        _update_list_item_fields(session, token, drive_id, data["id"], metadata)
    return data


def upload_file_to_sharepoint(
    filepath: str,
    target_filename: str,
    target_folder_name: str,
    content_type: str = "application/pdf",
    use_date_subfolder: bool = False,
    metadata: dict = None,
) -> dict:
    """
    SharePoint'e Graph ile upload (Secure Cloud Archive Mode).
    Uses 'upload' configuration (New Site).

    Args:
        filepath: Yüklenecek dosyanın yerel yolu
        target_filename: SharePoint'teki dosya adı
        target_folder_name: Hedef klasör adı (örn: "01_HAM_ARSIV")
        content_type: MIME type
        use_date_subfolder: True ise YYYY-MM-DD formatında alt klasör oluşturur

    Returns:
        SharePoint API response

    Faz 3-B: paylaşılan session'ın transport retry'ı (429/5xx/bağlantı) + ilk
    401'de bir kez zorla token yenileme + chunk'lı yolda nextExpectedRanges ile
    kaldığı yerden devam. Nihai başarısızlıkta exception fırlatır; ERROR
    loglamak çağıran katmanın işidir (upload_queue nihai failed / async_*
    fallback) — buradaki log deneme başına WARNING'dir (alarm sözleşmesi).
    """
    # Tarih bazlı alt klasör oluştur
    if use_date_subfolder:
        from datetime import datetime
        date_folder = datetime.now().strftime("%Y-%m-%d")
        target_folder_name = f"{target_folder_name}/{date_folder}"
        logger.info(f"📅 Tarih klasörü kullanılıyor: {target_folder_name}")

    session = _get_shared_session()
    try:
        return _with_fresh_token_on_401(
            lambda token: _upload_with_token(
                session,
                token,
                filepath,
                target_filename,
                target_folder_name,
                content_type,
                metadata,
            )
        )
    except Exception as e:
        logger.warning(f"SharePoint Upload Error: {e}")
        raise


def download_file_from_sharepoint(folder_name: str, filename: str) -> tuple[bytes, str]:
    """
    SharePoint'ten dosya içeriğini ve MIME tipini döndürür.
    Kimlik doğrulama backend service account üzerinden yapılır;
    son kullanıcının Microsoft tenant üyesi olması gerekmez.
    """
    _load_env()
    session = _get_shared_session()
    safe_path = quote(f"{folder_name}/{filename}")

    def _download(token: str) -> tuple[bytes, str]:
        _site_id, drive_id = _get_site_and_drive_id(token, config_type="default")
        url = f"{GRAPH}/drives/{drive_id}/root:/{safe_path}:/content"
        r = session.get(url, headers=_headers(token), timeout=(10, 120), allow_redirects=True)
        r.raise_for_status()
        content_type = r.headers.get("Content-Type", "application/octet-stream")
        return r.content, content_type

    return _with_fresh_token_on_401(_download)


#: Klasör listelemede sayfa boyu (`$top`); Graph tavanı 200'dür.
_LIST_PAGE_SIZE = 200
#: Listelemede istenen alanlar — gözcü (G109) yalnız bunlara bakar.
_LIST_SELECT = "id,name,size,eTag,file,lastModifiedDateTime"


def list_folder_children(folder_name: str) -> list[dict]:
    """Klasördeki DOSYALARI listeler (G109 SharePoint teslim gözcüsü).

    `GET /drives/{drive}/root:/{folder}:/children?$select=…&$top=200`;
    `@odata.nextLink` sonuna kadar izlenir, sayfalar tek listede birleşir.
    Yalnız `file` anahtarı taşıyan öğeler döner (alt klasörler elenir).

    Klasör yoksa (404) **boş liste + WARNING**: gece job'ı "klasör henüz
    açılmadı" diye ERROR basmasın — o bir kurulum eksiği, arıza değil. Diğer
    HTTP hataları yükselir (transport retry ortak session'da; ilk 401'de token
    zorla yenilenip bir kez daha denenir — `_with_fresh_token_on_401`).
    Deneme düzeyi log WARNING'dir; nihai ERROR çağıranın işidir (log sözleşmesi).
    """
    _load_env()
    session = _get_shared_session()
    safe_path = quote(folder_name)

    def _list(token: str) -> list[dict]:
        _site_id, drive_id = _get_site_and_drive_id(token, config_type="default")
        url: str | None = f"{GRAPH}/drives/{drive_id}/root:/{safe_path}:/children"
        params: dict | None = {"$select": _LIST_SELECT, "$top": _LIST_PAGE_SIZE}
        items: list[dict] = []
        while url:
            r = session.get(url, headers=_headers(token), params=params, timeout=(10, 60))
            if r.status_code == 404:
                logger.warning(f"SharePoint klasörü bulunamadı, boş liste dönüyor: {folder_name}")
                return []
            r.raise_for_status()
            data = r.json()
            items.extend(item for item in data.get("value", []) if "file" in item)
            url = data.get("@odata.nextLink")
            params = None  # nextLink sorgu parametrelerini kendi taşır
        return items

    return _with_fresh_token_on_401(_list)


def _update_list_item_fields(session, token, drive_id, item_id, fields):
    """Updates the ListItem fields for a given DriveItem."""
    logger.info(f"📝 Metadata Güncelleniyor: {fields}")
    url = f"{GRAPH}/drives/{drive_id}/items/{item_id}/listItem/fields"

    r = session.patch(
        url,
        headers=_headers(token) | {"Content-Type": "application/json"},
        json=fields,
        timeout=(10, 30)
    )
    if r.status_code != 200:
        # Bilinçli soft-fail (upload'ı düşürmez) → nihai değil, WARNING yeter
        logger.warning(f"⚠️ Metadata update failed: {r.text}")
    else:
        logger.info("✅ Metadata başarıyla işlendi.")
