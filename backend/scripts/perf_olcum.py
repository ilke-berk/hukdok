#!/usr/bin/env python3
"""Performans ölçüm raporu — SALT OKUNUR (G183).

`docs/arsiv/performans-denetimi-2026-09-14.md` bulgularını (D3 şişme, D5/D6 sunucu ve
bağlantı ayarları, D7 index sayaçları, D9 durum üçlüsü, D1/D2 arama planı) lokal restore
kopyasında ölçtü; lokal süreler ve sayaçlar prod'u TEMSİL ETMEZ. VACUUM FULL, index
düşürme, `ck_cases_status_uclu` VALIDATE'i gibi kararlar ancak bu script prod'da koşunca verilir.

    docker compose exec -T backend python -m scripts.perf_olcum
    docker compose exec -T backend python -m scripts.perf_olcum --term Bora
    docker compose exec -T backend python -m scripts.perf_olcum --term Bora --out /tmp/perf_olcum.md

Çıktı Markdown'dır: stdout'a basılır, `--out` verilirse ayrıca dosyaya (UTF-8) yazılır.

SALT OKUNUR — üç katmanlı güvence
---------------------------------
1. Script'in çalıştırdığı her SQL `salt_okunur_dogrula`'dan geçer: yalnız `SELECT` /
   `SHOW` / `EXPLAIN` ile başlayabilir, içinde veri ya da şema değiştiren anahtar sözcük
   (`YASAK_SOZCUKLER`) geçemez. Geçmezse sorgu HİÇ gönderilmeden `ValueError`.
2. CLI yolunda bağlantı `default_transaction_read_only=on` ile açılır: yukarıdaki süzgeç
   bir şeyi kaçırsa bile sunucu yazmayı reddeder.
3. Test (`tests/test_perf_olcum.py`) modüldeki bütün SQL metinlerini ve derlenmiş arama
   sorgusunu `INSERT|UPDATE|DELETE|ALTER|DROP|VACUUM` için tarar.

`--term` verilince arama sorgusu `EXPLAIN (ANALYZE, BUFFERS)` ile koşar: ANALYZE sorguyu
GERÇEKTEN çalıştırır, ama sorgu salt bir `SELECT` UNION'udur (yazma yok).

Bölümler
--------
1. Şişme — en büyük 12 tablo: heap boyutu / Σ pg_column_size oranı + ölü satır, vacuum.
2. Sunucu ayarları — `SHOW` (shared_buffers, effective_cache_size, ...).
3. Bağlantılar — `pg_stat_activity` durum dağılımı, "idle in transaction" sayısı ve süresi.
4. Index kullanımı — `scripts/index_envanteri.collect_indexes` ile `idx_scan = 0` listesi.
5. Veri dağılımı — `cases.status`, `tku_no`/`sistem_no`/`onceki_tracking_no` dolu sayıları.
6. Arama planı — `case_manager._search_term_ids(term, exact=False)` her UNION kolu için.

Bir bölüm hata verirse (yetki, statement_timeout) rapor durmaz: o bölüme "Ölçülemedi"
satırı düşer, WARNING loglanır, sonraki bölüm kendi transaction'ında koşar.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from scripts.index_envanteri import KORUMALI_UNIQUE, _pretty_size, classify, collect_indexes

logger = logging.getLogger(__name__)

TR = ZoneInfo("Europe/Istanbul")

# Ölçüm bağlantısının kendi tavanı: şişme bölümü tablo başına tam tarama yapar
# (Σ pg_column_size), uygulamanın 30 sn'lik statement_timeout'u buna dar gelebilir.
OLCUM_STATEMENT_TIMEOUT_MS = 120_000

BUYUK_TABLO_SAYISI = 12

BOLUM_BASLIKLARI: Tuple[str, ...] = (
    "1. Şişme",
    "2. Sunucu ayarları",
    "3. Bağlantılar",
    "4. Index kullanımı",
    "5. Veri dağılımı",
    "6. Arama planı",
)

# D5/D6: denetimin prod'da doğrulanmasını istediği ayarlar. `SHOW` adı bind
# parametresi alamaz → yalnız bu sabit listeden ve `_AYAR_ADI_RE` süzgecinden geçen ad.
AYARLAR: Tuple[str, ...] = (
    "shared_buffers",
    "effective_cache_size",
    "work_mem",
    "random_page_cost",
    "max_connections",
    "idle_in_transaction_session_timeout",
    "lock_timeout",
    "shared_preload_libraries",
)
_AYAR_ADI_RE = re.compile(r"^[a-z_]+$")

# ─── SQL metinleri (test hepsini tarar) ──────────────────────────────────────

SUNUCU_SQL = "SELECT current_database() AS veritabani, current_setting('server_version') AS surum"

BUYUK_TABLOLAR_SQL = """
SELECT
    s.relname                        AS tablo,
    pg_relation_size(s.relid)        AS heap_bayt,
    pg_total_relation_size(s.relid)  AS toplam_bayt,
    s.n_live_tup                     AS n_live_tup,
    s.n_dead_tup                     AS n_dead_tup,
    s.last_vacuum                    AS last_vacuum,
    s.last_autovacuum                AS last_autovacuum,
    s.last_autoanalyze               AS last_autoanalyze
