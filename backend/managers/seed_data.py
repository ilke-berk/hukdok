"""Referans listeleri için başlangıç (seed) verileri.

Her _seed_* fonksiyonu idempotenttir: yalnızca eksik kayıtları ekler
(veya tablo tamamen boşsa doldurur).
"""
import logging

from database import SessionLocal
import models

logger = logging.getLogger("AdminManager")


def seed_all_lists():
    """Seed tüm tabloları başlangıç verileriyle doldurur (yalnızca boşsa)."""
    _seed_file_types()
    _seed_court_types()
    _seed_party_roles()
    _seed_bureau_types()
    _seed_cities()
    _seed_specialties()
    _seed_client_categories()
    _seed_file_statuses()


def _seed_file_types():
    db = SessionLocal()
    try:
        items = [
            ("Ceza",        "Ceza"),
            ("Hukuk",       "Hukuk"),
            ("İcra",        "İcra"),
            ("İdare",       "İdare"),
            ("İdari Yargı", "İdari Yargı"),
            ("Arabuluculuk","Arabuluculuk"),
            ("Savcılık",    "Savcılık"),
            ("Tahkim",      "Tahkim"),
            ("Vergi",       "Vergi"),
            ("Danışmanlık", "Danışmanlık"),
        ]
        added = 0
        for idx, (code, name) in enumerate(items):
            if not db.query(models.FileType).filter_by(code=code).first():
                db.add(models.FileType(code=code, name=name, active=True, sequence=idx))
                added += 1
        db.commit()
        if added:
            logger.info(f"Seeded {added} new file_types")
    except Exception as e:
        logger.error(f"Seed FileTypes Error: {e}")
    finally:
        db.close()


def _seed_court_types():
    db = SessionLocal()
    try:
        data = {
            "Ceza": [
                "AĞIR CEZA MAHKEMESİ", "ASLİYE CEZA MAHKEMESİ",
                "Bölge Adliye Mah. Ceza Dairesi", "ÇOCUK AĞIR CEZA MAHKEMESİ",
                "ÇOCUK MAHKEMESİ", "FİKRİ VE SINAİ HAKLAR CEZA MAHKEMESİ",
                "İCRA CEZA HAKİMLİĞİ", "İNFAZ HAKİMLİĞİ",
                "İSTİNAF CEZA DAİRESİ (İLK DERECE)", "SULH CEZA HAKİMLİĞİ",
                "YARGITAY CEZA DAİRESİ (İLK DERECE)",
            ],
            "Hukuk": [
                "AİLE MAHKEMESİ", "ASLİYE HUKUK MAHKEMESİ", "ASLİYE TİCARET MAHKEMESİ",
                "BAM HUKUK DAİRESİ (İLK DERECE)", "BÖLGE ADLİYE MAH. HUKUK DAİRESİ",
                "FİKRİ VE SINAİ HAKLAR HUKUK MAHKEMESİ", "İCRA HUKUK MAHKEMESİ",
                "İŞ MAHKEMESİ", "KADASTRO MAHKEMESİ", "KADASTRO MAHKEMESİ (MÜŞ)",
                "SULH HUKUK MAHKEMESİ", "TÜKETİCİ MAHKEMESİ",
            ],
            "İcra": ["İCRA DAİRESİ"],
            "İdari Yargı": ["BÖLGE İDARE MAHKEMESİ", "İDARE MAHKEMESİ", "VERGİ MAHKEMESİ"],
            "İdare": ["BÖLGE İDARE MAHKEMESİ", "İDARE MAHKEMESİ", "VERGİ MAHKEMESİ"],
            "Arabuluculuk": ["ARABULUCULUK DAİRE BAŞKANLIĞI", "ARABULUCULUK MERKEZİ"],
            "Savcılık": ["CUMHURİYET BAŞSAVCILIĞI"],
            "Tahkim": ["TAHKIM MAHKEMESİ", "MİLLETLERARASI TAHKİM", "TOBB TAHKİM MAHKEMESİ"],
            "Vergi": ["VERGİ MAHKEMESİ", "BÖLGE İDARE MAHKEMESİ (VERGİ)", "DANIŞTAY"],
            "Danışmanlık": [],
        }
        added = 0
        seq = db.query(models.CourtType).count()
        existing_keys = {
            (r.name, r.parent_code)
            for r in db.query(models.CourtType.name, models.CourtType.parent_code).all()
        }
        for parent, names in data.items():
            for name in names:
                if (name, parent) not in existing_keys:
                    code = (parent[:3] + "-" + name[:6]).upper().replace(" ", "")
                    db.add(models.CourtType(code=f"{code}-{seq}", name=name, parent_code=parent, active=True, sequence=seq))
                    seq += 1
                    added += 1
        db.commit()
        if added:
            logger.info(f"Seeded {added} new court_types")
    except Exception as e:
        logger.error(f"Seed CourtTypes Error: {e}")
    finally:
        db.close()


