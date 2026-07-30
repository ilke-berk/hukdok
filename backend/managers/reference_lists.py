"""Referans listeleri için generic CRUD katmanı.

13 liste varlığı (avukat, durum, belge türü, …) aynı get/add/delete/reorder/
refresh davranışını paylaşır. Varlık başına kopyalanan üçlüler yerine tek
LIST_REGISTRY sözlüğü + generic fonksiyonlar kullanılır; route'ların beklediği
isimli sarmalayıcılar (get_lawyers, add_status, …) altta tanımlıdır.
"""
import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func

from database import SessionLocal
import models
from managers.config_manager import DynamicConfig

logger = logging.getLogger("AdminManager")


class DuplicateItemError(Exception):
    """Aynı isim/kod listede zaten varken ekleme girişimi (route katmanında 409'a çevrilir)."""


class ItemInUseError(Exception):
    """Silinmek istenen öğe bağlı kayıtlarda kullanılıyor (route katmanında 409'a çevrilir).

    usage: get_usage() çıktısı — arayüz "34 dava kullanıyor" uyarısını buradan kurar.
    """

    def __init__(self, message: str, usage: dict):
        super().__init__(message)
        self.usage = usage


def tr_upper(s: str) -> str:
    """Türkçe büyük harf — yalnızca harf duyarsız KARŞILAŞTIRMA için kullanılır.
    str.upper() 'i'yi 'I' yapar, önce 'İ'ye çevrilmeli. Boşluklar normalize edilir."""
    return " ".join(s.replace("i", "İ").upper().split())


def tr_lower(s: str) -> str:
    """Türkçe küçük harf: str.lower() 'İ'yi 'i̇' (i + combining dot) yapar."""
    return s.replace("İ", "i").replace("I", "ı").lower()


def tr_title(s: str) -> str:
    """Liste adlarının saklama formatı: her kelimenin ilk harfi büyük, kalanı
    küçük (Türkçe kurallarıyla: i→İ, ı→I). Boşluklar normalize edilir."""
    words = []
    for w in tr_lower(s).split():
        first = "İ" if w[0] == "i" else w[0].upper()
        words.append(first + w[1:])
    return " ".join(words)


def normalize_list_name(name: str) -> str:
    """Tüm referans listelerinin ad saklama formatı: her kelimenin ilk harfi büyük,
    kalanı küçük ("Doktor", "Özel Müvekkil"). Avukat ve e-posta alıcısı adları da
    dahil — istisna yoktur."""
    return tr_title(name)


@dataclass(frozen=True)
class ListSpec:
    model: type
    fields: tuple          # serialize edilen kolonlar
    setter: str            # DynamicConfig üzerindeki setter adı
    key: str = "code"      # add/delete/reorder kimlik kolonu
    order_by: tuple = ("sequence",)
    editable: tuple = ("name",)   # update_item ile düzenlenebilen kolonlar (kod hariç)


LIST_REGISTRY = {
    "lawyers":           ListSpec(models.Lawyer, ("code", "name", "tc_no", "sicil_no", "gorev", "email", "phone", "address", "city"), "set_lawyers",
                                  editable=("name", "tc_no", "sicil_no", "gorev", "email", "phone", "address", "city")),
    "statuses":          ListSpec(models.Status, ("code", "name"), "set_statuses"),
    "doctypes":          ListSpec(models.DocType, ("code", "name"), "set_doctypes"),
    "case_subjects":     ListSpec(models.CaseSubject, ("code", "name"), "set_case_subjects"),
    "emails":            ListSpec(models.EmailRecipient, ("name", "email", "description"), "set_email_recipients", key="email",
                                  editable=("name", "email", "description")),
    "file_types":        ListSpec(models.FileType, ("code", "name"), "set_file_types"),
    "court_types":       ListSpec(models.CourtType, ("code", "name", "parent_code"), "set_court_types", order_by=("parent_code", "sequence"),
                                  editable=("name", "parent_code")),
    "party_roles":       ListSpec(models.PartyRole, ("code", "name", "role_type"), "set_party_roles",
                                  editable=("name", "role_type")),
    "bureau_types":      ListSpec(models.BureauType, ("code", "name"), "set_bureau_types"),
    "cities":            ListSpec(models.City, ("code", "name"), "set_cities"),
    "specialties":       ListSpec(models.Specialty, ("code", "name"), "set_specialties"),
    "client_categories": ListSpec(models.ClientCategory, ("code", "name"), "set_client_categories"),
    "file_statuses":     ListSpec(models.FileStatus, ("code", "name"), "set_file_statuses"),
}

