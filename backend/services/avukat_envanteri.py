"""Avukat envanteri — avukat kimliği geçişinin DAVA KORUMA kanıtı (G224).

**Kullanıcı şartı (27.09):** avukat kimliği geçişinde (kodlar kalkar → kurumsal
kimlik, G225-G231) **hiçbir dava kaybolmamalı**. "Kaybolmak" burada şemadan
çok ekrandan tanımlıdır: bir avukat dava listesinde kendini seçtiğinde dün
gördüğü davayı bugün görmüyorsa dava onun için kaybolmuştur — kayıt DB'de
dursa bile. Bu yüzden ölçüm, filtrenin KENDİSİNİ koşturur
(`case_manager._lawyer_filter_case_ids`); ona ek olarak ham bağları sayar
(sorumlu avukat metni, `case_lawyers` satırları, belgelerin avukat kodu).

Desen `services/belge_envanteri.py` ile aynıdır: her veri adımından ÖNCE
fotoğraf, adımdan SONRA fotoğraf, `karsilastir` İHLAL döndürürse adım geri
alınır. Burası ölçümdür, karar değil.

**Önbellek tuzağı (27.09 ölçümü):** filtre avukatı DB'den değil süreç-içi
`DynamicConfig` önbelleğinden çözer. Uygulama açılışta önbelleği doldurur ama
tek başına koşan bir betikte önbellek BOŞTUR → çözümleme `None` döner, filtre
"kod metni ad içinde geçiyor mu" yedeğine düşer ve neredeyse her avukat için 0
sayar. Sahte bir "hepsi 0 → hepsi 0, denk" fotoğrafı en tehlikeli sonuçtur.
`olc` bu yüzden önbelleği ÖLÇTÜĞÜ oturumdan, uygulamanın doldurduğu biçimde
(aktif avukatlar, sıra numarasına göre, `LIST_REGISTRY` alanları) doldurur ve
iş bitince eski içeriğe geri koyar. Bekçi: `tests/test_avukat_envanteri.py`.

Avukat anahtarı: G225 sonrası `lawyers.kimlik`, öncesi `lawyers.code` —
kayıt ikisini de taşır; karşılaştırmada eşleşme kimlik → kod → ad sırasıyladır
(geçiş boyunca kod değişmez, ad değişebilir). G226 sonrası `case_documents.lawyer_id`
varsa belge sayımı onu da kullanır; kolon yokken yalnız `avukat_kodu` sayılır.

Salt okunurdur — hiçbir tabloya yazmaz, commit etmez.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy import func

import models
from managers.case_manager import _lawyer_filter_case_ids
from managers.config_manager import DynamicConfig
from managers.lawyer_resolver import _norm_name, _split_persons
from managers.reference_lists import LIST_REGISTRY

SURUM = 1

IHLAL = "IHLAL"
BILGI = "BILGI"

# Avukat başına düşüşü İHLAL olan sayımlar (artışı BİLGİ).
AVUKAT_SAYIMLARI = ("filtre_dava", "sorumlu_kart", "case_lawyers", "case_lawyers_bagli", "belge")

# Toplamlar: düşüşü İHLAL olanlar. `case_lawyers_bagsiz` bilinçli olarak YOK —
# geçişin amacı bağsız satırları bağlamaktır, azalması beklenen sonuçtur.
TOPLAM_KORUNAN = (
    "aktif_dava", "sorumlu_dolu_dava", "case_lawyers_satir", "case_lawyers_bagli", "avukatli_belge",
)

ALAN_ETIKETI = {
    "filtre_dava": "dava listesi filtresinin bulduğu aktif dava",
    "sorumlu_kart": "sorumlu avukatı bu kişi olan aktif kart",
    "case_lawyers": "case_lawyers satırı",
    "case_lawyers_bagli": "bağlı (lawyer_id dolu) case_lawyers satırı",
    "belge": "belge",
    "aktif_dava": "aktif dava",
    "sorumlu_dolu_dava": "sorumlu avukatı dolu aktif dava",
    "case_lawyers_satir": "case_lawyers satırı",
    "avukatli_belge": "avukatlı belge",
    "case_lawyers_bagsiz": "bağsız case_lawyers satırı",
}


# ─── Ölçüm ───────────────────────────────────────────────────────────────────

def olc(db) -> Dict[str, Any]:
    """Avukat envanterinin anlık görüntüsü (JSON'a yazılabilir sözlük).

    Dönen: ``{"surum", "olculme_zamani", "avukatlar": {anahtar: kayit}, "toplamlar"}``.
    Kayıt: ``kimlik, code, ad, aktif, filtre_dava, sorumlu_kart, case_lawyers,
    case_lawyers_bagli, belge``.
    """
    avukatlar = _avukat_satirlari(db)
    aktif_ids, kart_normlari, sorumlu_dolu = _aktif_kartlar(db)
    cl_bagli, cl_bagsiz_norm, cl_bagsiz_ham, cl_toplam = _case_lawyers(db)
    belge_id_sayim, belge_norm_sayim, avukatli_belge = _belgeler(db)

    # Norm → o normu taşıyan aktif kartlar (bir kart birden çok norm taşıyabilir).
    norm_kartlari: Dict[str, Set[int]] = defaultdict(set)
    for cid, normlar in kart_normlari.items():
        for n in normlar:
            norm_kartlari[n].add(cid)

    kayitlar: Dict[str, Dict[str, Any]] = {}
    config = DynamicConfig.get_instance()
    onceki_onbellek = config.get_lawyers()
    config.set_lawyers(_onbellek_listesi(db))
    try:
        for lw in avukatlar:
            kimlik = getattr(lw, "kimlik", None)
            normlar = _avukat_normlari(lw)
            secim = lw.code or lw.name or ""          # frontend filtresi `code || name` gönderir
            filtre = _lawyer_filter_case_ids(db, secim, None) & aktif_ids if secim.strip() else set()
            kartlar: Set[int] = set()
            for n in normlar:
                kartlar |= norm_kartlari.get(n, set())
            bagli = cl_bagli.get(lw.id, 0)
            kayit = {
                "kimlik": kimlik,
                "code": lw.code,
                "ad": lw.name,
                "aktif": bool(lw.active),
                "filtre_dava": len(filtre),
                "sorumlu_kart": len(kartlar),
                "case_lawyers": bagli + sum(cl_bagsiz_norm.get(n, 0) for n in normlar),
                "case_lawyers_bagli": bagli,
                "belge": belge_id_sayim.get(lw.id, 0) + sum(belge_norm_sayim.get(n, 0) for n in normlar),
            }
            kayitlar[str(kimlik or lw.code or f"id:{lw.id}")] = kayit
    finally:
        config.set_lawyers(onceki_onbellek)

    cl_bagli_toplam = sum(cl_bagli.values())
    toplamlar = {
        "avukat": len(avukatlar),
        "aktif_dava": len(aktif_ids),
        "sorumlu_dolu_dava": sorumlu_dolu,
        "case_lawyers_satir": cl_toplam,
        "case_lawyers_bagli": cl_bagli_toplam,
        "case_lawyers_bagsiz": cl_toplam - cl_bagli_toplam,
        "avukatli_belge": avukatli_belge,
        "bagsiz_case_lawyers_adlari": dict(
            sorted(cl_bagsiz_ham.items(), key=lambda kv: (-kv[1], kv[0]))
        ),
    }
    return {
        "surum": SURUM,
        "olculme_zamani": datetime.now(timezone.utc).isoformat(),
        "avukatlar": kayitlar,
        "toplamlar": toplamlar,
    }


def _avukat_satirlari(db) -> List[Any]:
    """Avukat listesinin TAMAMI — pasifler dahil (pasife çekilen avukatın davası da sayılır)."""
    return db.query(models.Lawyer).order_by(models.Lawyer.sequence, models.Lawyer.id).all()


def _onbellek_listesi(db) -> List[Dict[str, Any]]:
    """`reference_lists.get_items("lawyers")` ile AYNI biçim, ama ölçülen oturumdan.

    `get_items` kendi `SessionLocal`'ını açar; ölçüm ise çağıranın oturumunda
    (commit edilmemiş adım dahil) yapılmalı — önbellek de oradan dolar.
    """
    spec = LIST_REGISTRY["lawyers"]
    q = db.query(models.Lawyer).filter(models.Lawyer.active.is_(True))
    q = q.order_by(*(getattr(models.Lawyer, col).asc() for col in spec.order_by))
    return [{f: getattr(i, f) for f in spec.fields} for i in q.all()]


def _avukat_normlari(lw) -> Set[str]:
    """Bir avukatın ham metinlerde görünebileceği normalize biçimler: ad + kod."""
    return {n for n in (_norm_name(lw.name or ""), _norm_name(lw.code or "")) if n}


def _deger_normlari(deger: Optional[str]) -> Set[str]:
    """Çoklu avukat alanının normları: bütün değer + her kişi parçası.

    Bütün değer de eklenir: ayraç içeren liste kaydı ("Hanyaloğlu & Acar")
    `_split_persons` ile iki parçaya bölünür ama kendisi tek kişidir.
    """
    if not deger:
        return set()
    normlar = {_norm_name(deger)}
    normlar.update(_norm_name(p) for p in _split_persons(deger))
    return {n for n in normlar if n}


def _aktif_kartlar(db):
    """(aktif kart id kümesi, {id: sorumlu avukat normları}, sorumlusu dolu kart sayısı)."""
    q = db.query(models.Case.id, models.Case.responsible_lawyer_name).filter(
        models.Case.active.is_(True), models.Case.deleted_at.is_(None),
    )
    aktif: Set[int] = set()
    normlar: Dict[int, Set[str]] = {}
    dolu = 0
    for cid, sorumlu in q.all():
        aktif.add(cid)
        if sorumlu and sorumlu.strip():
            dolu += 1
            normlar[cid] = _deger_normlari(sorumlu)
    return aktif, normlar, dolu


def _case_lawyers(db):
    """(lawyer_id → bağlı satır, norm → bağsız satır, ham ad → bağsız satır, toplam satır)."""
    bagli: Counter = Counter()
    bagsiz_norm: Counter = Counter()
    bagsiz_ham: Counter = Counter()
    toplam = 0
    for lawyer_id, ad in db.query(models.CaseLawyer.lawyer_id, models.CaseLawyer.name).all():
        toplam += 1
        if lawyer_id is not None:
            bagli[lawyer_id] += 1
            continue
        bagsiz_ham[ad or ""] += 1
        n = _norm_name(ad or "")
        if n:
            bagsiz_norm[n] += 1
    return bagli, bagsiz_norm, bagsiz_ham, toplam


def _belgeler(db):
    """(lawyer_id → belge, avukat_kodu normu → belge, avukatlı belge toplamı).

    Silinmiş (soft-delete) belgeler sayılmaz. `lawyer_id` kolonu (G226) yoksa
    yalnız `avukat_kodu`; varsa bağlı belge kimliğiyle, bağsız belge kodla sayılır.
    """
    doc = models.CaseDocument
    lawyer_col = getattr(doc, "lawyer_id", None)
    kolonlar: List[Any] = [doc.avukat_kodu]
    if lawyer_col is not None:
        kolonlar.append(lawyer_col)
    q = db.query(*kolonlar, func.count(doc.id)).filter(doc.deleted_at.is_(None)).group_by(*kolonlar)

    id_sayim: Counter = Counter()
    norm_sayim: Counter = Counter()
    toplam = 0
    for satir in q.all():
        kod = satir[0]
        lawyer_id = satir[1] if lawyer_col is not None else None
        adet = int(satir[-1])
        if lawyer_id is not None:
            id_sayim[lawyer_id] += adet
            toplam += adet
            continue
        n = _norm_name(kod or "")
        if n:
            norm_sayim[n] += adet
            toplam += adet
    return id_sayim, norm_sayim, toplam


# ─── Karşılaştırma ───────────────────────────────────────────────────────────

def karsilastir(once: Dict[str, Any], sonra: Dict[str, Any]) -> List[Dict[str, Any]]:
    """İki fotoğrafın farkı: ``[{tur, avukat, alan, once, sonra, aciklama}]``.

    `tur` = ``IHLAL`` (dava/bağ kaybı — adım geri alınır) ya da ``BILGI``
    (artış, ad değişikliği, yeni avukat, bağsız satırların azalması). BOŞ LİSTE =
    birebir denk.
    """
    sonuc: List[Dict[str, Any]] = []
    sonra_kayitlar = list((sonra.get("avukatlar") or {}).items())
    kullanilan: Set[str] = set()

    for anahtar, k_once in (once.get("avukatlar") or {}).items():
        eslesen = _eslestir(k_once, sonra_kayitlar, kullanilan)
        if eslesen is None:
            sonuc.append(_madde(IHLAL, anahtar, "avukat", k_once.get("ad"), None,
                                "avukat sonraki fotoğrafta bulunamadı (kimlik/kod/ad eşleşmedi)"))
            continue
        s_anahtar, k_sonra = eslesen
        kullanilan.add(s_anahtar)
        if (k_once.get("ad") or "") != (k_sonra.get("ad") or ""):
            sonuc.append(_madde(BILGI, anahtar, "ad", k_once.get("ad"), k_sonra.get("ad"), "ad değişti"))
        if k_once.get("kimlik") != k_sonra.get("kimlik"):
            sonuc.append(_madde(BILGI, anahtar, "kimlik", k_once.get("kimlik"), k_sonra.get("kimlik"),
                                "kimlik değişti"))
        for alan in AVUKAT_SAYIMLARI:
            a, b = int(k_once.get(alan) or 0), int(k_sonra.get(alan) or 0)
            if b < a:
                sonuc.append(_madde(IHLAL, anahtar, alan, a, b, f"{ALAN_ETIKETI[alan]} düştü"))
            elif b > a:
                sonuc.append(_madde(BILGI, anahtar, alan, a, b, f"{ALAN_ETIKETI[alan]} arttı"))

    for s_anahtar, k_sonra in sonra_kayitlar:
        if s_anahtar not in kullanilan:
            sonuc.append(_madde(BILGI, s_anahtar, "avukat", None, k_sonra.get("ad"), "yeni avukat kaydı"))

    t_once = once.get("toplamlar") or {}
    t_sonra = sonra.get("toplamlar") or {}
    for alan in (*TOPLAM_KORUNAN, "case_lawyers_bagsiz"):
        a, b = int(t_once.get(alan) or 0), int(t_sonra.get(alan) or 0)
        if a == b:
            continue
        tur = IHLAL if (b < a and alan in TOPLAM_KORUNAN) else BILGI
        yon = "düştü" if b < a else "arttı"
        sonuc.append(_madde(tur, None, alan, a, b, f"toplam {ALAN_ETIKETI[alan]} {yon}"))
    return sonuc


def ihlaller(fark: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Farkın yalnız İHLAL maddeleri (kapının tek soruşu: boş mu?)."""
    return [m for m in fark if m["tur"] == IHLAL]


def _eslestir(k_once: Dict[str, Any], adaylar, kullanilan: Set[str]):
    """Önceki kaydın sonraki fotoğraftaki karşılığı: kimlik → kod → normalize ad."""
    serbest = [(a, k) for a, k in adaylar if a not in kullanilan]
    kimlik = k_once.get("kimlik")
    if kimlik:
        for a, k in serbest:
            if k.get("kimlik") == kimlik:
                return a, k
    kod = k_once.get("code")
    if kod:
        for a, k in serbest:
            if k.get("code") == kod:
                return a, k
    ad = _norm_name(k_once.get("ad") or "")
    if ad:
        for a, k in serbest:
            if _norm_name(k.get("ad") or "") == ad:
                return a, k
    return None


def _madde(tur, avukat, alan, once, sonra, aciklama) -> Dict[str, Any]:
    return {"tur": tur, "avukat": avukat, "alan": alan, "once": once, "sonra": sonra, "aciklama": aciklama}


# ─── Biçim ───────────────────────────────────────────────────────────────────

def ozet_metni(foto: Dict[str, Any]) -> str:
    """Fotoğrafın insana okunur özeti (betik çıktısı + rapor)."""
    t = foto.get("toplamlar") or {}
    satirlar = [
        f"Avukat envanteri ({foto.get('olculme_zamani')})",
        f"  avukat {t.get('avukat', 0)} · aktif dava {t.get('aktif_dava', 0)} · "
        f"sorumlusu dolu {t.get('sorumlu_dolu_dava', 0)}",
        f"  case_lawyers {t.get('case_lawyers_satir', 0)} (bağlı {t.get('case_lawyers_bagli', 0)}, "
        f"bağsız {t.get('case_lawyers_bagsiz', 0)}) · avukatlı belge {t.get('avukatli_belge', 0)}",
        "  anahtar | aktif | filtre | sorumlu | case_lawyers (bağlı) | belge | ad",
    ]
    for anahtar, k in (foto.get("avukatlar") or {}).items():
        satirlar.append(
            f"  {anahtar} | {'E' if k.get('aktif') else 'H'} | {k.get('filtre_dava')} | "
            f"{k.get('sorumlu_kart')} | {k.get('case_lawyers')} ({k.get('case_lawyers_bagli')}) | "
            f"{k.get('belge')} | {k.get('ad')}"
        )
    return "\n".join(satirlar)


def fark_metni(fark: List[Dict[str, Any]]) -> str:
    """Karşılaştırma sonucunu İHLAL'ler önde olacak biçimde metne çevirir."""
    if not fark:
        return "avukat envanteri DENK"
    ihlal = ihlaller(fark)
    satirlar = [f"avukat envanteri: {len(ihlal)} İHLAL, {len(fark) - len(ihlal)} bilgi"]
    for m in sorted(fark, key=lambda m: m["tur"] != IHLAL):
        kim = m["avukat"] or "TOPLAM"
        satirlar.append(f"  [{m['tur']}] {kim} · {m['alan']}: {m['once']} → {m['sonra']} ({m['aciklama']})")
    return "\n".join(satirlar)