def _seed_party_roles():
    db = SessionLocal()
    try:
        main_roles = [
            "Davacı", "Davalı", "Müşteki", "Sanık", "İhbar Olunan", "Müdahil",
            "Şüpheli", "Borçlu", "Başvurucu", "Feri Müdahil", "Müdahil Davalı",
        ]
        third_roles = ["Tanık", "Bilirkişi", "Uzman", "Arabulucu", "Diğer"]

        def _norm(name):
            return name.upper().replace(" ", "-").replace("İ", "I").replace("Ş", "S").replace("Ğ", "G").replace("Ü", "U").replace("Ö", "O").replace("Ç", "C")

        existing = {r.name for r in db.query(models.PartyRole).all()}
        seq = db.query(models.PartyRole).count()
        added = 0
        for name in main_roles:
            if name not in existing:
                db.add(models.PartyRole(code=_norm(name), name=name, role_type="MAIN", active=True, sequence=seq))
                seq += 1
                added += 1
        for name in third_roles:
            if name not in existing:
                db.add(models.PartyRole(code="3-" + _norm(name), name=name, role_type="THIRD", active=True, sequence=seq))
                seq += 1
                added += 1
        db.commit()
        if added:
            logger.info(f"Seeded {added} new party_roles")
    except Exception as e:
        logger.error(f"Seed PartyRoles Error: {e}")
    finally:
        db.close()


def _seed_bureau_types():
    db = SessionLocal()
    try:
        if db.query(models.BureauType).count() > 0:
            return
        names = ["ALEYHE", "DR ÖZEL", "HASTANE ÖZEL MÜVEKKİL", "LEXİS", "RÜCU", "VEKALETLİ TAKİP", "VEKALETSİZ TAKİP", "ÖZEL"]
        for idx, name in enumerate(names):
            code = name.replace(" ", "-")
            db.add(models.BureauType(code=code, name=name, active=True, sequence=idx))
        db.commit()
        logger.info(f"Seeded {len(names)} bureau_types")
    except Exception as e:
        logger.error(f"Seed BureauTypes Error: {e}")
    finally:
        db.close()


def _seed_cities():
    db = SessionLocal()
    try:
        if db.query(models.City).count() > 0:
            return
        names = [
            "Adana", "Adıyaman", "Afyonkarahisar", "Ağrı", "Amasya", "Ankara", "Antalya", "Artvin",
            "Aydın", "Balıkesir", "Bilecik", "Bingöl", "Bitlis", "Bolu", "Burdur", "Bursa",
            "Çanakkale", "Çankırı", "Çorum", "Denizli", "Diyarbakır", "Edirne", "Elazığ",
            "Erzincan", "Erzurum", "Eskişehir", "Gaziantep", "Giresun", "Gümüşhane", "Hakkari",
            "Hatay", "Isparta", "Mersin", "İstanbul", "İzmir", "Kars", "Kastamonu", "Kayseri",
            "Kırklareli", "Kırşehir", "Kocaeli", "Konya", "Kütahya", "Malatya", "Manisa",
            "Kahramanmaraş", "Mardin", "Muğla", "Muş", "Nevşehir", "Niğde", "Ordu", "Rize",
            "Sakarya", "Samsun", "Siirt", "Sinop", "Sivas", "Tekirdağ", "Tokat", "Trabzon",
            "Tunceli", "Şanlıurfa", "Uşak", "Van", "Yozgat", "Zonguldak", "Aksaray", "Bayburt",
            "Karaman", "Kırıkkale", "Batman", "Şırnak", "Bartın", "Ardahan", "Iğdır", "Yalova",
            "Karabük", "Kilis", "Osmaniye", "Düzce", "Delft", "Girne", "London", "Salmiya",
        ]
        sorted_names = sorted(names, key=lambda x: x.lower())
        for idx, name in enumerate(sorted_names):
            code = name.upper().replace(" ", "-").replace("İ", "I").replace("Ş", "S").replace("Ğ", "G").replace("Ü", "U").replace("Ö", "O").replace("Ç", "C").replace("I", "I")
            db.add(models.City(code=code, name=name, active=True, sequence=idx))
        db.commit()
        logger.info(f"Seeded {len(names)} cities")
    except Exception as e:
        logger.error(f"Seed Cities Error: {e}")
    finally:
        db.close()