# refresh_cache("email_recipients") gibi eski çağrılar için takma adlar
_ALIASES = {"email_recipients": "emails"}


@dataclass(frozen=True)
class DepSpec:
    """Liste öğesinin adının denormalize saklandığı yer.

    Dava/müvekkil/belge kayıtları listelere FK ile bağlı değil, adın kopyasını
    taşır. Eşleşme ve güncelleme bu kolon üzerinden yapılır:
      - yeniden adlandırma → kolon yeni ada çevrilir
      - silme → kolon boşaltılır ya da başka bir öğenin adına taşınır
    code_column : satır kodu da taşıyorsa (belge türü) adla birlikte güncellenir
    clearable   : kolon NOT NULL ise False — silmede boşaltılamaz, yalnızca taşınabilir
    """
    model: type
    column: str
    label: str
    clearable: bool = True
    code_column: Optional[str] = None


# Her liste için "bu adı kim taşıyor?" haritası. Yeniden adlandırma yayılımı,
# kullanım sayımı ve silme davranışı tek kaynaktan bu tabloyu okur.
#
# clearable=False olanlar: kolon NOT NULL ya da okuma şeması (CaseRead/CasePartyCreate)
# değeri zorunlu görüyor — boşaltılırsa dava listesi hata verir. Bu satırlar ancak
# başka bir öğeye taşınarak silinebilir.
DEPENDENCIES = {
    # Durumlar BELGE durumudur (Gelen Belge / Final / …); kodu analiz sonucuna ve
    # dosya adına gider, hiçbir kolonda saklanmaz. cases.status ise MAHZEN/DERDEST
    # tutar ve bu listeyle ilgisizdir — eski RENAME_PROPAGATION'daki eşleme yanlıştı
    # (hiç eşleşmiyordu; bir durum "Mahzen" olarak adlandırılsaydı 11k davayı bozardı).
    "statuses":          [],
    "bureau_types":      [DepSpec(models.Case, "bureau_type", "dava")],
    "file_types":        [DepSpec(models.Case, "file_type", "dava"),
                          DepSpec(models.CourtType, "parent_code", "mahkeme türü", clearable=False)],
    "court_types":       [DepSpec(models.Case, "sub_type", "dava")],
    "case_subjects":     [DepSpec(models.Case, "subject", "dava")],
    "file_statuses":     [DepSpec(models.Case, "dosya_son_durumu", "dava")],
    "client_categories": [DepSpec(models.Client, "category", "müvekkil")],
    # Uzmanlıklar hem müvekkil kartında hem davanın alt tür alanlarında kullanılıyor
    "specialties":       [DepSpec(models.Client, "specialty", "müvekkil"),
                          DepSpec(models.Case, "sub_type", "dava (alt tür)"),
                          DepSpec(models.Case, "sub_type_extra", "dava (ek alt kırılım)")],
    "doctypes":          [DepSpec(models.CaseDocument, "belge_turu_adi", "belge", code_column="belge_turu_kodu")],
    "party_roles":       [DepSpec(models.CaseParty, "role", "dava tarafı", clearable=False)],
    "cities":            [DepSpec(models.Client, "il", "müvekkil"),
                          DepSpec(models.Lawyer, "city", "avukat")],
    "lawyers":           [DepSpec(models.Case, "responsible_lawyer_name", "dava (sorumlu avukat)"),
                          DepSpec(models.Case, "uyap_lawyer_name", "dava (UYAP avukatı)"),
                          DepSpec(models.CaseLawyer, "name", "dava avukatı", clearable=False)],
    "emails":            [],
}


def _spec(list_type: str):
    return LIST_REGISTRY.get(_ALIASES.get(list_type, list_type))


def resolve_list_type(list_type: str) -> Optional[str]:
    """Takma adı çözer ve listenin tanımlı olduğunu doğrular; bilinmiyorsa None."""
    key = _ALIASES.get(list_type, list_type)
    return key if key in LIST_REGISTRY else None