FROM pg_stat_user_tables s
WHERE s.schemaname = 'public'
ORDER BY pg_total_relation_size(s.relid) DESC, s.relname
LIMIT :limit
"""

AYAR_KAYNAK_SQL = """
SELECT name AS ayar, source AS kaynak
FROM pg_settings
WHERE name = ANY(:adlar)
"""

BAGLANTILAR_SQL = """
SELECT
    COALESCE(datname, '(yok)')                                  AS veritabani,
    COALESCE(state, '(bilinmiyor)')                             AS durum,
    count(*)                                                    AS adet,
    max(EXTRACT(EPOCH FROM (now() - state_change)))             AS en_uzun_durum_sn,
    max(EXTRACT(EPOCH FROM (now() - xact_start)))               AS en_uzun_islem_sn
FROM pg_stat_activity
WHERE backend_type = 'client backend'
  AND pid <> pg_backend_pid()
GROUP BY 1, 2
ORDER BY 3 DESC, 1, 2
"""

STAT_SIFIRLAMA_SQL = """
SELECT pg_stat_get_db_stat_reset_time(d.oid) AS sifirlama
FROM pg_database d
WHERE d.datname = current_database()
"""

DURUM_DAGILIMI_SQL = """
SELECT
    status                                          AS durum,
    count(*) FILTER (WHERE deleted_at IS NULL)      AS canli,
    count(*) FILTER (WHERE deleted_at IS NOT NULL)  AS silinmis
FROM cases
GROUP BY status
ORDER BY 2 DESC, 1
"""

KIMLIK_DOLULUK_SQL = """
SELECT
    'cases'                                                              AS tablo,
    count(*)                                                             AS toplam,
    count(*) FILTER (WHERE NULLIF(btrim(tku_no), '') IS NOT NULL)        AS tku_no,
    count(*) FILTER (WHERE NULLIF(btrim(sistem_no), '') IS NOT NULL)     AS sistem_no,
    NULL::bigint                                                         AS onceki_tracking_no
FROM cases
UNION ALL
SELECT
    'case_foys',
    count(*),
    count(*) FILTER (WHERE NULLIF(btrim(tku_no), '') IS NOT NULL),
    count(*) FILTER (WHERE NULLIF(btrim(sistem_no), '') IS NOT NULL),
    count(*) FILTER (WHERE NULLIF(btrim(onceki_tracking_no), '') IS NOT NULL)
FROM case_foys
"""

EXPLAIN_ONEKI = "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "


def show_sql(ayar: str) -> str:
    """`SHOW <ayar>` — ad yalnız sabit listeden gelir, yine de biçim süzgecinden geçer."""
    if ayar not in AYARLAR or not _AYAR_ADI_RE.match(ayar):
        raise ValueError(f"bilinmeyen ayar adı: {ayar!r}")
    return f"SHOW {ayar}"


def satir_verisi_sql(tablo_tirnakli: str) -> str:
    """Bir tablonun canlı satırlarının Σ pg_column_size'ı (tablo adı TIRNAKLI verilir)."""
    return (
        "SELECT count(*) AS satir, COALESCE(sum(pg_column_size(t.*)), 0) AS veri_bayt "
        f"FROM public.{tablo_tirnakli} AS t"
    )


