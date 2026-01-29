import logging
import requests
from auth_graph import get_graph_token
from sharepoint_uploader_graph import _get_site_and_drive_id, GRAPH, _headers, _load_env

# Logger kurulumu
logger = logging.getLogger("ListManager")


def get_lawyer_list_from_sharepoint():
    """
    SharePoint 'AvukatListesi'nden avukatları ve kısaltmalarını çeker.
    Returns:
        list: [{'code': 'AGH', 'name': 'Ayşe...'}, ...] formatında liste.
    """
    _load_env()
    LIST_NAME = "AvukatListesi"
    lawyers = []

    try:
        logger.info(f"ListManager: '{LIST_NAME}' verisi çekiliyor...")

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
            logger.error(f"ListManager: '{LIST_NAME}' bulunamadı!")
            return []

        # 2. Öğeleri Çek
        items_url = (
            f"{GRAPH}/sites/{site_id}/lists/{target_list_id}/items?expand=fields"
        )
        r = requests.get(items_url, headers=headers)
        r.raise_for_status()

        items = r.json().get("value", [])

        for item in items:
            fields = item.get("fields", {})
            name = fields.get("Title")
            # Correct internal field name found via diagnosis: kKisaKod
            code = fields.get("kKisaKod")

            if name and code:
                lawyers.append({"code": code, "name": name})

        logger.info(f"ListManager: {len(lawyers)} avukat başarıyla çekildi.")
        return lawyers

    except Exception as e:
        logger.error(f"ListManager HATA: {e}")
        return []


def get_status_list_from_sharepoint():
    """
    SharePoint 'durum' listesinden durum kodlarını çeker.
    Returns:
        list: [{'code': 'B', 'name': 'Büro...'}, ...] formatında liste.
    """
    _load_env()
    LIST_NAME = "durum"
    statuses = []

    try:
        logger.info(f"ListManager: '{LIST_NAME}' verisi çekiliyor...")

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
            logger.error(f"ListManager: '{LIST_NAME}' bulunamadı!")
            return []

        # 3. Öğeleri Çek
        items_url = (
            f"{GRAPH}/sites/{site_id}/lists/{target_list_id}/items?expand=fields"
        )
        r = requests.get(items_url, headers=headers)
        r.raise_for_status()

        items = r.json().get("value", [])

        for item in items:
            fields = item.get("fields", {})
            name = fields.get("Title")
            # Try multiple variations
            code = (
                fields.get("Kod")
                or fields.get("OData__x004b_od")
                or fields.get("KisaKod")
                or fields.get("Kisakod")
            )

            if name and code:
                statuses.append({"code": code, "name": name})

        logger.info(f"ListManager: {len(statuses)} durum başarıyla çekildi.")
        return statuses


    except Exception as e:
        logger.error(f"ListManager Status HATA: {e}")
        # Don't print raw exception to console (security)
        try:
            from log_manager import TechnicalLogger
            TechnicalLogger.log("ERROR", "Status list fetch failed", {
                "error_type": type(e).__name__,
                "list_name": LIST_NAME
            })
        except:
            pass  # Fallback if logger unavailable
        return []



def get_doctype_list_from_sharepoint():
    """
    SharePoint 'BelgeTuru' listesinden belge türlerini çeker.
    Returns:
        list: [{'code': 'DAVA-DLK', 'name': 'Dava Dilekçesi'}, ...]
    """
    _load_env()
    LIST_NAME = "BelgeTuru"
    doctypes = []

    try:
        logger.info(f"ListManager: '{LIST_NAME}' verisi çekiliyor...")

        token = get_graph_token()
        site_id, _ = _get_site_and_drive_id(token)
        headers = _headers(token)

        # Listeyi Bul
        r = requests.get(f"{GRAPH}/sites/{site_id}/lists", headers=headers)
        r.raise_for_status()

        lists = r.json().get("value", [])
        target_list_id = None

        for lst in lists:
            if lst.get("displayName") == LIST_NAME or lst.get("name") == LIST_NAME:
                target_list_id = lst["id"]
                break

        if not target_list_id:
            logger.error(f"ListManager: '{LIST_NAME}' bulunamadı!")
            return []

        # Öğeleri Çek
        items_url = (
            f"{GRAPH}/sites/{site_id}/lists/{target_list_id}/items?expand=fields"
        )
        r = requests.get(items_url, headers=headers)
        r.raise_for_status()

        items = r.json().get("value", [])

        for item in items:
            fields = item.get("fields", {})
            # Title -> Kon (Dosya Adı)
            # field_1 -> Orijinal Adı / Açıklama (SharePoint Internal Name: field_1)
            code = fields.get("Title")
            name = (
                fields.get("field_1")
                or fields.get("OrijinalAdi")
                or fields.get("Aciklama")
            )

            if code:
                # Name boşsa code'u kullan (fallback)
                final_name = name if name else code
                doctypes.append({"code": code, "name": final_name})

        logger.info(f"ListManager: {len(doctypes)} belge türü başarıyla çekildi.")
        return doctypes


    except Exception as e:
        logger.error(f"ListManager DocType HATA: {e}")
        # Don't print raw exception to console (security)
        try:
            from log_manager import TechnicalLogger
            TechnicalLogger.log("ERROR", "DocType list fetch failed", {
                "error_type": type(e).__name__,
                "list_name": LIST_NAME
            })
        except:
            pass  # Fallback if logger unavailable
        return []

