"""Avukat adı normalize / çözümleme motoru.

Davalardaki responsible_lawyer_name değerleri tutarsız formatlarda saklanmış:
  "Av. Serap Turgal" / "Serap Turgal" / "TUGCE UNGOR" / "Tuğçe Üngör Yanık" / "AGH" (kod)
Düz LIKE '%tam ad%' bu varyantları yakalayamıyordu. Burada her iki taraf da
ASCII'ye katlanıp ünvanlar atılarak token bazlı eşleştirilir.
"""
import logging
import re

import models
from managers.config_manager import DynamicConfig
from managers.reference_lists import get_lawyers

logger = logging.getLogger("AdminManager")

# Türkçe karakter katlama (ASCII, küçük harf)
_TR_FOLD = str.maketrans({
    "ı": "i", "İ": "i", "I": "i",
    "ş": "s", "Ş": "s",
    "ç": "c", "Ç": "c",
    "ğ": "g", "Ğ": "g",
    "ö": "o", "Ö": "o",
    "ü": "u", "Ü": "u",
    "â": "a", "Â": "a", "î": "i", "Î": "i", "û": "u", "Û": "u",
})

# Ünvan token'ları — eşleştirmede gürültü, atılır
_TITLE_TOKENS = {"av", "avk", "avukat", "stj", "stajyer", "dr", "prof"}

# Çoklu avukat ayraçları: virgül, noktalı virgül, eğik çizgi, &, " ve "
_PERSON_SPLIT = re.compile(r"\s*(?:,|;|/|&|\bve\b)\s*", re.IGNORECASE)


def _norm_name(s: str) -> str:
    """Adı ASCII küçük harfe katlar, noktalama + ünvanı atar, boşlukları sadeleştirir."""
    if not s:
        return ""
    s = s.translate(_TR_FOLD).lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    toks = [t for t in s.split() if t and t not in _TITLE_TOKENS]
    return " ".join(toks)


def _name_tokens(s: str) -> set:
    return set(_norm_name(s).split())


def _split_persons(s: str):
    """Çoklu avukat içeren bir alanı tekil kişilere böler."""
    if not s:
        return []
    return [p for p in _PERSON_SPLIT.split(s) if p and p.strip()]


def _resolve_lawyer_aliases(selected: str):
    """selected (kod veya ad) → config'teki avukatı çözer ve eşleştirme bilgisini döndürür.
    Dönen: (core_tokens, code_norm, surname, surname_unique) | None (çözülemezse)."""
    try:
        lawyers = DynamicConfig.get_instance().get_lawyers() or []
    except Exception:
        lawyers = []
    if not lawyers:
        return None
    sel_norm = _norm_name(selected)
    sel_code = _norm_name(selected)  # kodlar da normalize edilerek karşılaştırılır
    target = None
    for lw in lawyers:
        code_norm = _norm_name(lw.get("code") or "")
        name_norm = _norm_name(lw.get("name") or "")
        if (code_norm and code_norm == sel_code) or (name_norm and name_norm == sel_norm):
            target = lw
            break
    if target is None:
        return None
    core_tokens = _name_tokens(target.get("name") or "")
    code_norm = _norm_name(target.get("code") or "")
    name_toks = _norm_name(target.get("name") or "").split()
    surname = name_toks[-1] if name_toks else ""
    # Soyad config genelinde benzersiz mi? (tek-token kayıtları güvenle eşlemek için)
    surname_count = sum(
        1 for lw in lawyers
        if (_norm_name(lw.get("name") or "").split() or [""])[-1] == surname
    )
    return core_tokens, code_norm, surname, (surname_count == 1)


def _value_matches(value, core_tokens, code_norm, surname, surname_unique) -> bool:
    """Bir ad alanının (tekil veya çoklu) seçilen avukatla eşleşip eşleşmediği."""
    for part in _split_persons(value):
        ptoks = _name_tokens(part)
        if not ptoks:
            continue
        # 1) Kod birebir (ör. "AGH")
        if code_norm and code_norm in ptoks:
            return True
        # 2) En az 2 ortak token (ad+soyad veya ad+ikinci ad)
        if len(ptoks & core_tokens) >= 2:
            return True
        # 3) Tek-token kayıt yalnızca benzersiz soyadla eşleşir (ör. "Hanyaloğlu")
        if surname and surname_unique and ptoks == {surname}:
            return True
    return False


