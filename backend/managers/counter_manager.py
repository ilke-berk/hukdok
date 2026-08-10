"""
SharePoint Counter Manager - Multi-User Safe Counter System

Bu modül SharePoint List kullanarak merkezi, atomic counter yönetimi sağlar.
Race condition'ları ETag ve optimistic concurrency ile önler.

Faz 3-D (plan 3.4) — atomik tahsis: numara verme işlemi artık tek adımdır.
reserve_next_counter() mevcut değeri okur, ETag/If-Match ile +1 yazar ve
OKUNAN değeri döndürür. Eski akışta /process sadece okuyor, artırma /confirm
arka planında yapılıyordu — iki eşzamanlı kullanıcı dakikalarca açık kalan
pencerede AYNI numarayı görüyordu. Yan etki: analiz edilip onaylanmayan
belgeler artık bir numara "yakar" (boşluk) — mükerrer numaraya tercih edilir
(eski akış da /confirm başına koşulsuz artırdığından boşluklar zaten vardı).

Transport katmanı Faz 3-B'nin paylaşılan Session'ıdır (urllib3.Retry):
- GET'ler idempotent → 429/5xx transient hatalarında bedava retry.
- If-Match'li PATCH retry altında GÜVENLİ (koddan doğrulandı, 3-D):
  Retry'ın status_forcelist'i 412'yi İÇERMEZ; ilk deneme sunucuda işlenip
  yanıt kaybolursa transport tekrarı bayat ETag'le 412 alır ve çakışma
  yoluna düşer → yeni değer okunur, tahsis TAZE numarayla tekrarlanır.
  En kötü durum bir numaranın atlanmasıdır; iki kullanıcıya aynı numara
  verilmez, sayaç geri gitmez.
"""

import os
import random
import threading
import time
import logging
from datetime import datetime

import requests

from sharepoint.auth_graph import get_graph_token
from sharepoint.sharepoint_uploader_graph import _get_site_and_drive_id, _headers
from managers.log_manager import TechnicalLogger

GRAPH = "https://graph.microsoft.com/v1.0"
COUNTER_LIST_NAME = os.getenv("SHAREPOINT_COUNTER_LIST_NAME", "Counter")

# ETag çakışmasında (412) deneme sayısı ve backoff. Eski increment_counter
# döngüsü backoff'suz anında tekrar deniyordu — çakışan iki istemci aynı anda
# tekrar okuyup yeniden çarpışabiliyordu; jitter'lı üstel bekleme bunu kırar.
# /process tarafındaki 10 sn'lik bekleme bütçesine sığacak şekilde sınırlı:
# en kötü toplam uyku ~0.3+0.6+1.2 (+jitter) ≈ 2.5 sn + HTTP tur süreleri.
RESERVE_MAX_ATTEMPTS = 4
_CONFLICT_BACKOFF_BASE_SECONDS = 0.3
_CONFLICT_BACKOFF_CAP_SECONDS = 2.0
_CONFLICT_BACKOFF_JITTER_SECONDS = 0.2

logger = logging.getLogger("SharePointCounterManager")


def _get_session() -> requests.Session:
    """Faz 3-B paylaşılan Session'ı (retry politikası + bağlantı havuzu).

    Dolaylama testler için: sahte session monkeypatch ile buradan verilir.
    """
    from sharepoint.sharepoint_uploader_graph import _get_shared_session
    return _get_shared_session()


