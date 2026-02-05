"""
SharePoint Counter Manager - Multi-User Safe Counter System

Bu modül SharePoint List kullanarak merkezi, atomic counter yönetimi sağlar.
Race condition'ları ETag ve optimistic concurrency ile önler.
"""

import os
import requests
import logging
from typing import Optional, Tuple
from datetime import datetime

from auth_graph import get_graph_token
from sharepoint_uploader_graph import _get_site_and_drive_id, _headers
from log_manager import TechnicalLogger

GRAPH = "https://graph.microsoft.com/v1.0"
COUNTER_LIST_NAME = os.getenv("SHAREPOINT_COUNTER_LIST_NAME", "Counter")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SharePointCounterManager")


class SharePointCounterManager:
    """
    SharePoint List tabanlı multi-user-safe counter.
    
    Özellikler:
    - Atomic increment (ETag + optimistic concurrency)
    - Merkezi (tüm kullanıcılar aynı counter'ı kullanır)
    - No fallback (SharePoint offline ise hata fırlatır)
    """
    
    def __init__(self):
        self.list_name = COUNTER_LIST_NAME
        self._field_map_cache = None  # Field mapping cache
        
    def _get_list_id(self, token: str, site_id: str) -> Optional[str]:
        """Counter list'in ID'sini bul"""
        try:
            url = f"{GRAPH}/sites/{site_id}/lists"
            r = requests.get(url, headers=_headers(token), timeout=30)
            r.raise_for_status()
            
            lists = r.json().get("value", [])
            for lst in lists:
                if lst.get("displayName") == self.list_name or lst.get("name") == self.list_name:
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
            r = requests.get(url, headers=_headers(token), timeout=30)
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
            r = requests.get(url, headers=_headers(token), timeout=30)
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
        Mevcut counter değerini al (9 haneye formatlanmış).
        
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
            raise Exception(f"SharePoint counter erişilemedi: {e}")
    
    def increment_counter(self) -> bool:
        """
        Counter'ı atomic olarak 1 artır (ETag ile optimistic concurrency).
        
        Returns:
            True: Başarılı
            False: Hata (exception fırlatır)
            
        Raises:
            Exception: SharePoint güncelleme hatası veya ETag conflict
        """
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                token = get_graph_token()
                site_id, _ = _get_site_and_drive_id(token)
                list_id = self._get_list_id(token, site_id)
                
                # Field mapping
                field_map = self._detect_field_mapping(token, site_id, list_id)
                current_count_field = field_map.get("Current_Count")
                last_updated_field = field_map.get("Last_Updated")
                updated_by_field = field_map.get("Updated_By")
                
                # Item al (ETag ile)
                item = self._get_counter_item(token, site_id, list_id)
                item_id = item["id"]
                etag = item.get("eTag")
                current_count = item["fields"].get(current_count_field, 1)
                
                # Yeni değer (ensure int)
                new_count = int(float(current_count)) + 1
                
                # Kullanıcı bilgisi
                try:
                    username = os.getlogin()
                except:
                    username = "System"
                
                # PATCH ile atomic update (ETag kontrolü)
                url = f"{GRAPH}/sites/{site_id}/lists/{list_id}/items/{item_id}"
                headers = _headers(token)
                
                # ETag ekle (optimistic concurrency için)
                if etag:
                    headers["If-Match"] = etag
                
                update_data = {
                    "fields": {
                        current_count_field: new_count
                    }
                }
                
                # Opsiyonel field'lar (varsa)
                if last_updated_field:
                    update_data["fields"][last_updated_field] = datetime.now().isoformat()
                if updated_by_field:
                    update_data["fields"][updated_by_field] = username
                
                r = requests.patch(url, headers=headers, json=update_data, timeout=30)
                
                # ETag conflict (başka kullanıcı aynı anda güncelledi)
                if r.status_code == 412:  # Precondition Failed
                    retry_count += 1
                    logger.warning(f"ETag conflict! Retry {retry_count}/{max_retries}")
                    continue
                
                r.raise_for_status()
                
                logger.info(f"Counter güncellendi: {current_count} → {new_count}")
                TechnicalLogger.log("INFO", f"Counter increment: {current_count} → {new_count}", {
                    "user": username,
                    "list": self.list_name
                })
                return True
                
            except requests.HTTPError as e:
                if e.response.status_code == 412:
                    # ETag conflict, retry
                    retry_count += 1
                    continue
                else:
                    error_msg = f"Counter increment hatası: {e}"
                    logger.error(error_msg)
                    TechnicalLogger.log("ERROR", error_msg)
                    raise Exception(f"SharePoint counter güncellenemedi: {e}")
            
            except Exception as e:
                error_msg = f"Counter increment hatası: {e}"
                logger.error(error_msg)
                TechnicalLogger.log("ERROR", error_msg)
                raise Exception(f"Counter increment başarısız: {e}")
        
        # Max retry aşıldı
        error_msg = f"Counter increment başarısız: {max_retries} deneme sonrası ETag conflict devam ediyor"
        logger.error(error_msg)
        TechnicalLogger.log("CRITICAL", error_msg)
        raise Exception(error_msg)


# --- FACTORY FUNCTION (eski api.py kodu ile uyumluluk için) ---

def get_counter_manager():
    """
    Counter Manager Factory - SharePoint Counter döner.
    
    Returns:
        SharePointCounterManager instance
    """
    logger.info("SharePoint Counter Manager kullanılıyor")
    return SharePointCounterManager()


# Test fonksiyonu
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("SharePointCounterManagerTest")

    logger.info("SharePoint Counter Manager Test")
    logger.info("=" * 60)
    
    try:
        cm = SharePointCounterManager()
        
        logger.info("1. Counter okuma...")
        current = cm.get_next_counter()
        logger.info(f"   Mevcut counter: {current}")
        
        logger.info("2. Counter artırma...")
        cm.increment_counter()
        logger.info("   ✅ Counter artırıldı")
        
        logger.info("3. Yeni değer...")
        new_val = cm.get_next_counter()
        logger.info(f"   Yeni counter: {new_val}")
        
        logger.info("=" * 60)
        logger.info("✅ Test başarılı!")
        
    except Exception as e:
        logger.error(f"❌ HATA: {e}")
        import traceback
        traceback.print_exc()
