"""Avukat adı normalize / çözümleme motoru.

Davalardaki responsible_lawyer_name değerleri tutarsız formatlarda saklanmış:
  "Av. Serap Turgal" / "Serap Turgal" / "TUGCE UNGOR" / "Tuğçe Üngör Yanık"
Düz LIKE '%tam ad%' bu varyantları yakalayamıyordu. Burada her iki taraf da
ASCII'ye katlanıp ünvanlar atılarak token bazlı eşleştirilir.

G228 (27.09): avukat KODU artık ad metninde eşleşme token'ı DEĞİLDİR — kod gizli ve
sunucu üretimidir, kimlik `lawyers.kimlik` (`AVK-00001`). Ölçüm (lokal, 27.09): kart
sorumlu/UYAP avukatı, `case_lawyers.name` ve duruşma avukatı alanlarında kod biçimli
değer 0; üstelik "ABDULLAH" gibi kodlar sıradan ad token'ıydı (yanlış pozitif kaynağı).
Seçim (filtre girdisi) düzeyinde kimlik, ad ve — 1 sürüm geriye uyum için — eski kod
avukatı bulur; eşleşmenin kendisi daima AD üzerinden yürür.
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


def _secimdeki_avukat(selected: str, lawyers):
    """Filtre seçimini (kimlik · ad · eski kod) listedeki avukat kaydına çevirir; yoksa None.

    Öncelik kimlik (`AVK-00001`, harf duyarsız) → normalize ad → eski kod. Eski kod YALNIZ
    seçim düzeyinde tanınır (1 sürüm geriye uyum: eski yer imleri/URL'ler; G231'de kalkar) —
    kart metninde kod token'ı ARANMAZ.
    """
    secim = (selected or "").strip()
    if not secim:
        return None
    kimlik = secim.upper()
    for lw in lawyers:
        if lw.get("kimlik") and str(lw.get("kimlik")).upper() == kimlik:
            return lw
    sel_norm = _norm_name(secim)
    if not sel_norm:
        return None
    for lw in lawyers:
        if _norm_name(lw.get("name") or "") == sel_norm:
            return lw
    # GERİYE UYUM (G228 → G231'de kalkar): eski `?lawyer=<kod>` değeri.
    for lw in lawyers:
        if _norm_name(lw.get("code") or "") == sel_norm:
            return lw
    return None


def _resolve_lawyer_aliases(selected: str):
    """selected (kimlik, ad ya da eski kod) → config'teki avukatı çözer ve AD eşleştirme bilgisini döndürür.
    Dönen: (core_tokens, code_norm, surname, surname_unique) | None (çözülemezse).

    G228: `code_norm` daima "" — kod artık eşleşme token'ı değildir. Demet biçimi çağıranlar
    (`case_manager._lawyer_filter_case_ids`, ön-eleme) için korunur; G231 alanı kaldırır."""
    try:
        lawyers = DynamicConfig.get_instance().get_lawyers() or []
    except Exception:
        lawyers = []
    if not lawyers:
        return None
    target = _secimdeki_avukat(selected, lawyers)
    if target is None:
        return None
    core_tokens = _name_tokens(target.get("name") or "")
    name_toks = _norm_name(target.get("name") or "").split()
    surname = name_toks[-1] if name_toks else ""
    # Soyad config genelinde benzersiz mi? (tek-token kayıtları güvenle eşlemek için)
    surname_count = sum(
        1 for lw in lawyers
        if (_norm_name(lw.get("name") or "").split() or [""])[-1] == surname
    )
    return core_tokens, "", surname, (surname_count == 1)


def _value_matches(value, core_tokens, code_norm, surname, surname_unique) -> bool:
    """Bir ad alanının (tekil veya çoklu) seçilen avukatla eşleşip eşleşmediği.

    Kurallar yalnız ADA bakar. `code_norm` parametresi imza uyumu için durur ve YOK
    SAYILIR (G228: kod token eşlemesi kaldırıldı; G231 parametreyi siler)."""
    del code_norm
    for part in _split_persons(value):
        ptoks = _name_tokens(part)
        if not ptoks:
            continue
        # 1) En az 2 ortak token (ad+soyad veya ad+ikinci ad)
        if len(ptoks & core_tokens) >= 2:
            return True
        # 2) Tek-token kayıt yalnızca benzersiz soyadla eşleşir (ör. "Hanyaloğlu")
        if surname and surname_unique and ptoks == {surname}:
            return True
    return False


# --- Track B: Merkezi Avukat Çözümleyici (tüm yazma yollarının tek kapısı) ---
#
# Ham bir avukat metnini ("TUGCE UNGOR", "Serap Turgal"…) config'teki tek bir avukata
# çözer. Yeni veri buradan geçince responsible_lawyer_name canonical olur ve
# case_lawyers.lawyer_id (yapısal bağ) dolar. Bulamazsa None → çağıran ham değeri korur.
# G228: avukat kodu ("AGH") artık çözülmez — yalnız ad kuralları.

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
        tk = _norm_name(lw.get("name") or "").split()
        sur = tk[-1] if tk else ""
        if len(ptoks & core) >= 2:
            return lw
        if sur and surname_count.get(sur) == 1 and ptoks == {sur}:
            return lw
    return None


def _avukat_anahtari(lw) -> str:
    """Tekilleştirme anahtarı: kurumsal kimlik; kimliksiz kayıtta (test/eski önbellek) normalize ad."""
    return str(lw.get("kimlik") or "") or "ad:" + _norm_name(lw.get("name") or "")


def resolve_lawyers_field(raw_value: str):
    """Çoklu avukat içerebilen bir alanı çözer.
    Dönen: [(lawyer_dict | None, ham_parça), …] — sıra ve tekrar korunur."""
    out = []
    seen = set()
    for part in _split_persons(raw_value):
        matched = resolve_lawyer(part)
        key = _avukat_anahtari(matched) if matched else _norm_name(part)
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


def secimi_liste_adina_cevir(selected, lawyers=None):
    """Filtre SEÇİMİNİ (kimlik · ad · eski kod) listedeki avukat adına çevirir; çözülemezse None.

    Dava listesi filtresiyle (`_resolve_lawyer_aliases`) AYNI seçim sözleşmesi: önce
    `_secimdeki_avukat` (kimlik harf duyarsız → normalize ad → eski kod), sonra toleranslı
    ad çözümü (`kanonik_avukat_adi`, örn. "TUGCE UNGOR"). Eski kod YALNIZ seçim düzeyinde
    1 sürüm geriye uyumludur (G231'de `_secimdeki_avukat`tan kalkınca burada da kalkar).
    Pasif avukatın kimliği aktif listede yoktur → çağıran önce DB'den ada çevirir
    (`case_manager._kimligi_ada_cevir`, G233)."""
    secim = (selected or "").strip()
    if not secim:
        return None
    liste = _liste() if lawyers is None else lawyers
    hedef = _secimdeki_avukat(secim, liste)
    if hedef is not None and hedef.get("name"):
        return hedef.get("name")
    return kanonik_avukat_adi(secim)


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


def _avukat_id(db, lw):
    """Çözülen avukatın `lawyers.id`'si — bağ KİMLİKLE kurulur (G228; kod araması kalktı).
    Kimliksiz kayıtta (eski önbellek / test sözlüğü) None — bağ kurulmaz, ad yine yazılır."""
    kimlik = lw.get("kimlik")
    if not kimlik:
        return None
    lrow = db.query(models.Lawyer).filter(models.Lawyer.kimlik == kimlik).first()
    return lrow.id if lrow else None


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
            lid = _avukat_id(db, matched)
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