# ─── salt okunur süzgeci ─────────────────────────────────────────────────────

# İlk altısı görev sözleşmesi; kalanlar aynı sınıftan (yazma/şema/sayaç sıfırlama).
# `pg_stat_reset*` bilinçli: sayaçları sıfırlamak D7 ölçümünü yok eder.
YASAK_SOZCUKLER: Tuple[str, ...] = (
    "INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "VACUUM",
    "CREATE", "TRUNCATE", "GRANT", "REVOKE", "COPY", "MERGE",
    "SET_CONFIG", "NEXTVAL", "SETVAL", "PG_STAT_RESET",
)
# Tam sözcük eşleşmesi: `deleted_at`/`updated_at` kolon adları DELETE/UPDATE sayılmaz.
# Tek önek eşleşmesi `pg_stat_reset*` (pg_stat_reset_shared, ..._single_table_counters).
_YASAK_RE = re.compile(
    r"\b(" + "|".join(s for s in YASAK_SOZCUKLER if s != "PG_STAT_RESET") + r")\b|\b(PG_STAT_RESET)\w*",
    re.IGNORECASE,
)
_IZINLI_BAS_RE = re.compile(r"^\s*(SELECT|SHOW|EXPLAIN)\b", re.IGNORECASE)


def salt_okunur_dogrula(sql: str) -> str:
    """SQL salt okunur değilse `ValueError`; öyleyse metni aynen döndürür."""
    if not _IZINLI_BAS_RE.match(sql):
        raise ValueError("yalnız SELECT/SHOW/EXPLAIN koşulur: " + sql.strip()[:60])
    yasak = _YASAK_RE.search(sql)
    if yasak:
        raise ValueError(f"salt okunur olmayan sözcük ({yasak.group(0)}): " + sql.strip()[:60])
    return sql


