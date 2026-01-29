"""
SharePoint Müvekkil Listesi Senkronizasyonu

Bu modül SharePoint 'Muvekkil' listesini çeker, JSON olarak kaydeder,
normalize eder ve sistemdeki matcher'ı günceller.
"""

import json
from pathlib import Path
import logging
from typing import List, Dict
from datetime import datetime
# from sharepoint_manager import get_client_list  # Legacy import removed

logger = logging.getLogger(__name__)

LISTE_DOSYASI = Path("backend/data/muvekkil_listesi.json")

def sync_muvekkil_listesi_from_sharepoint() -> bool:
    """
    SHAREPOINT'ten müvekkil listesini çeker, JSON'a yazar,
    Normalize eder ve Matcher'ı günceller.
    
    Returns:
        bool: Başarılı ise True
    """
    logger.info("🔄 SharePoint sync başlatıldı...")
    
    try:
        # SharePoint'ten listeyi çek
        from sharepoint_muvekkil_manager import get_client_list_from_sharepoint
        
        muvekiller = get_client_list_from_sharepoint()
        
        if not muvekiller:
            logger.warning("⚠️ SharePoint'ten müvekkil listesi boş geldi")
            return False
        
        # JSON'a kaydet
        data = {
            "metadata": {
                "kaynak": "SharePoint - Muvekkil Listesi",
                "son_guncelleme": datetime.now().isoformat(),
                "toplam_muvekkil": len(muvekiller),
                "durum": "AKTIF"
            },
            "muvekiller": muvekiller
        }
        
        with open(LISTE_DOSYASI, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ {len(muvekiller)} müvekkil ham listeye kaydedildi")
        
        # 1. Normalize Et (Ham liste -> Normalized Liste)
        from client_normalizer import process_client_list
        logger.info("🔨 Liste normalize ediliyor...")
        process_client_list()
        
        # 2. Matcher Yenile (Hot Reload)
        from muvekkil_matcher_v2 import yenile_matcher
        yenile_matcher()
        
        return True
        
    except Exception as e:
        logger.error(f"❌ SharePoint sync hatası: {e}")
        return False

def manuel_liste_yukle(csv_dosya: str) -> bool:
    """
    CSV dosyasından manuel liste yükleme (geçici çözüm)
    
    Args:
        csv_dosya: CSV dosya yolu (İsim sütunu olmalı)
    
    Returns:
        bool: Başarılı ise True
    """
    import csv
    
    try:
        muvekiller = []
        
        with open(csv_dosya, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                isim = row.get("İsim") or row.get("Müvekkil Adı") or row.get("Ad Soyad")
                if isim:
                    muvekiller.append(isim.strip())
        
        data = {
            "metadata": {
                "kaynak": f"Manuel CSV Import - {csv_dosya}",
                "son_guncelleme": datetime.now().isoformat(),
                "toplam_muvekkil": len(muvekiller),
                "durum": "MANUEL - SharePoint sync bekleniyor"
            },
            "muvekiller": muvekiller
        }
        
        with open(LISTE_DOSYASI, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ {len(muvekiller)} müvekkil manuel olarak yüklendi")
        
        # 1. Normalize Et
        from client_normalizer import process_client_list
        logger.info("🔨 Liste normalize ediliyor...")
        process_client_list()
        
        # 2. Matcher Yenile
        from muvekkil_matcher_v2 import yenile_matcher
        yenile_matcher()
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Manuel yükleme hatası: {e}")
        return False

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("SharePointSyncTest")

    logger.info("SharePoint Sync Modülü (Placeholder)")
    logger.info("Liste hazır olunca aktive edilecek")
    
    logger.info("Manuel CSV yükleme için:")
    logger.info("  python sharepoint_sync.py")
    # logger.info("  >>> from sharepoint_sync import manuel_liste_yukle")
    # logger.info("  >>> manuel_liste_yukle('muvekiller.csv')")
