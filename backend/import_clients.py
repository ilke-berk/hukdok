"""
Müvekkil (Client) İçeri Aktarma Scripti
========================================
CSV dosyasından müvekkil verilerini PostgreSQL veritabanına aktarır.

Kurallar:
- İsimlerden DR, DR. gibi ünvanlar temizlenir
- Cari kodu olmayana otomatik benzersiz cari kod verilir (AUTO-XXXXX)
- Veritabanında zaten varsa: sadece BOŞ alanlar güncellenir (dolu olanlar ezilmez)
- Veritabanında yoksa: yeni kayıt oluşturulur

Kullanım:
  cd backend
  python import_clients.py
"""

import csv
import os
import re
import sys

# Ensure we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# FORCE LOCALHOST FOR WINDOWS EXECUTION
import os
os.environ["DATABASE_URL"] = "postgresql://hukudok_user:dv3clS_gcjnKgCn7suoaZU@localhost:5432/hukudok"

from database import SessionLocal
from models import Client

# ============================================================================
# İSİM TEMİZLEME FONKSİYONU
# ============================================================================

# DR/DR. ünvanlarını isimden temizle
DR_PATTERNS = [
    r'\bDR\.\s*$',     # Sondaki "DR."
    r'\bDR\s*$',       # Sondaki "DR"
    r'\bDR\.\s*,',     # "DR.," gibi
    r',\s*DR\.?\s*$',  # Sondaki ", DR."
]

def clean_client_name(raw_name: str) -> str:
    """
    İsimden DR/DR. ünvanını temizler, fazla boşlukları siler, büyük harfe çevirir.
    Örnek: "FERHAT TÜFEKÇİ DR." -> "FERHAT TÜFEKÇİ"
    """
    if not raw_name:
        return ""
    
    name = raw_name.strip()
    
    # Sondaki DR. veya DR'yi temizle
    for pattern in DR_PATTERNS:
        name = re.sub(pattern, '', name, flags=re.IGNORECASE)
    
    # Baştaki DR. veya DR'yi de temizle (nadiren olur)
    name = re.sub(r'^\s*DR\.?\s+', '', name, flags=re.IGNORECASE)
    
    # Birden fazla boşluğu tek boşluğa indir
    name = re.sub(r'\s+', ' ', name).strip()
    
    # Büyük harfe çevir (Türkçe uyumlu)
    name = name.upper()
    
    return name


def clean_value(val: str) -> str:
    """Boş, anlamsız değerleri temizler."""
    if not val:
        return None
    val = val.strip()
    # "Lütfen Seçiniz", "-", "." gibi anlamsız değerleri boşalt
    if val.lower() in ['', '-', '.', 'lütfen seçiniz', 'giriniz', 'yok', 'none']:
        return None
    return val


def map_client_type(tur: str) -> str:
    """CSV'deki Tür -> DB client_type dönüşümü."""
    if not tur:
        return None
    tur = tur.strip().lower()
    if tur == 'şahıs' or tur == 'sahıs' or tur == 'sahis':
        return 'Individual'
    elif tur == 'kurum':
        return 'Corporate'
    return None


# ============================================================================
# ANA İMPORT FONKSİYONU
# ============================================================================

