
"""
SharePoint Müvekkil Listesi Yöneticisi
'Muvekkil' listesinden müvekkil isimlerini çeker
"""

import logging
import requests
from auth_graph import get_graph_token
from sharepoint_uploader_graph import _get_site_and_drive_id, GRAPH, _headers, _load_env

# DB Imports
from database import SessionLocal
import models

# Logger kurulumu
logger = logging.getLogger("MuvekkilListManager")


def get_client_list_from_sharepoint():
    """
    Retrieves clients from the local database.
    Falls back to SharePoint if DB is empty or fails.
    Returns:
        list[dict]: [{'id': '123', 'name': 'Ahmet Yılmaz'}, ...]
    """
    try:
        db = SessionLocal()
        try:
            clients_db = db.query(models.Client).filter(models.Client.active == True).all()
            if clients_db:
                # Note: 'id' in the return object historically referred to SharePoint ID
                # We should maintain that contract for now.
                # Since we have normalized, we return the source_ids string (JSON) as the ID ref
                # FIX: Ensure we return parsed list if possible to avoid double escaping in consumers
                result = []
                import json
                for c in clients_db:
                    try:
                         # Try to load if it's a JSON string, otherwise use as is
                         sid = json.loads(c.source_ids) if c.source_ids and (
                             c.source_ids.startswith("[") or c.source_ids.startswith("\"")
                         ) else c.source_ids
                         
                         # If it was a list of strings, that's what we want
                         if isinstance(sid, list):
                             # Ensure all elements are strings
                             sid = [str(x) for x in sid]
                    except:
                        sid = c.source_ids

                    result.append({"id": sid, "name": c.name})

                logger.info(f"MuvekkilListManager: {len(result)} clients loaded from DATABASE.")
                return result
        except Exception as db_e:
            logger.error(f"MuvekkilListManager DB Error: {db_e}")
        finally:
            db.close()
            
        return _fetch_clients_direct_sharepoint()

    except Exception as e:
        logger.error(f"MuvekkilListManager HATA: {e}")
        return []

def _fetch_clients_direct_sharepoint():
    _load_env()
    LIST_NAME = "Muvekkil"
    clients = []
    try:
        logger.info(f"MuvekkilListManager: '{LIST_NAME}' verisi çekiliyor (Online)...")
        token = get_graph_token()
        site_id, _ = _get_site_and_drive_id(token)
        headers = _headers(token)
        
        r = requests.get(f"{GRAPH}/sites/{site_id}/lists", headers=headers)
        r.raise_for_status()
        lists = r.json().get("value", [])
        target_list_id = None
        for lst in lists:
            if lst.get("displayName") == LIST_NAME or lst.get("name") == LIST_NAME:
                target_list_id = lst["id"]
                break
        if not target_list_id: return []
        
        items_url = f"{GRAPH}/sites/{site_id}/lists/{target_list_id}/items?expand=fields&$top=5000"
        page_count = 0
        while items_url:
            page_count += 1
            r = requests.get(items_url, headers=headers)
            r.raise_for_status()
            response_data = r.json()
            items = response_data.get("value", [])
            for item in items:
                item_id = item.get("id")
                fields = item.get("fields", {})
                client_name = fields.get("Title")
                if client_name and item_id:
                    clients.append({"id": str(item_id), "name": client_name.strip()})
            items_url = response_data.get("@odata.nextLink", None)
            
        logger.info(f"MuvekkilListManager: {len(clients)} client SharePoint'ten çekildi.")
        return clients
    except Exception as e:
        logger.error(f"Client Fetch Error: {e}")
        return []