# --- Track B: Merkezi Avukat Çözümleyici (tüm yazma yollarının tek kapısı) ---
#
# Ham bir avukat metnini ("TUGCE UNGOR", "Serap Turgal", "AGH"…) config'teki tek bir
# avukata çözer. Yeni veri buradan geçince responsible_lawyer_name canonical olur ve
# case_lawyers.lawyer_id (yapısal bağ) dolar. Bulamazsa None → çağıran ham değeri korur.

def resolve_lawyer(raw_value: str, lawyers=None):
    """Tek kişilik ham avukat metnini config avukatına çözer. Dönen: lawyer dict | None.
    `lawyers` verilirse (ör. yazımın yapıldığı DB oturumundaki liste) config yerine o kullanılır."""
    if not raw_value or not str(raw_value).strip():
        return None
    if lawyers is None:
        try:
            lawyers = DynamicConfig.get_instance().get_lawyers() or []
        except Exception:
            lawyers = []
        if not lawyers:
            # Cache boş (ör. standalone script) → DB'den oku
            lawyers = get_lawyers() or []
    if not lawyers:
        return None
    ptoks = _name_tokens(raw_value)
    if not ptoks:
        return None
    # Benzersiz soyad haritası (tek-token kayıtları güvenle çözmek için)
    surname_count: dict = {}
    for lw in lawyers:
        tk = _norm_name(lw.get("name") or "").split()
        if tk:
            surname_count[tk[-1]] = surname_count.get(tk[-1], 0) + 1
    for lw in lawyers:
        core = _name_tokens(lw.get("name") or "")
        code = _norm_name(lw.get("code") or "")
        tk = _norm_name(lw.get("name") or "").split()
        sur = tk[-1] if tk else ""
        if code and code in ptoks:
            return lw
        if len(ptoks & core) >= 2:
            return lw
        if sur and surname_count.get(sur) == 1 and ptoks == {sur}:
            return lw
    return None


def resolve_lawyers_field(raw_value: str):
    """Çoklu avukat içerebilen bir alanı çözer.
    Dönen: [(lawyer_dict | None, ham_parça), …] — sıra ve tekrar korunur."""
    out = []
    seen = set()
    for part in _split_persons(raw_value):
        matched = resolve_lawyer(part)
        key = (matched.get("code") if matched else None) or _norm_name(part)
        if key in seen:
            continue
        seen.add(key)
        out.append((matched, part.strip()))
    return out


# --- Yazım koruması (kullanıcı kararı 27.09): avukat adı sistemde TEK yazımla durur ---
#
# Avukat adı yazan her yol (kart sorumlu/UYAP avukatı, duruşma, müvekkil vekil listesi,
# aktarım) değeri buradan geçirir: listedeki kişiye çözülen parça listedeki YAZIMA iner.
# Kullanıcı uçları ayrıca `listede_olmayan_yeni_adlar` ile listede karşılığı olmayan YENİ
# adı reddeder (değişmeden geri gelen eski değer engellenmez — eski kartlar kilitlenmesin).

class AvukatListedeYok(ValueError):
    """Kullanıcı ucuna listede karşılığı olmayan yeni avukat adı geldi (→ 422)."""

    def __init__(self, adlar):
        self.adlar = list(adlar)
        super().__init__(
            "Avukat listede yok: " + ", ".join(self.adlar)
            + " — önce Yönetim › Avukatlar'a ekleyin ya da listeden seçin."
        )


def _liste():
    try:
        lawyers = DynamicConfig.get_instance().get_lawyers() or []
    except Exception:
        lawyers = []
    return lawyers or (get_lawyers() or [])


def _tam_liste_adi(raw_value, lawyers=None):
    """Değerin TAMAMI listedeki bir adla (katlanmış) aynıysa o ad — "Hanyaloğlu & Acar"
    gibi ayraç içeren liste kayıtları bölünmeden tanınsın."""
    anahtar = _norm_name(raw_value or "")
    if not anahtar:
        return None
    for lw in (_liste() if lawyers is None else lawyers):
        if _norm_name(lw.get("name") or "") == anahtar:
            return lw.get("name")
    return None