# Excel çıktısında ve arayüzde kullanılan Türkçe başlıklar
LIST_TITLES = {
    "lawyers": "Avukatlar", "statuses": "Durumlar", "doctypes": "Belge Türleri",
    "case_subjects": "Dava Konuları", "emails": "E-posta Alıcıları",
    "file_types": "Dava Türleri", "court_types": "Mahkemeler",
    "party_roles": "Taraf Rolleri", "bureau_types": "Büro Türleri",
    "cities": "Şehirler", "specialties": "Uzmanlıklar",
    "client_categories": "Kategoriler", "file_statuses": "Dosya Durumları",
}

COLUMN_TITLES = {
    "code": "Kod", "name": "Ad", "tc_no": "T.C. No", "sicil_no": "Baro Sicil No",
    "gorev": "Görev", "email": "E-posta", "phone": "Telefon", "address": "Adres",
    "city": "Şehir", "description": "Rol", "parent_code": "Dava Türü",
    "role_type": "Tür",
}


def _name_variants(name: str) -> list:
    """Eşleşmede denenecek yazım biçimleri.

    Eski/Excel'den gelen kayıtlar aynı değeri BÜYÜK HARFLE saklamış olabiliyor
    ("DOKTOR" ↔ "Doktor"). Tam eşleşme bunları ıskalayacağı için adın yaygın
    biçimleri birlikte aranır."""
    return [v for v in {name, tr_upper(name), tr_lower(name), tr_title(name)} if v]


# ─── GENERIC CRUD ────────────────────────────────────────────────────────────

def get_items(list_type: str, extra_filter=None):
    """Aktif kayıtları sıra numarasına göre listeler ve dict'e serialize eder."""
    spec = _spec(list_type)
    if not spec:
        return []
    db = None
    try:
        db = SessionLocal()
        q = db.query(spec.model).filter(spec.model.active.is_(True))
        if extra_filter is not None:
            q = q.filter(extra_filter)
        items = q.order_by(*(getattr(spec.model, col).asc() for col in spec.order_by)).all()
        return [{f: getattr(i, f) for f in spec.fields} for i in items]
    except Exception as e:
        logger.error(f"Error fetching {list_type}: {e}")
        return []
    finally:
        if db is not None:
            db.close()


def add_item(list_type: str, **fields):
    spec = _spec(list_type)
    if not spec:
        return False
    if fields.get("name"):
        fields["name"] = normalize_list_name(fields["name"])
    db = None
    try:
        db = SessionLocal()

        # Mükerrer isim kontrolü (büyük/küçük harf duyarsız; mahkeme türleri
        # aynı ada farklı üst tür altında izin verdiği için parent'a göre daraltılır)
        if fields.get("name"):
            target = tr_upper(fields["name"])
            q = db.query(spec.model)
            if "parent_code" in fields:
                q = q.filter(spec.model.parent_code == fields["parent_code"])
            for row in q.all():
                if tr_upper(getattr(row, "name", None) or "") == target:
                    raise DuplicateItemError(f"\"{fields['name']}\" zaten listede mevcut")

        # Mükerrer kod kontrolü
        identifier = fields.get(spec.key)
        if identifier and db.query(spec.model).filter(getattr(spec.model, spec.key) == identifier).first():
            raise DuplicateItemError(f"\"{identifier}\" kodu zaten listede mevcut")

        db.add(spec.model(active=True, **fields))
        db.commit()
        refresh_cache(list_type)
        return True
    except DuplicateItemError:
        raise
    except Exception as e:
        logger.error(f"Add {list_type} Error: {e}")
        return False
    finally:
        if db is not None:
            db.close()


def get_usage(list_type: str, identifier: str):
    """Öğenin adını taşıyan bağlı kayıtları sayar.

    Dönüş: {"name", "total", "items": [{"label", "count", "clearable"}], "clearable"}
    | None (öğe bulunamadı). clearable=False ise bağlı kolon NOT NULL'dur; silmede
    boşaltılamaz, yalnızca başka bir öğeye taşınabilir.
    """
    spec = _spec(list_type)
    if not spec:
        return None
    key = _ALIASES.get(list_type, list_type)
    db = None
    try:
        db = SessionLocal()
        item = db.query(spec.model).filter(getattr(spec.model, spec.key) == identifier).first()
        if not item:
            return None
        name = getattr(item, "name", None)
        rows = []
        if name:
            variants = _name_variants(name)
            for dep in DEPENDENCIES.get(key, []):
                count = (
                    db.query(func.count())
                    .select_from(dep.model)
                    .filter(getattr(dep.model, dep.column).in_(variants))
                    .scalar()
                ) or 0
                if count:
                    rows.append({"label": dep.label, "count": count, "clearable": dep.clearable})
        return {
            "name": name,
            "total": sum(r["count"] for r in rows),
            "items": rows,
            "clearable": all(r["clearable"] for r in rows),
        }
    except Exception as e:
        logger.error(f"Usage {list_type} Error: {e}")
        return None
    finally:
        if db is not None:
            db.close()