class SharePointCounterManager:
    """
    SharePoint List tabanlı multi-user-safe counter.

    Özellikler:
    - Atomik tahsis: oku + artır + döndür tek işlemde (reserve_next_counter)
    - Atomic increment (ETag + optimistic concurrency, jitter'lı backoff)
    - Merkezi (tüm kullanıcılar aynı counter'ı kullanır)
    - No fallback (SharePoint offline ise hata fırlatır)
    """

    def __init__(self):
        self.list_name = COUNTER_LIST_NAME
        self._field_map_cache = None  # Field mapping cache
        self._list_id_cache = None    # Liste kimliği değişmez; her tahsiste yeniden aramaya gerek yok

    def _reset_caches(self):
        """Liste silinip yeniden oluşturulursa 404'e saplanmamak için:
        412-dışı her hatada cache'ler düşer, sonraki çağrı yeniden çözer."""
        self._field_map_cache = None
        self._list_id_cache = None

    def _get_list_id(self, token: str, site_id: str) -> str:
        """Counter list'in ID'sini bul (bulamazsa raise eder, None dönmez)"""
        if self._list_id_cache:
            return self._list_id_cache
        try:
            url = f"{GRAPH}/sites/{site_id}/lists"
            r = _get_session().get(url, headers=_headers(token), timeout=30)
            r.raise_for_status()

            lists = r.json().get("value", [])
            for lst in lists:
                if lst.get("displayName") == self.list_name or lst.get("name") == self.list_name:
                    self._list_id_cache = lst["id"]
                    return lst["id"]

            raise Exception(f"Counter list '{self.list_name}' bulunamadı!")
        except Exception as e:
            logger.error(f"List ID alma hatası: {e}")
            raise

    def _detect_field_mapping(self, token: str, site_id: str, list_id: str) -> dict:
        """
        SharePoint kolonlarının internal name'lerini tespit et.

        Returns:
            {
                "Current_Count": "field_1",
                "Last_Updated": "field_2",
                "Updated_By": "field_3"
            }
        """
        if self._field_map_cache:
            return self._field_map_cache

        try:
            url = f"{GRAPH}/sites/{site_id}/lists/{list_id}/columns"
            r = _get_session().get(url, headers=_headers(token), timeout=30)
            r.raise_for_status()

            columns = r.json().get("value", [])
            field_map = {}

            target_columns = ["Current_Count", "Last_Updated", "Updated_By"]
            for col in columns:
                display_name = col.get("displayName", "")
                internal_name = col.get("name", "")

                if display_name in target_columns:
                    field_map[display_name] = internal_name

            # Cache it
            self._field_map_cache = field_map
            logger.info(f"Field mapping tespit edildi: {field_map}")
            return field_map

        except Exception as e:
            logger.error(f"Field mapping hatası: {e}")
            raise

    def _get_counter_item(self, token: str, site_id: str, list_id: str) -> dict:
        """
        Counter item'ı al (ilk ve tek item).

        Returns:
            {
                "id": "1",
                "eTag": "...",
                "fields": {
                    "field_1": 42  # Current_Count
                }
            }
        """
        try:
            url = f"{GRAPH}/sites/{site_id}/lists/{list_id}/items?$expand=fields&$top=1"
            r = _get_session().get(url, headers=_headers(token), timeout=30)
            r.raise_for_status()

            items = r.json().get("value", [])
            if not items:
                raise Exception(
                    f"Counter list boş! Lütfen '{self.list_name}' list'ine bir item ekleyin:\\n"
                    "  Title: 'Global Counter'\\n"
                    "  Current_Count: 1"
                )

            return items[0]
        except Exception as e:
            logger.error(f"Counter item alma hatası: {e}")
            raise

    def get_next_counter(self) -> str:
        """
        Mevcut counter değerini al (9 haneye formatlanmış) — SALT OKUR.

        Tahsis İÇİN KULLANMA: eşzamanlı iki okuyucu aynı değeri görür.
        Tanılama/smoke amaçlı; gerçek tahsis reserve_next_counter()'dadır.

        Returns:
            "000000042" gibi 9 haneli string

        Raises:
            Exception: SharePoint erişim hatası
        """
        try:
            token = get_graph_token()
            site_id, _ = _get_site_and_drive_id(token)
            list_id = self._get_list_id(token, site_id)

            # Field mapping tespit et
            field_map = self._detect_field_mapping(token, site_id, list_id)
            current_count_field = field_map.get("Current_Count")

            if not current_count_field:
                raise Exception("Current_Count field bulunamadı!")

            # Item al
            item = self._get_counter_item(token, site_id, list_id)
            raw_count = item["fields"].get(current_count_field, 1)
            count = int(float(raw_count))  # Ensure int (handle 2.0 -> 2)

            # 9 haneye format
            formatted = str(count).zfill(9)
            logger.info(f"Counter okundu: {formatted}")
            return formatted

        except Exception as e:
            error_msg = f"Counter okuma hatası: {e}"
            logger.error(error_msg)
            TechnicalLogger.log("ERROR", error_msg)
            raise Exception(f"SharePoint counter erişilemedi: {e}") from e

    def reserve_next_counter(self) -> str:
        """
        Sıradaki ofis numarasını ATOMİK tahsis et: oku + artır + döndür.

        ETag/If-Match ile optimistic concurrency: PATCH yalnız okunan sürüm
        hâlâ günceldeyse geçer; 412'de (başka kullanıcı önce davrandı) yeni
        değer okunup jitter'lı backoff ile tekrar denenir. Dönen numara BU
        çağrıya aittir — eşzamanlı iki çağrı asla aynı numarayı alamaz.

        Returns:
            Tahsis edilen numara, "000000042" gibi 9 haneli string

        Raises:
            Exception: SharePoint erişim hatası ya da çakışmaların
            RESERVE_MAX_ATTEMPTS boyunca sürmesi
        """
        try:
            username = os.getlogin()
        except OSError:
            username = "System"

        for attempt in range(1, RESERVE_MAX_ATTEMPTS + 1):
            try:
                token = get_graph_token()
                site_id, _ = _get_site_and_drive_id(token)
                list_id = self._get_list_id(token, site_id)

                field_map = self._detect_field_mapping(token, site_id, list_id)
                current_count_field = field_map.get("Current_Count")
                last_updated_field = field_map.get("Last_Updated")
                updated_by_field = field_map.get("Updated_By")

                if not current_count_field:
                    raise Exception("Current_Count field bulunamadı!")

                # Item al (ETag ile)
                item = self._get_counter_item(token, site_id, list_id)
                item_id = item["id"]
                etag = item.get("eTag")
                reserved = int(float(item["fields"].get(current_count_field, 1)))
                new_count = reserved + 1

                url = f"{GRAPH}/sites/{site_id}/lists/{list_id}/items/{item_id}"
                headers = _headers(token)
                # ETag: yazma yalnız okuduğumuz sürümün üstüne geçebilir.
                # ETag hiç gelmezse (beklenmez) son-yazan-kazanır PATCH'e düşer.
                if etag:
                    headers["If-Match"] = etag

                update_data = {"fields": {current_count_field: new_count}}
                if last_updated_field:
                    update_data["fields"][last_updated_field] = datetime.now().isoformat()
                if updated_by_field:
                    update_data["fields"][updated_by_field] = username

                r = _get_session().patch(url, headers=headers, json=update_data, timeout=30)

                if r.status_code == 412:  # Precondition Failed — başka kullanıcı kazandı
                    self._sleep_before_retry(attempt)
                    continue

                r.raise_for_status()

                formatted = str(reserved).zfill(9)
                logger.info(f"Ofis no tahsis edildi: {formatted} (sayaç {reserved} → {new_count})")
                TechnicalLogger.log("INFO", f"Counter tahsis: {reserved} → {new_count}", {
                    "user": username,
                    "list": self.list_name,
                })
                return formatted

            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 412:
                    self._sleep_before_retry(attempt)
                    continue
                self._reset_caches()
                error_msg = f"Counter tahsis hatası: {e}"
                logger.error(error_msg)
                TechnicalLogger.log("ERROR", error_msg)
                raise Exception(f"SharePoint counter güncellenemedi: {e}") from e

            except Exception as e:
                self._reset_caches()
                error_msg = f"Counter tahsis hatası: {e}"
                logger.error(error_msg)
                TechnicalLogger.log("ERROR", error_msg)
                raise Exception(f"Counter tahsisi başarısız: {e}") from e

        # Tüm denemeler 412 ile tükendi — nihai başarısızlık, tek ERROR
        # (log sözleşmesi: ara çakışmalar WARNING'di).
        error_msg = (
            f"Counter tahsisi başarısız: {RESERVE_MAX_ATTEMPTS} deneme sonrası "
            "ETag conflict devam ediyor"
        )
        logger.error(error_msg)
        TechnicalLogger.log("ERROR", error_msg)
        raise Exception(error_msg)

    def _sleep_before_retry(self, attempt: int):
        """412 sonrası bekleme: üstel backoff + jitter; son denemeden sonra uyumaz.

        Bilinçli senkron sleep: reserve_next_counter daima executor thread'inde
        koşar (routes/processing fetch_counter), event loop'u tutmaz.
        """
        logger.warning(f"ETag conflict! Retry {attempt}/{RESERVE_MAX_ATTEMPTS}")
        if attempt >= RESERVE_MAX_ATTEMPTS:
            return
        delay = min(
            _CONFLICT_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)),
            _CONFLICT_BACKOFF_CAP_SECONDS,
        )
        time.sleep(delay + random.uniform(0, _CONFLICT_BACKOFF_JITTER_SECONDS))