def kanonik_avukat_adi(raw_value):
    """Tek kişilik adı listedeki yazıma çevirir; çözülemezse None."""
    tam = _tam_liste_adi(raw_value)
    if tam:
        return tam
    matched = resolve_lawyer(raw_value)
    return (matched.get("name") or None) if matched else None


def kanonik_avukat_metni(raw_value, ayirici: str = ";"):
    """Tek ya da çoklu avukat metnini parça parça listedeki yazıma indirir (toleranslı).

    Çözülen parça listedeki ad olur, çözülemeyen parça boşlukları sadeleşmiş hâliyle kalır;
    aynı kişi iki kez yazılmışsa bir kez kalır; sıra korunur. Boş girdi olduğu gibi döner.
    """
    if raw_value is None or not str(raw_value).strip():
        return raw_value
    tam = _tam_liste_adi(str(raw_value))
    if tam:
        return tam
    parcalar, gorulen = [], set()
    for parca in _split_persons(str(raw_value)):
        temiz = " ".join(parca.split())
        ad = kanonik_avukat_adi(temiz) or temiz
        anahtar = _norm_name(ad)
        if anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        parcalar.append(ad)
    return ayirici.join(parcalar)


def listede_olmayan_yeni_adlar(yeni_deger, onceki_deger=None, lawyers=None):
    """`yeni_deger`deki, listede karşılığı OLMAYAN ve `onceki_deger`de de bulunmayan parçalar.

    Avukat listesi TAMAMEN boşsa (yeni kurulum / liste yüklenmemiş ortam) doğrulanacak referans
    yoktur → boş döner (kayıt engellenmez; kanonik yazım yine uygulanır)."""
    if yeni_deger is None or not str(yeni_deger).strip():
        return []
    if lawyers is None:
        lawyers = _liste()
    if not lawyers:
        return []
    if _tam_liste_adi(str(yeni_deger), lawyers) or _norm_name(str(yeni_deger)) == _norm_name(str(onceki_deger or "")):
        return []
    onceki = {_norm_name(p) for p in _split_persons(str(onceki_deger or ""))}
    return [
        " ".join(p.split()) for p in _split_persons(str(yeni_deger))
        if resolve_lawyer(p, lawyers) is None and _norm_name(p) not in onceki
    ]


def canonicalize_lawyers(db, lawyers_input, responsible_text):
    """Yazma yolları için: gelen avukat girdisini canonical hale getirir.
    Girdi öncelik sırası: yapısal `lawyers` listesi → yoksa serbest `responsible_text`.
    Dönen: (case_lawyer_rows, canonical_responsible_name, unresolved_parts)
      - case_lawyer_rows: [{"name", "lawyer_id"}] (canonical ad + FK)
      - unresolved_parts: çözülemeyen ham parçalar (review için)
    """
    raws = []
    if lawyers_input:
        for lw in lawyers_input:
            nm = (lw or {}).get("name")
            if nm:
                raws.append(nm)
    elif responsible_text:
        tam = _tam_liste_adi(responsible_text)
        raws = [tam] if tam else list(_split_persons(responsible_text))

    rows, names, unresolved = [], [], []
    for raw in raws:
        tam = _tam_liste_adi(raw)
        matched = next((lw for lw in _liste() if lw.get("name") == tam), None) if tam else resolve_lawyer(raw)
        if matched:
            lid = None
            lrow = db.query(models.Lawyer).filter(models.Lawyer.code == matched.get("code")).first()
            if lrow:
                lid = lrow.id
            cname = matched.get("name") or raw
            if cname not in names:
                rows.append({"name": cname, "lawyer_id": lid})
                names.append(cname)
        else:
            # Çözülemedi → ham değeri koru ama işaretle
            if raw not in names:
                rows.append({"name": raw, "lawyer_id": None})
                names.append(raw)
                unresolved.append(raw)
    canonical = ", ".join(names) if names else None
    return rows, canonical, unresolved