def _apply_to_dependents(db, key: str, old_name: str, new_name, new_code=None) -> int:
    """Bağlı kayıtlardaki denormalize adı yeni değere çevirir (None → boşaltır).
    Etkilenen satır sayısını döner."""
    if not old_name:
        return 0
    variants = _name_variants(old_name)
    affected = 0
    for dep in DEPENDENCIES.get(key, []):
        values = {dep.column: new_name}
        if dep.code_column:
            values[dep.code_column] = new_code
        affected += (
            db.query(dep.model)
            .filter(getattr(dep.model, dep.column).in_(variants))
            .update(values, synchronize_session=False)
        )
    return affected


def delete_item(list_type: str, identifier: str, mode: str = "block", target: str = None):
    """Liste öğesini siler. Bağlı kayıtlara ne olacağı mode ile belirlenir:

      "block"    — bağlı kayıt varsa silme reddedilir (ItemInUseError)
      "clear"    — bağlı kayıtlarda alan boşaltılır (NULL)
      "reassign" — bağlı kayıtlar target koduyla verilen öğeye taşınır
      "keep"     — bağlı kayıtlara dokunulmaz (eski davranış; ad kayıtta asılı kalır)

    Dönüş: {"affected": n} | False (öğe yok / hata).
    """
    spec = _spec(list_type)
    if not spec:
        return False
    key = _ALIASES.get(list_type, list_type)
    db = None
    try:
        db = SessionLocal()
        key_col = getattr(spec.model, spec.key)
        item = db.query(spec.model).filter(key_col == identifier).first()
        if not item:
            return False
        # name'siz modelde (olmamalı) identifier'a düş — mesajlar ve
        # bağımlı kayıt eşleştirmesi str bekler
        old_name = getattr(item, "name", None) or str(identifier)

        affected = 0
        if mode in ("block", "clear"):
            usage = get_usage(key, identifier) or {"total": 0, "clearable": True, "items": []}
            if usage["total"]:
                if mode == "block":
                    raise ItemInUseError(f"\"{old_name}\" {usage['total']} kayıtta kullanılıyor", usage)
                if not usage["clearable"]:
                    blocking = ", ".join(r["label"] for r in usage["items"] if not r["clearable"])
                    raise ItemInUseError(
                        f"\"{old_name}\" zorunlu alanlarda kullanılıyor ({blocking}); "
                        "boşaltılamaz, önce başka bir kayda taşıyın", usage
                    )
                affected = _apply_to_dependents(db, key, old_name, None, None)
        elif mode == "reassign":
            if not target or target == identifier:
                return False
            new_item = db.query(spec.model).filter(key_col == target).first()
            if not new_item:
                return False
            affected = _apply_to_dependents(db, key, old_name, new_item.name, getattr(new_item, "code", None))

        db.delete(item)
        db.commit()
        refresh_cache(key)
        if key == "file_types":
            refresh_cache("court_types")
        logger.info(f"Delete {key}: {old_name!r} (mode={mode}, {affected} kayıt etkilendi)")
        return {"affected": affected}
    except ItemInUseError:
        raise
    except Exception as e:
        logger.error(f"Delete {list_type} Error: {e}")
        return False
    finally:
        if db is not None:
            db.close()