def _kos(conn, sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Süzgeçten geçen SQL'i koşar, satırları sözlük listesi olarak döndürür."""
    result = conn.execute(text(salt_okunur_dogrula(sql)), params or {})
    return [dict(row) for row in result.mappings().all()]


def salt_okunur_engine(url):
    """CLI bağlantısı: sunucu tarafında da salt okunur (ikinci güvence katmanı)."""
    return create_engine(
        url,
        poolclass=NullPool,
        connect_args={
            "connect_timeout": 5,
            "options": (
                "-c default_transaction_read_only=on "
                f"-c statement_timeout={OLCUM_STATEMENT_TIMEOUT_MS}"
            ),
        },
    )


# ─── Markdown biçimleme ──────────────────────────────────────────────────────

def tr_sayi(deger: Any, ondalik: int = 0) -> str:
    """Türkçe sayı: binlik nokta, ondalık virgül (14.338 · 91,5)."""
    metin = f"{float(deger):,.{ondalik}f}" if ondalik else f"{int(deger):,}"
    return metin.replace(",", "\0").replace(".", ",").replace("\0", ".")


def tr_zaman(deger: Optional[dt.datetime]) -> str:
    """Zaman damgası TR saatiyle; tz'siz değer UTC kabul edilir (DB UTC)."""
    if deger is None:
        return "—"
    if deger.tzinfo is None:
        deger = deger.replace(tzinfo=dt.timezone.utc)
    return deger.astimezone(TR).strftime("%Y-%m-%d %H:%M:%S")


def md_hucre(deger: Any) -> str:
    if deger is None:
        return "—"
    if isinstance(deger, bool):
        return "evet" if deger else "hayır"
    if isinstance(deger, int):
        return tr_sayi(deger)
    if isinstance(deger, (float, Decimal)):
        return tr_sayi(deger, 1)
    if isinstance(deger, dt.datetime):
        return tr_zaman(deger)
    metin = str(deger).replace("\r", " ").replace("\n", " ").replace("|", "\\|")
    return metin if metin.strip() else "—"


def md_tablo(basliklar: Sequence[str], satirlar: Sequence[Sequence[Any]]) -> str:
    """GitHub Markdown tablosu. Boş satır listesi tablo yerine not basar."""
    if not satirlar:
        return "_(satır yok)_"
    cizgiler = [
        "| " + " | ".join(md_hucre(b) for b in basliklar) + " |",
        "| " + " | ".join("---" for _ in basliklar) + " |",
    ]
    for satir in satirlar:
        if len(satir) != len(basliklar):
            raise ValueError(f"satır {len(satir)} hücre, başlık {len(basliklar)}")
        cizgiler.append("| " + " | ".join(md_hucre(h) for h in satir) + " |")
    return "\n".join(cizgiler)


def _oran(pay: Optional[float], payda: Optional[float]) -> Optional[float]:
    if pay is None or not payda:
        return None
    return float(pay) / float(payda)


# ─── 1. Şişme ────────────────────────────────────────────────────────────────

def bolum_sisme(conn) -> str:
    quote = conn.dialect.identifier_preparer.quote_identifier
    tablolar = _kos(conn, BUYUK_TABLOLAR_SQL, {"limit": BUYUK_TABLO_SAYISI})
    satirlar = []
    for t in tablolar:
        veri = _kos(conn, satir_verisi_sql(quote(t["tablo"])))[0]
        # Ölü oranının paydası GERÇEK satır sayısı (count): `n_live_tup` istatistiktir,
        # restore sonrası ya da ANALYZE görmemiş tabloda 0/bayat kalır ve oranı %100'e iter.
        canli, olu = int(veri["satir"]), t["n_dead_tup"] or 0
        oran = _oran(t["heap_bayt"], veri["veri_bayt"])
        olu_yuzde = _oran(olu * 100, canli + olu)
        satirlar.append((
            t["tablo"],
            _pretty_size(t["heap_bayt"]),
            _pretty_size(int(veri["veri_bayt"])),
            None if oran is None else tr_sayi(oran, 2),
            _pretty_size(t["toplam_bayt"]),
            canli,
            olu,
            None if olu_yuzde is None else tr_sayi(olu_yuzde, 1),
            t["last_autovacuum"],
            t["last_vacuum"],
            t["last_autoanalyze"],
        ))
    return "\n\n".join([
        f"En büyük {BUYUK_TABLO_SAYISI} tablo (index + TOAST dahil toplam boyuta göre). "
        "**Oran = heap / Σ pg_column_size(satır)**: sayfa başlığı, satır işaretçisi ve boş alan "
        "yüzünden 1'in biraz üstü normaldir; TOAST'a taşınan büyük değerler oranı 1'in altına "
        "çekebilir. Denetimin D3 kararı (VACUUM FULL / pg_repack) prod oranıyla verilir.",
        md_tablo(
            ("Tablo", "Heap", "Σ satır verisi", "Oran", "Toplam", "Satır (count)",
             "n_dead_tup", "Ölü %", "last_autovacuum", "last_vacuum", "last_autoanalyze"),
            satirlar,
        ),
    ])


# ─── 2. Sunucu ayarları ──────────────────────────────────────────────────────

def bolum_ayarlar(conn) -> str:
    kaynaklar = {r["ayar"]: r["kaynak"] for r in _kos(conn, AYAR_KAYNAK_SQL, {"adlar": list(AYARLAR)})}
    satirlar = []
    for ayar in AYARLAR:
        deger = conn.execute(text(salt_okunur_dogrula(show_sql(ayar)))).scalar()
        satirlar.append((ayar, deger, kaynaklar.get(ayar)))
    return md_tablo(("Ayar", "Değer (SHOW)", "Kaynak (pg_settings.source)"), satirlar)


# ─── 3. Bağlantılar ──────────────────────────────────────────────────────────

def bolum_baglantilar(conn) -> str:
    satirlar = _kos(conn, BAGLANTILAR_SQL)
    idle_tx = [s for s in satirlar if s["durum"] == "idle in transaction"]
    idle_adet = sum(int(s["adet"]) for s in idle_tx)
    idle_sure = max((float(s["en_uzun_durum_sn"] or 0) for s in idle_tx), default=None)
    ozet = (
        f"**idle in transaction:** {tr_sayi(idle_adet)} bağlantı"
        + (f", en uzun {tr_sayi(idle_sure, 1)} sn" if idle_sure is not None else "")
        + ". Ölçümün kendi bağlantısı sayılmaz. Tek anlık fotoğraftır — D5 için mesai içinde "
        "birkaç kez koşun."
    )
    tablo = md_tablo(
        ("Veritabanı", "Durum", "Adet", "En uzun durum süresi (sn)", "En uzun transaction (sn)"),
        [(s["veritabani"], s["durum"], int(s["adet"]), s["en_uzun_durum_sn"], s["en_uzun_islem_sn"])
         for s in satirlar],
    )
    return "\n\n".join([ozet, tablo])


# ─── 4. Index kullanımı ──────────────────────────────────────────────────────

def bolum_index(conn, simdi: dt.datetime) -> str:
    sifirlama = _kos(conn, STAT_SIFIRLAMA_SQL)[0]["sifirlama"]
    indexler = classify(collect_indexes(conn))
    # Önce karar konusu olabilecekler (unique/PK olmayan), sonra dokunulmazlar; grup içinde büyükten küçüğe.
    taranmamis = sorted(
        (i for i in indexler if i.idx_scan == 0),
        key=lambda i: (i.verdict == KORUMALI_UNIQUE, -i.size_bytes, i.index_name),
    )
    unique_adet = sum(1 for i in taranmamis if i.verdict == KORUMALI_UNIQUE)
    if sifirlama is None:
        pencere = "**İstatistik sıfırlama:** bilinmiyor (NULL — sayaç bu veritabanında hiç sıfırlanmamış)."
    else:
        gun = (simdi - sifirlama).total_seconds() / 86400
        pencere = (
            f"**İstatistik sıfırlama:** {tr_zaman(sifirlama)} (TR) — sayaç penceresi "
            f"{tr_sayi(gun, 1)} gün. Restore edilmiş kopyada sayaçlar sıfırdır; düşürme kararı "
            "yalnız prod sayacıyla (D7)."
        )
    ozet = (
        f"Toplam index: {tr_sayi(len(indexler))} · `idx_scan = 0`: {tr_sayi(len(taranmamis))} "
        f"({_pretty_size(sum(i.size_bytes for i in taranmamis))}) · bunların unique/primary olanı: "
        f"{tr_sayi(unique_adet)} — DOKUNMA (unique doğrulaması `idx_scan`'i artırmaz, bkz. "
        "`scripts/index_envanteri.py`)."
    )
    tablo = md_tablo(
        ("Index", "Tablo", "Boyut", "Unique/PK", "Envanter kararı"),
        [(i.index_name, i.table_name, _pretty_size(i.size_bytes), i.is_unique or i.is_primary, i.verdict)
         for i in taranmamis],
    )
    return "\n\n".join([pencere, ozet, tablo])


# ─── 5. Veri dağılımı ────────────────────────────────────────────────────────

def bolum_veri(conn) -> str:
    from constants import CASE_STATUSES

    durumlar = _kos(conn, DURUM_DAGILIMI_SQL)
    ihlal = sum(int(d["canli"]) + int(d["silinmis"]) for d in durumlar if d["durum"] not in CASE_STATUSES)
    durum_tablosu = md_tablo(
        ("cases.status", "Canlı", "Silinmiş", "Üçlü dışı (D9)"),
        [(d["durum"] if d["durum"] is not None else "(NULL)", int(d["canli"]), int(d["silinmis"]),
          d["durum"] not in CASE_STATUSES) for d in durumlar],
    )
    doluluk = _kos(conn, KIMLIK_DOLULUK_SQL)
    doluluk_tablosu = md_tablo(
        ("Tablo", "Toplam satır", "tku_no dolu", "sistem_no dolu", "onceki_tracking_no dolu"),
        [(d["tablo"], int(d["toplam"]), int(d["tku_no"]), int(d["sistem_no"]),
          None if d["onceki_tracking_no"] is None else int(d["onceki_tracking_no"])) for d in doluluk],
    )
    return "\n\n".join([
        f"Durum üçlüsü (`constants.CASE_STATUSES`: {', '.join(CASE_STATUSES)}) dışındaki satır: "
        f"**{tr_sayi(ihlal)}** — `VALIDATE CONSTRAINT ck_cases_status_uclu` (D9) ancak 0 iken koşulabilir.",
        durum_tablosu,
        "Kimlik kolonları (D2: `cases` legacy kolonları boşsa oradaki index'ler boşa taşınıyor; "
        "asıl aranan `case_foys` kolonları). \"Dolu\" = NULL ve boşluk değil.",
        doluluk_tablosu,
    ])


# ─── 6. Arama planı ──────────────────────────────────────────────────────────

_APPEND_TURLERI = ("Append", "Merge Append")


@dataclass
class KolOzeti:
    kol: str
    kok_dugum: str
    taramalar: List[str] = field(default_factory=list)
    seq_scan: bool = False
    satir: int = 0
    elenen: int = 0
    buffer_hit: int = 0
    buffer_read: int = 0
    sure_ms: float = 0.0


@dataclass
class PlanOzeti:
    planlama_ms: Optional[float]
    calisma_ms: Optional[float]
    buffer_hit: int
    buffer_read: int
    kollar: List[KolOzeti]
    uyari: Optional[str] = None


def kol_adlari(selects: Sequence[Any]) -> List[str]:
    """`_term_case_id_selects` kollarının okunur adı: `tablo.kolon` (çıkmazsa `kol N`)."""
    adlar = []
    for sira, secim in enumerate(selects, 1):
        sol = getattr(getattr(secim, "whereclause", None), "left", None)
        tablo = getattr(getattr(sol, "table", None), "name", None)
        kolon = getattr(sol, "name", None)
        adlar.append(f"{tablo}.{kolon}" if tablo and kolon else f"kol {sira}")
    return adlar


def _dugumler(plan: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    yield plan
    for alt in plan.get("Plans") or []:
        yield from _dugumler(alt)


def _dongu(dugum: Dict[str, Any]) -> int:
    return int(dugum.get("Actual Loops") or 1)


def _tarama_etiketi(dugum: Dict[str, Any]) -> Optional[str]:
    tur = dugum.get("Node Type", "")
    if "Scan" not in tur:
        return None
    etiket = ("Parallel " if dugum.get("Parallel Aware") else "") + tur
    if dugum.get("Relation Name"):
        etiket += f" {dugum['Relation Name']}"
    if dugum.get("Index Name"):
        etiket += f" [{dugum['Index Name']}]"
    return etiket


def kol_ozeti(ad: str, kok: Dict[str, Any]) -> KolOzeti:
    """Bir UNION kolunun alt ağacını özetler.

    `Actual Rows`/`Rows Removed by Filter`/`Actual Total Time` döngü BAŞINA ortalamadır →
    `Actual Loops` ile çarpılır. Buffer sayaçları kümülatiftir (çocuklar dahil) → kökten okunur.
    """
    dugumler = list(_dugumler(kok))
    taramalar = [e for e in (_tarama_etiketi(d) for d in dugumler) if e]
    return KolOzeti(
        kol=ad,
        kok_dugum=kok.get("Node Type", "?"),
        taramalar=taramalar,
        seq_scan=any(d.get("Node Type") == "Seq Scan" for d in dugumler),
        satir=int(round(float(kok.get("Actual Rows") or 0) * _dongu(kok))),
        elenen=int(round(sum(float(d.get("Rows Removed by Filter") or 0) * _dongu(d) for d in dugumler))),
        buffer_hit=int(kok.get("Shared Hit Blocks") or 0),
        buffer_read=int(kok.get("Shared Read Blocks") or 0),
        sure_ms=float(kok.get("Actual Total Time") or 0) * _dongu(kok),
    )


def explain_ozeti(ham: Any, adlar: Sequence[str]) -> PlanOzeti:
    """`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` çıktısını kol kol özetler.

    UNION kolları planın ilk `Append` düğümünün çocuklarıdır ve SELECT sırasını korur;
    kol sayısı tutan ilk Append seçilir. Tutmazsa kollar `kol N` diye adlanır ve
    `uyari` doldurulur (planın biçimi beklenenden farklı — rapor yine basılır).
    """
    belge = json.loads(ham) if isinstance(ham, (str, bytes)) else ham
    kok_kayit = belge[0] if isinstance(belge, list) else belge
    plan = kok_kayit["Plan"]

    appendler = [d for d in _dugumler(plan) if d.get("Node Type") in _APPEND_TURLERI]
    secilen = next((d for d in appendler if len(d.get("Plans") or []) == len(adlar)), None)
    uyari = None
    if secilen is None and appendler:
        secilen = appendler[0]
        uyari = f"Append çocuk sayısı ({len(secilen.get('Plans') or [])}) kol sayısını ({len(adlar)}) tutmuyor"
    elif secilen is None:
        uyari = "planda Append düğümü yok — kollar ayrıştırılamadı"

    kollar = []
    for sira, cocuk in enumerate((secilen or {}).get("Plans") or []):
        ad = adlar[sira] if uyari is None and sira < len(adlar) else f"kol {sira + 1}"
        kollar.append(kol_ozeti(ad, cocuk))

    return PlanOzeti(
        planlama_ms=kok_kayit.get("Planning Time"),
        calisma_ms=kok_kayit.get("Execution Time"),
        buffer_hit=int(plan.get("Shared Hit Blocks") or 0),
        buffer_read=int(plan.get("Shared Read Blocks") or 0),
        kollar=kollar,
        uyari=uyari,
    )


def arama_sorgusu(dialect, term: str) -> Tuple[str, Dict[str, Any], List[str]]:
    """Uygulamanın gerçek arama sorgusu: (EXPLAIN'li SQL, parametreler, kol adları)."""
    from managers import case_manager

    stmt = case_manager._search_term_ids(term, exact=False)
    derlenmis = stmt.compile(dialect=dialect)
    sql = salt_okunur_dogrula(EXPLAIN_ONEKI + str(derlenmis))
    return sql, dict(derlenmis.params), kol_adlari(case_manager._term_case_id_selects(term, exact=False))


def render_plan(term: str, ozet: PlanOzeti) -> str:
    seq = sum(1 for k in ozet.kollar if k.seq_scan)
    basliklar = [
        f"Terim: `{term}` · `case_manager._search_term_ids(term, exact=False)` · "
        "`EXPLAIN (ANALYZE, BUFFERS)`",
        "**Planlama:** {p} ms · **Çalışma:** {c} ms · **Buffer (hit/read):** {h} / {r} · "
        "**Seq Scan'li kol:** {s} / {n}".format(
            p="—" if ozet.planlama_ms is None else tr_sayi(ozet.planlama_ms, 1),
            c="—" if ozet.calisma_ms is None else tr_sayi(ozet.calisma_ms, 1),
            h=tr_sayi(ozet.buffer_hit), r=tr_sayi(ozet.buffer_read),
            s=tr_sayi(seq), n=tr_sayi(len(ozet.kollar)),
        ),
    ]
    if ozet.uyari:
        basliklar.append(f"**Uyarı:** {ozet.uyari}")
    tablo = md_tablo(
        ("Kol", "Kök düğüm", "Taramalar", "Seq Scan", "Satır", "Filtreyle elenen",
         "Buffer hit", "Buffer read", "Süre (ms)"),
        [(k.kol, k.kok_dugum, "; ".join(k.taramalar), k.seq_scan, k.satir, k.elenen,
          k.buffer_hit, k.buffer_read, k.sure_ms) for k in ozet.kollar],
    )
    basliklar.append(tablo)
    basliklar.append(
        "Süre ve buffer bu veritabanının önbellek durumuna bağlıdır; ilk koşu soğuk, ikinci koşu "
        "sıcak okur. Lokal restore kopyasındaki süreler prod'u temsil etmez."
    )
    return "\n\n".join(basliklar)


def bolum_arama(conn, term: str) -> str:
    sql, params, adlar = arama_sorgusu(conn.dialect, term)
    ham = conn.exec_driver_sql(sql, params).scalar()
    return render_plan(term, explain_ozeti(ham, adlar))


# ─── rapor ───────────────────────────────────────────────────────────────────

def _baslik(conn, term: Optional[str], simdi: dt.datetime, surum: str) -> str:
    try:
        sunucu = _kos(conn, SUNUCU_SQL)[0]
        veritabani = f"{sunucu['veritabani']} · PostgreSQL {sunucu['surum']}"
    except Exception as exc:
        logger.warning("perf_olcum: sunucu bilgisi okunamadı: %s", exc)
        veritabani = f"okunamadı ({type(exc).__name__})"
    finally:
        conn.rollback()
    return "\n\n".join([
        "# HukuDok performans ölçümü (salt okunur)",
        md_tablo(("Alan", "Değer"), [
            ("Sürüm (APP_VERSION)", surum),
            ("Zaman (TR)", simdi.astimezone(TR).strftime("%Y-%m-%d %H:%M:%S")),
            ("Veritabanı", veritabani),
            ("Arama terimi", term),
        ]),
        "> Üretici: `scripts/perf_olcum.py` (G183). Lokal restore kopyasında alınan süre ve "
        "sayaçlar prod'u TEMSİL ETMEZ; kararlar (VACUUM FULL, index düşürme, CHECK VALIDATE) prod "
        "çıktısıyla verilir.",
    ])


def rapor_uret(
    conn,
    term: Optional[str] = None,
    simdi: Optional[dt.datetime] = None,
    surum: Optional[str] = None,
) -> str:
    """Altı bölümlü Markdown raporu. Her bölüm kendi transaction'ında; hata bölümle sınırlı."""
    simdi = simdi or dt.datetime.now(TR)
    # /healthz "version" alanıyla AYNI kaynak (api.py): imaja gömülen git SHA.
    surum = surum or os.getenv("APP_VERSION", "dev")

    bolumler: List[Tuple[str, Optional[Callable[[], str]]]] = [
        (BOLUM_BASLIKLARI[0], lambda: bolum_sisme(conn)),
        (BOLUM_BASLIKLARI[1], lambda: bolum_ayarlar(conn)),
        (BOLUM_BASLIKLARI[2], lambda: bolum_baglantilar(conn)),
        (BOLUM_BASLIKLARI[3], lambda: bolum_index(conn, simdi)),
        (BOLUM_BASLIKLARI[4], lambda: bolum_veri(conn)),
        (BOLUM_BASLIKLARI[5], (lambda: bolum_arama(conn, term)) if term else None),
    ]

    parcalar = [_baslik(conn, term, simdi, surum)]
    for baslik, uret in bolumler:
        parcalar.append(f"## {baslik}")
        if uret is None:
            parcalar.append("_Atlandı: `--term` verilmedi (EXPLAIN koşulmadı)._")
            continue
        try:
            parcalar.append(uret())
        except Exception as exc:
            logger.warning("perf_olcum: '%s' bölümü ölçülemedi: %s: %s", baslik, type(exc).__name__, exc)
            parcalar.append(f"_Ölçülemedi: {type(exc).__name__}: {md_hucre(str(exc)[:300])}_")
        finally:
            conn.rollback()
    return "\n\n".join(parcalar) + "\n"


def main(argv: Optional[List[str]] = None, engine=None) -> int:
    parser = argparse.ArgumentParser(description="Performans ölçüm raporu (salt okunur, Markdown)")
    parser.add_argument("--term", help="arama planı için terim (verilmezse EXPLAIN bölümü atlanır)")
    parser.add_argument("--out", help="raporu ayrıca bu dosyaya UTF-8 yazar")
    args = parser.parse_args(argv)

    kendi_engine = engine is None
    if engine is None:
        import database

        engine = salt_okunur_engine(database.DATABASE_URL)
    try:
        with engine.connect() as conn:
            rapor = rapor_uret(conn, term=args.term)
    finally:
        if kendi_engine:
            engine.dispose()

    sys.stdout.write(rapor)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(rapor)
        print(f"perf_olcum: rapor yazıldı → {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    # database import'u (engine kurulumu) logging kurulmadan ÖNCE: açılış INFO satırı
    # stdout'taki Markdown'a karışmasın (configure_logging handler'ı stdout'tur).
    import database
    from logging_setup import configure_logging

    olcum_engine = salt_okunur_engine(database.DATABASE_URL)
    configure_logging()
    try:
        sys.exit(main(engine=olcum_engine))
    finally:
        olcum_engine.dispose()
