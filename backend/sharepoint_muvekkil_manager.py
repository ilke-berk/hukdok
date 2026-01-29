
"""
SharePoint Müvekkil Listesi Yöneticisi
'Muvekkil' listesinden müvekkil isimlerini çeker
"""

import logging
import requests
from auth_graph import get_graph_token
from sharepoint_uploader_graph import _get_site_and_drive_id, GRAPH, _headers, _load_env

# Logger kurulumu
logger = logging.getLogger("MuvekkilListManager")


def get_client_list_from_sharepoint():
    """
    SharePoint 'Muvekkil' listesinden müvekkil isimlerini ve ID'lerini çeker.
    Returns:
        list[dict]: [{'id': '123', 'name': 'Ahmet Yılmaz'}, ...] formatında liste.
    """
    _load_env()
    LIST_NAME = "Muvekkil"
    clients = []

    try:
        logger.info(f"MuvekkilListManager: '{LIST_NAME}' verisi çekiliyor...")

        token = get_graph_token()
        site_id, _ = _get_site_and_drive_id(token)
        headers = _headers(token)

        # 1. Listeyi Bul
        r = requests.get(f"{GRAPH}/sites/{site_id}/lists", headers=headers)
        r.raise_for_status()

        lists = r.json().get("value", [])
        target_list_id = None

        for lst in lists:
            if lst.get("displayName") == LIST_NAME or lst.get("name") == LIST_NAME:
                target_list_id = lst["id"]
                break

        if not target_list_id:
            logger.error(f"MuvekkilListManager: '{LIST_NAME}' bulunamadı!")
            return []

        # 2. Öğeleri Çek (Pagination ile - tüm sayfaları çek)
        items_url = (
            f"{GRAPH}/sites/{site_id}/lists/{target_list_id}/items?expand=fields&$top=5000"
        )
        
        page_count = 0
        while items_url:
            page_count += 1
            logger.info(f"MuvekkilListManager: Sayfa {page_count} çekiliyor...")
            
            r = requests.get(items_url, headers=headers)
            r.raise_for_status()
            
            response_data = r.json()
            items = response_data.get("value", [])
            
            # Bu sayfadaki itemleri işle
            for item in items:
                item_id = item.get("id")  # SharePoint item ID
                fields = item.get("fields", {})
                # Title sütunu varsayılan SharePoint sütunu - müvekkil adı burada
                client_name = fields.get("Title")
                
                if client_name and item_id:
                    clients.append({
                        "id": str(item_id),
                        "name": client_name.strip()
                    })
            
            # Sonraki sayfa var mı kontrol et
            items_url = response_data.get("@odata.nextLink", None)
            
            logger.info(f"MuvekkilListManager: Sayfa {page_count} - {len(items)} item çekildi (Toplam: {len(clients)})")

        logger.info(f"MuvekkilListManager: ✅ TOPLAM {len(clients)} müvekkil başarıyla çekildi ({page_count} sayfa).")
        return clients

    except Exception as e:
        logger.error(f"MuvekkilListManager HATA: {e}")
        return []