def import_clients(csv_path: str):
    """CSV dosyasından müvekkilleri veritabanına aktarır."""
    
    if not os.path.exists(csv_path):
        print(f"❌ Dosya bulunamadı: {csv_path}")
        return
    
    db = SessionLocal()
    
    try:
        # Mevcut müvekkilleri isimle indexle
        existing_clients = db.query(Client).all()
        client_map = {}
        for c in existing_clients:
            client_map[c.name.upper().strip()] = c
        
        print(f"📊 Veritabanında mevcut müvekkil sayısı: {len(client_map)}")
        
        # Mevcut en yüksek cari kodu bul (AUTO- olanlar için)
        existing_cari_kods = set()
        for c in existing_clients:
            if c.cari_kod:
                existing_cari_kods.add(c.cari_kod)
        
        auto_counter = 90001  # AUTO kodları 90001'den başlasın
        
        # CSV'yi oku
        updated_count = 0
        created_count = 0
        skipped_count = 0
        errors = []
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row_num, row in enumerate(reader, start=2):  # 2'den başla (1 = başlık satırı)
                try:
                    # İsmi temizle
                    raw_name = row.get('Ad Soyad / Unvan', '').strip()
                    if not raw_name:
                        skipped_count += 1
                        continue
                    
                    clean_name_val = clean_client_name(raw_name)
                    if not clean_name_val:
                        skipped_count += 1
                        continue
                    
                    # CSV değerlerini çıkart ve temizle
                    cari_kod = clean_value(row.get('Cari Kodu', ''))
                    email = clean_value(row.get('e-Posta Adresi', ''))
                    mobile_phone = clean_value(row.get('Cep Telefonu', ''))
                    phone = clean_value(row.get('Telefon', ''))
                    city = clean_value(row.get('İl', ''))
                    tc_no = clean_value(row.get('TC Kimlik No', ''))
                    specialty = clean_value(row.get('Uzmanlık Alanı', ''))
                    category = clean_value(row.get('Grup/Kategori', ''))
                    client_type_raw = clean_value(row.get('Tür', ''))
                    client_type = map_client_type(client_type_raw)
                    
                    # Cari kodu yoksa benzersiz otomatik ver
                    if not cari_kod:
                        while str(auto_counter) in existing_cari_kods:
                            auto_counter += 1
                        cari_kod = str(auto_counter)
                        existing_cari_kods.add(cari_kod)
                        auto_counter += 1
                    
                    # Veritabanında bu isimle müvekkil var mı?
                    existing = client_map.get(clean_name_val)
                    
                    if existing:
                        # GÜNCELLE: Sadece boş alanları doldur (dolu olanları ezme!)
                        changed = False
                        if not existing.cari_kod and cari_kod:
                            existing.cari_kod = cari_kod; changed = True
                        if not existing.email and email:
                            existing.email = email; changed = True
                        if not existing.mobile_phone and mobile_phone:
                            existing.mobile_phone = mobile_phone; changed = True
                        if not existing.phone and phone:
                            existing.phone = phone; changed = True
                        if not existing.address and city:
                            existing.address = city; changed = True
                        if not existing.tc_no and tc_no:
                            existing.tc_no = tc_no; changed = True
                        if not existing.specialty and specialty:
                            existing.specialty = specialty; changed = True
                        if not existing.category and category:
                            existing.category = category; changed = True
                        if not existing.client_type and client_type:
                            existing.client_type = client_type; changed = True
                        
                        if changed:
                            updated_count += 1
                        else:
                            skipped_count += 1
                    else:
                        # YENİ KAYIT OLUŞTUR
                        new_client = Client(
                            name=clean_name_val,
                            cari_kod=cari_kod,
                            email=email,
                            mobile_phone=mobile_phone,
                            phone=phone,
                            address=city,
                            tc_no=tc_no,
                            specialty=specialty,
                            category=category,
                            client_type=client_type,
                            active=True,
                            contact_type="Client",
                        )
                        db.add(new_client)
                        client_map[clean_name_val] = new_client
                        created_count += 1
                
                except Exception as e:
                    errors.append(f"Satır {row_num}: {raw_name} -> {str(e)}")
                    continue
        
        # Değişiklikleri kaydet
        db.commit()
        
        # SONUÇ RAPORU
        print("\n" + "=" * 60)
        print("📋 MÜVEKKİL IMPORT RAPORU")
        print("=" * 60)
        print(f"✅ Yeni eklenen müvekkil  : {created_count}")
        print(f"🔄 Güncellenen müvekkil   : {updated_count}")
        print(f"⏭️  Değişiklik yok/atlandı : {skipped_count}")
        print(f"❌ Hata                    : {len(errors)}")
        print(f"📊 Toplam işlenen satır   : {created_count + updated_count + skipped_count + len(errors)}")
        print("=" * 60)
        
        if errors:
            print("\n⚠️ HATALAR:")
            for err in errors[:20]:  # İlk 20 hatayı göster
                print(f"   {err}")
            if len(errors) > 20:
                print(f"   ... ve {len(errors) - 20} hata daha")
    
    except Exception as e:
        db.rollback()
        print(f"❌ Kritik hata: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        db.close()


# ============================================================================
# ÇALIŞTIR
# ============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--wipe", action="store_true", help="Wipe existing clients before import")
    args = parser.parse_args()

    csv_file = r"c:\Users\ilkeb\OneDrive\Masaüstü\Cari_Listesi_Final.csv"
    
    if args.wipe:
        print("⚠️ DİKKAT: Mevcut müvekkiller siliniyor...")
        from database import SessionLocal
        from models import Client
        db = SessionLocal()
        try:
            db.query(Client).delete()
            db.commit()
            print("✅ Mevcut müvekkiller silindi.")
        except Exception as e:
            db.rollback()
            print(f"❌ Silme hatası: {e}")
        finally:
            db.close()

    print(f"📂 CSV dosyası: {csv_file}")
    print(f"🚀 İçeri aktarma başlıyor...\n")
    import_clients(csv_file)