# --- FACTORY FUNCTION (eski api.py kodu ile uyumluluk için) ---

_manager_singleton = None
_manager_lock = threading.Lock()


def get_counter_manager():
    """
    Counter Manager Factory - süreç-tekil SharePoint Counter döner.

    Singleton (Faz 3-D): list_id + field_map cache'leri çağrılar arasında
    yaşasın diye — sıcak yolda tahsis 2 HTTP turudur (item GET + PATCH).
    Cache yazımları idempotent (hep aynı değerler), thread yarışı zararsız.
    """
    global _manager_singleton
    if _manager_singleton is None:
        with _manager_lock:
            if _manager_singleton is None:
                logger.info("SharePoint Counter Manager kullanılıyor")
                _manager_singleton = SharePointCounterManager()
    return _manager_singleton


# Test fonksiyonu (python -m managers.counter_manager ile koşar)
if __name__ == "__main__":
    import logging

    from logging_setup import configure_logging

    configure_logging()
    logger = logging.getLogger("SharePointCounterManagerTest")

    logger.info("SharePoint Counter Manager Test")
    logger.info("=" * 60)

    try:
        cm = SharePointCounterManager()

        logger.info("1. Counter okuma (salt okunur)...")
        current = cm.get_next_counter()
        logger.info(f"   Mevcut counter: {current}")

        logger.info("2. Atomik tahsis (oku+artır+döndür)...")
        reserved = cm.reserve_next_counter()
        logger.info(f"   ✅ Tahsis edilen numara: {reserved}")

        logger.info("3. Yeni değer...")
        new_val = cm.get_next_counter()
        logger.info(f"   Yeni counter: {new_val}")

        logger.info("=" * 60)
        logger.info("✅ Test başarılı!")

    except Exception as e:
        logger.error(f"❌ HATA: {e}")
        import traceback
        traceback.print_exc()