def _seed_specialties():
    db = SessionLocal()
    try:
        if db.query(models.Specialty).count() > 0:
            return
        names = [
            "Acil Tıp", "Aile Hekimliği", "Anesteziyoloji ve Reanimasyon", "Ağız ve Diş Sağlığı",
            "Beyin ve Sinir Cerrahisi (Nöroşirurji)", "Deri ve Zührevi Hastalıkları", "Diş Tabibi",
            "Enfeksiyon Hastalıkları ve Klinik Mikrobiyoloji", "Fiziksel Tıp ve Rehabilitasyon",
            "Gastroenteroloji", "Genel Cerrahisi", "Göz Hastalıkları", "Göğüs Cerrahisi",
            "Göğüs Hastalıkları", "Hematoloji", "Kadın Hastalıkları ve Doğum",
            "Kalp ve Damar Cerrahisi", "Kardiyoloji", "Kulak Burun Boğaz Hastalıkları",
            "Nefroloji", "Nöroloji", "Ortodonti", "Ortopedi ve Travmatoloji", "Perinatoloji",
            "Plastik Rekonstrüktif ve Estetik Cerrahi", "Pratisyen Tabip",
            "Radyasyon Onkolojisi", "Radyoloji (Radyodiyagnostik)", "Ruh Sağlığı ve Hastalıkları",
            "Spor Hekimliği", "Sualtı Hekimliği ve Hiperbarik Tip", "Tıbbi Biyokimya",
            "Tıbbi Patoloji", "Yoğun Bakım", "Çocuk Acil", "Çocuk Cerrahisi",
            "Çocuk Endokrinolojisi", "Çocuk Enfeksiyon Hastalıkları",
            "Çocuk Hematolojisi ve Onkolojisi", "Çocuk Nörolojisi",
            "Çocuk Sağlığı ve Hastalıkları", "Çocuk Ürolojisi", "Üroloji",
            "İç Hastalıkları", "Adli Tıp",
        ]
        sorted_names = sorted(names, key=lambda x: x.lower())
        for idx, name in enumerate(sorted_names):
            code = name[:20].upper().replace(" ", "-").replace("İ", "I").replace("Ş", "S").replace("Ğ", "G").replace("Ü", "U").replace("Ö", "O").replace("Ç", "C").replace("(", "").replace(")", "")
            db.add(models.Specialty(code=f"{code}-{idx}", name=name, active=True, sequence=idx))
        db.commit()
        logger.info(f"Seeded {len(names)} specialties")
    except Exception as e:
        logger.error(f"Seed Specialties Error: {e}")
    finally:
        db.close()


def _seed_client_categories():
    db = SessionLocal()
    try:
        if db.query(models.ClientCategory).count() > 0:
            return
        items = [
            ("DOKTOR", "Doktor"),
            ("KURUM", "Kurum"),
            ("OZEL-HASTANE", "Özel Hastane"),
            ("BIREYSEL", "Bireysel"),
            ("SIGORTA", "Sigorta Şirketi"),
            ("DIGER", "Diğer"),
        ]
        for idx, (code, name) in enumerate(items):
            db.add(models.ClientCategory(code=code, name=name, active=True, sequence=idx))
        db.commit()
        logger.info(f"Seeded {len(items)} client_categories")
    except Exception as e:
        logger.error(f"Seed ClientCategories Error: {e}")
    finally:
        db.close()


def _seed_file_statuses():
    db = SessionLocal()
    try:
        if db.query(models.FileStatus).count() > 0:
            return
        names = [
            "Aciz Vesikası", "Azil", "Bekletici Mesele/Ceza-Hukuk Dosyası",
            "Bekletici Mesele/MSK", "Bilirkişi Kusur Raporu Alındı",
            "Bilirkişi Maluliyet Raporu Alındı", "Bilirkişi Tazminat Raporu Alındı",
            "Bilirkişide", "Birleşme", "Bozma Sonrası Yargılama",
            "Dava Açılması Bekleniyor", "Davaya Dönüştü", "Deliller Toplanıyor",
            "Islah", "İade", "İncelemede", "İnfaz Haricen", "İnfaz İcradan",
            "İstifa", "İstinafta", "Kanun Yararına Bozmada",
            "Kapama Müvekkil Talimatıyla", "Karar Düzeltmede",
            "Karar Kesinleşmesi Bekleniyor", "Karar Tebliği Bekleniyor",
            "Karar Yazımı Bekleniyor", "Kesin Aleyhe", "Kesin Lehe",
            "Lexis Rapor Gönderildi", "Lexis Rapor Hazırlanıyor", "Müvekkil Vefatı",
            "Ön İnceleme", "Sözlü Yargılama", "Sulh İle Kapatma", "Tanık",
            "Tehiri İcra", "Temyizde", "Uyuşmazlık Mahkemesinde",
        ]
        for idx, name in enumerate(names):
            code = name.upper().replace(" ", "-").replace("/", "-").replace("İ", "I").replace("Ş", "S").replace("Ğ", "G").replace("Ü", "U").replace("Ö", "O").replace("Ç", "C")
            db.add(models.FileStatus(code=code, name=name, active=True, sequence=idx))
        db.commit()
        logger.info(f"Seeded {len(names)} file_statuses")
    except Exception as e:
        logger.error(f"Seed FileStatuses Error: {e}")
    finally:
        db.close()