def update_item(list_type: str, identifier: str, fields: dict):
    """Liste öğesinin düzenlenebilir alanlarını günceller.

    Ad değişirse eski adı taşıyan dava/müvekkil/belge kayıtlarına yayılır
    (bkz. DEPENDENCIES). Kod alanı kimlik olduğu ve arşivdeki dosya adlarında
    geçtiği için düzenlenmez.

    Dönüş: {"updated": yansıyan_kayıt} | None (öğe bulunamadı) | False (hata).
    Aynı ada/koda sahip başka öğe varsa DuplicateItemError yükseltir.
    """
    spec = _spec(list_type)
    if not spec:
        return False
    key = _ALIASES.get(list_type, list_type)

    fields = {k: v for k, v in (fields or {}).items() if k in spec.editable and v is not None}
    if not fields:
        return {"updated": 0}

    # Kimlik kolonu (e-posta alıcılarında e-posta) boşaltılamaz
    if spec.key in fields and not fields[spec.key].strip():
        return False

    if "name" in fields:
        new_name = normalize_list_name(fields["name"])
        if not new_name:
            return False
        fields["name"] = new_name

    db = None
    try:
        db = SessionLocal()
        key_col = getattr(spec.model, spec.key)
        item = db.query(spec.model).filter(key_col == identifier).first()
        if not item:
            return None
        old_name = getattr(item, "name", None)
        new_name = fields.get("name")

        # Mükerrer ad kontrolü — kendisi hariç, harf duyarsız. Mahkeme türlerinde
        # aynı ad farklı üst tür altında serbest olduğu için parent'a göre daraltılır.
        if new_name and (not old_name or tr_upper(new_name) != tr_upper(old_name)):
            target_name = tr_upper(new_name)
            q = db.query(spec.model).filter(key_col != identifier)
            if key == "court_types":
                q = q.filter(spec.model.parent_code == fields.get("parent_code", item.parent_code))
            for row in q.all():
                if tr_upper(getattr(row, "name", None) or "") == target_name:
                    raise DuplicateItemError(f"\"{new_name}\" zaten listede mevcut")

        # Kimlik kolonu düzenlenebiliyorsa (e-posta alıcıları) mükerrer kontrolü
        new_key = fields.get(spec.key)
        if new_key and new_key != identifier:
            if db.query(spec.model).filter(key_col == new_key).first():
                raise DuplicateItemError(f"\"{new_key}\" zaten listede mevcut")

        for field, value in fields.items():
            setattr(item, field, value if field == "name" else (value or None))

        updated = 0
        if new_name and old_name and new_name != old_name:
            updated = _apply_to_dependents(db, key, old_name, new_name, getattr(item, "code", None))

        db.commit()
        refresh_cache(key)
        if key == "file_types":
            # Dava türü adı mahkeme türlerinin parent_code'unda da geçer
            refresh_cache("court_types")
        logger.info(f"Update {key}: {identifier!r} {list(fields)} ({updated} kayıt yansıtıldı)")
        return {"updated": updated}
    except DuplicateItemError:
        raise
    except Exception as e:
        logger.error(f"Update {list_type} Error: {e}")
        return False
    finally:
        if db is not None:
            db.close()


def rename_item(list_type: str, identifier: str, new_name: str):
    """Yalnızca adı değiştiren ince sarmalayıcı (eski /api/config/rename yolu)."""
    return update_item(list_type, identifier, {"name": new_name})


def reorder_list(list_type: str, ordered_ids: list):
    spec = _spec(list_type)
    if not spec:
        return False
    db = None
    try:
        db = SessionLocal()
        key_col = getattr(spec.model, spec.key)
        for idx, identifier in enumerate(ordered_ids):
            item = db.query(spec.model).filter(key_col == identifier).first()
            if item:
                item.sequence = idx
        db.commit()
        refresh_cache(list_type)
        return True
    except Exception as e:
        logger.error(f"Reorder Error: {e}")
        return False
    finally:
        if db is not None:
            db.close()


def refresh_cache(list_type: str):
    """DynamicConfig singleton'ını restart gerektirmeden günceller."""
    key = _ALIASES.get(list_type, list_type)
    spec = LIST_REGISTRY.get(key)
    if not spec:
        return
    config = DynamicConfig.get_instance()
    getattr(config, spec.setter)(get_items(key))


# ─── İSİMLİ SARMALAYICILAR (route'ların import ettiği API) ───────────────────

def get_lawyers():           return get_items("lawyers")
def get_statuses():          return get_items("statuses")
def get_doctypes():          return get_items("doctypes")
def get_case_subjects():     return get_items("case_subjects")
def get_email_recipients():  return get_items("emails")
def get_file_types():        return get_items("file_types")
def get_party_roles():       return get_items("party_roles")
def get_bureau_types():      return get_items("bureau_types")
def get_cities():            return get_items("cities")
def get_specialties():       return get_items("specialties")
def get_client_categories(): return get_items("client_categories")
def get_file_statuses():     return get_items("file_statuses")


def get_court_types(parent_code: str = None):
    extra = models.CourtType.parent_code == parent_code if parent_code else None
    return get_items("court_types", extra_filter=extra)


def add_lawyer(code: str, name: str, tc_no: str = None, sicil_no: str = None,
               gorev: str = None, email: str = None, phone: str = None,
               address: str = None, city: str = None):
    return add_item("lawyers", code=code, name=name,
                    tc_no=tc_no or None, sicil_no=sicil_no or None,
                    gorev=gorev or None, email=email or None,
                    phone=phone or None, address=address or None,
                    city=city or None)


def update_lawyer(code: str, tc_no: str = None, sicil_no: str = None,
                  gorev: str = None, email: str = None, phone: str = None, address: str = None):
    """Avukat alanlarını günceller (eski PUT /api/config/lawyers/{code} yolu)."""
    result = update_item("lawyers", code, {
        "tc_no": tc_no, "sicil_no": sicil_no, "gorev": gorev,
        "email": email, "phone": phone, "address": address,
    })
    return bool(result)


def add_status(code: str, name: str):           return add_item("statuses", code=code, name=name)
def add_doctype(code: str, name: str):          return add_item("doctypes", code=code, name=name)
def add_case_subject(code: str, name: str):     return add_item("case_subjects", code=code, name=name)
def add_file_type(code: str, name: str):        return add_item("file_types", code=code, name=name)
def add_bureau_type(code: str, name: str):      return add_item("bureau_types", code=code, name=name)
def add_city(code: str, name: str):             return add_item("cities", code=code, name=name)
def add_specialty(code: str, name: str):        return add_item("specialties", code=code, name=name)
def add_client_category(code: str, name: str):  return add_item("client_categories", code=code, name=name)
def add_file_status(code: str, name: str):      return add_item("file_statuses", code=code, name=name)


def add_court_type(code: str, name: str, parent_code: str):
    return add_item("court_types", code=code, name=name, parent_code=parent_code)


def add_party_role(code: str, name: str, role_type: str = "MAIN"):
    return add_item("party_roles", code=code, name=name, role_type=role_type)


def add_email_recipient(name: str, email: str, description: str = ""):
    db = None
    try:
        db = SessionLocal()
        existing = db.query(models.EmailRecipient).filter(models.EmailRecipient.email == email).first()
        if existing:
            if not existing.active:
                existing.active = True
                existing.name = name
                existing.description = description
                db.commit()
                refresh_cache("emails")
                return True
            raise DuplicateItemError(f"\"{email}\" zaten listede mevcut")

        max_seq = db.query(func.max(models.EmailRecipient.sequence)).scalar()
        new_seq = (max_seq if max_seq is not None else -1) + 1

        new_item = models.EmailRecipient(name=name, email=email, description=description, active=True, sequence=new_seq)
        db.add(new_item)
        db.commit()
        refresh_cache("emails")
        return True
    except DuplicateItemError:
        raise
    except Exception as e:
        logger.error(f"Add Email Error: {e}")
        return False
    finally:
        if db is not None:
            db.close()


def delete_lawyer(code: str):           return delete_item("lawyers", code)
def delete_status(code: str):           return delete_item("statuses", code)
def delete_doctype(code: str):          return delete_item("doctypes", code)
def delete_case_subject(code: str):     return delete_item("case_subjects", code)
def delete_email_recipient(email: str): return delete_item("emails", email)
def delete_file_type(code: str):        return delete_item("file_types", code)
def delete_court_type(code: str):       return delete_item("court_types", code)
def delete_party_role(code: str):       return delete_item("party_roles", code)
def delete_bureau_type(code: str):      return delete_item("bureau_types", code)
def delete_city(code: str):             return delete_item("cities", code)
def delete_specialty(code: str):        return delete_item("specialties", code)
def delete_client_category(code: str):  return delete_item("client_categories", code)
def delete_file_status(code: str):      return delete_item("file_statuses", code)
