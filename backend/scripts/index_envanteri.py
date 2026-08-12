#!/usr/bin/env python3
"""Index envanteri ve GÜVENLİ düşürme listesi (FAZ D 6.2, G042).

SALT OKUNUR. Hiçbir DDL çalıştırmaz; yalnız `pg_index` / `pg_class` /
`pg_stat_user_indexes` okur ve rapor basar. Düşürme kararını insan verir,
düşürme DDL'i `database.py` migrasyonundadır.

    docker compose exec -T backend python scripts/index_envanteri.py
    docker compose exec -T backend python scripts/index_envanteri.py --json

PAZARLIKSIZ KURAL — neden isimle değil `indkey` ile
---------------------------------------------------
`idx_scan` **index taramalarını** sayar; UNIQUE kısıt doğrulaması (INSERT/UPDATE
sırasındaki tekillik kontrolü) o sayacı **artırmaz**. Yani görevini kusursuz yapan
bir UNIQUE index ömrü boyunca `idx_scan = 0` görünür. Bu şemadaki somut kurban
adayı `ix_cases_tracking_no`: `indisunique = true`, `pg_constraint`'te karşılığı
YOK — ofis dosya numarası tekilliğini tutan **tek yapı** o ve hiç taranmamış
görünüyor. Prod ölçümünde (2026-08-12) `idx_scan = 0` olan 96 index'in **44'ü**
unique/primary'dir; körlemesine "kullanılmayanı düşür" kuralı 44 kısıt silerdi.

Bu yüzden liste:

* `indisunique` / `indisprimary` olanı **ZORUNLU** dışlar (tek satırlık kural,
  başka hiçbir koşula bağlı değil),
* ikizliği isim kalıbıyla değil **`indkey` + opclass + access method + kısmi
  koşul** imzasıyla belirler — bu şemada `ix_` / `idx_` isimlendirmesi tutarlı
  DEĞİL (`idx_case_parties_case` ile `ix_case_parties_case_id` aynı kolonun iki
  index'i), isimle eleme yanlış kümeyi verir.

İki aday türü — güven dereceleri FARKLI
---------------------------------------
* ``ikiz``  : imzası birebir aynı ikinci bir index var. Sorgu planı için fark
  yok, kalan ikiz aynı işi görür → **istatistikten bağımsız** güvenli. Bu tür
  lokal kopyada da doğru ölçülür.
* ``taranmamis`` : `idx_scan = 0`. Yalnız **istatistiğin toplandığı** veritabanı
  için anlamlıdır. Restore edilmiş bir kopyada sayaçlar sıfırlanmış olur —
  raporun başındaki `stats_reset` satırı bu yüzden basılır. Bu türü PROD'da
  koşmadan düşürme listesine ALMA.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Envanter sorgusu: imza bileşenleri (indkey/indclass/indcollation/indoption/
# amname/pred/exprs) tek seferde okunur; boyut ve tarama sayacı raporun kendisi
# içindir, sınıflandırmayı yalnız `idx_scan` etkiler.
INVENTORY_SQL = """
SELECT
    t.relname                                    AS table_name,
    ci.relname                                   AS index_name,
    i.indisunique                                AS is_unique,
    i.indisprimary                               AS is_primary,
    i.indkey::text                               AS indkey,
    i.indclass::text                             AS indclass,
    i.indcollation::text                         AS indcollation,
    i.indoption::text                            AS indoption,
    am.amname                                    AS access_method,
    COALESCE(pg_get_expr(i.indpred, i.indrelid), '')   AS predicate,
    COALESCE(pg_get_expr(i.indexprs, i.indrelid), '')  AS expressions,
    pg_relation_size(i.indexrelid)               AS size_bytes,
    COALESCE(s.idx_scan, 0)                      AS idx_scan,
    ci.oid                                       AS index_oid,
    EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid = i.indexrelid) AS has_constraint,
    pg_get_indexdef(i.indexrelid)                AS indexdef
FROM pg_index i
JOIN pg_class ci      ON ci.oid = i.indexrelid
JOIN pg_class t       ON t.oid  = i.indrelid
JOIN pg_namespace n   ON n.oid  = ci.relnamespace
JOIN pg_am am         ON am.oid = ci.relam
LEFT JOIN pg_stat_user_indexes s ON s.indexrelid = i.indexrelid
WHERE n.nspname = 'public'
  AND i.indisvalid
  AND i.indislive
ORDER BY t.relname, ci.relname
"""

# Verdict değerleri — rapor ve testler bu sabitleri kullanır.
KORUMALI_UNIQUE = "KORUMALI-UNIQUE"    # indisunique/indisprimary → dokunulmaz
KALSIN_IKIZ = "KALSIN-IKIZ"            # ikiz grubunun korunan üyesi
ADAY_IKIZ = "ADAY-IKIZ"                # imzası birebir aynı başka index var
ADAY_TARANMAMIS = "ADAY-TARANMAMIS"    # idx_scan = 0 (istatistiğe bağlı)
KULLANILIYOR = "KULLANILIYOR"          # idx_scan > 0, ikizi yok


@dataclass
class IndexInfo:
    table_name: str
    index_name: str
    is_unique: bool
    is_primary: bool
    indkey: str
    indclass: str
    indcollation: str
    indoption: str
    access_method: str
    predicate: str
    expressions: str
    size_bytes: int
    idx_scan: int
    index_oid: int
    has_constraint: bool
    indexdef: str
    verdict: str = ""
    reason: str = ""
    twins: List[str] = field(default_factory=list)

    @property
    def signature(self) -> tuple:
        """İkizlik imzası — ADI İÇERMEZ (bilinçli).

        Aynı imzalı iki index, planlayıcı için birbirinin yerine geçer:
        aynı tablo, aynı access method, aynı kolon/ifade dizisi, aynı operatör
        sınıfı, aynı collation, aynı ASC/DESC-NULLS seçenekleri, aynı kısmi
        koşul. Bunlardan biri bile farklıysa ikiz DEĞİLDİR (örn. `tku_no`
        üzerindeki btree ile GIN trigram index'i aynı kolonu tutar ama farklı
        sorguya hizmet eder).
        """
        return (
            self.table_name,
            self.access_method,
            self.indkey,
            self.indclass,
            self.indcollation,
            self.indoption,
            self.predicate,
            self.expressions,
        )

    @property
    def guards_uniqueness_alone(self) -> bool:
        """UNIQUE ama `pg_constraint` karşılığı yok → tekilliği TEK BAŞINA tutuyor.

        Böyle bir index düşerse kısıt sessizce kaybolur (ofis no tekilliği:
        `ix_cases_tracking_no`). Rapor bunları ayrıca listeler.
        """
        return self.is_unique and not self.has_constraint


def collect_indexes(conn) -> List[IndexInfo]:
    """Bağlı veritabanındaki public şema index'lerini okur (salt okunur)."""
    from sqlalchemy import text

    rows = conn.execute(text(INVENTORY_SQL)).mappings().all()
    return [IndexInfo(**dict(row)) for row in rows]


def classify(indexes: List[IndexInfo]) -> List[IndexInfo]:
    """Her index'e verdict + gerekçe yazar; listeyi aynen döndürür.

    Sıra önemlidir: unique/primary kontrolü HER ŞEYDEN önce gelir ve başka hiçbir
    koşulla ezilemez.
    """
    groups: Dict[tuple, List[IndexInfo]] = {}
    for idx in indexes:
        groups.setdefault(idx.signature, []).append(idx)

    for idx in indexes:
        group = groups[idx.signature]
        idx.twins = sorted(o.index_name for o in group if o.index_name != idx.index_name)

        # 1) PAZARLIKSIZ: unique/primary asla adaya girmez.
        if idx.is_unique or idx.is_primary:
            idx.verdict = KORUMALI_UNIQUE
            idx.reason = (
                "tekilliği tek başına tutuyor (pg_constraint karşılığı yok)"
                if idx.guards_uniqueness_alone
                else "unique/primary — kısıt yapısı"
            )
            continue

        # 2) İkiz: imzası aynı başka index var mı? Unique bir ikiz varsa
        #    "PK-ikizi"dir (kalan taraf zaten daha güçlü); yoksa gruptan biri
        #    korunur, diğerleri adaydır.
        if len(group) > 1:
            keeper = _keeper(group)
            if keeper is idx:
                idx.verdict = KALSIN_IKIZ
                idx.reason = f"ikiz grubunun korunan üyesi ({', '.join(idx.twins)} düşer)"
            else:
                unique_twin = next((o for o in group if o.is_unique or o.is_primary), None)
                idx.verdict = ADAY_IKIZ
                idx.reason = (
                    f"PK/unique ikizi: '{unique_twin.index_name}' aynı imzayı daha güçlü tutuyor"
                    if unique_twin
                    else f"birebir ikiz: '{keeper.index_name}' aynı işi görür"
                )
            continue

        # 3) Hiç taranmamış: yalnız istatistiğin toplandığı DB için geçerli.
        if idx.idx_scan == 0:
            idx.verdict = ADAY_TARANMAMIS
            idx.reason = "idx_scan = 0 (bu veritabanının istatistik penceresinde)"
            continue

        idx.verdict = KULLANILIYOR
        idx.reason = f"idx_scan = {idx.idx_scan:,}"

    return indexes


def _keeper(group: List[IndexInfo]) -> IndexInfo:
    """İkiz grubunda hangi index KALIR.

    Öncelik: (1) unique/primary olan — kısıtı taşıdığı için zaten düşürülemez,
    (2) en çok taranan — planlayıcının fiilen kullandığı taraf korunur,
    (3) eşitlikte en eski (`oid`) — deterministik olsun diye.
    """
    return sorted(
        group,
        key=lambda i: (0 if (i.is_unique or i.is_primary) else 1, -i.idx_scan, i.index_oid),
    )[0]


def safe_drop_candidates(indexes: List[IndexInfo], include_unscanned: bool = True) -> List[IndexInfo]:
    """Güvenli düşürme adayları.

    `include_unscanned=False` yalnız yapısal (ikiz) adayları verir — istatistiği
    güvenilmeyen bir kopyada koşarken doğru olan budur.
    """
    wanted = {ADAY_IKIZ, ADAY_TARANMAMIS} if include_unscanned else {ADAY_IKIZ}
    return [i for i in indexes if i.verdict in wanted]


def _pretty_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "kB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:,.0f} {unit}" if unit == "B" else f"{value:,.1f} {unit}"
        value /= 1024
    return f"{num_bytes} B"


def _stats_reset(conn) -> Optional[str]:
    from sqlalchemy import text

    return conn.execute(text(
        "SELECT stats_reset::text FROM pg_stat_database WHERE datname = current_database()"
    )).scalar()


def render_report(indexes: List[IndexInfo], stats_reset: Optional[str] = None) -> str:
    """İnsan okuyacak rapor. Adaylar tablo tablo, gerekçesiyle."""
    lines: List[str] = []
    add = lines.append

    add("=" * 100)
    add("INDEX ENVANTERİ — salt okunur (G042)")
    add("=" * 100)
    add(f"İstatistik sıfırlanma (stats_reset): {stats_reset or 'bilinmiyor'}")
    add("  ↑ idx_scan sayaçları BU andan itibaren birikti. Restore edilmiş bir kopyada")
    add("    sayaçlar sıfırdır; ADAY-TARANMAMIS satırları o kopyada ANLAMSIZDIR.")
    add("")

    unique_count = sum(1 for i in indexes if i.verdict == KORUMALI_UNIQUE)
    unscanned = [i for i in indexes if i.idx_scan == 0]
    unscanned_unique = [i for i in unscanned if i.is_unique or i.is_primary]
    add(f"Toplam index: {len(indexes)}   |   unique/primary (DIŞLANDI): {unique_count}")
    add(f"idx_scan = 0: {len(unscanned)}   |   bunların unique/primary olanı: {len(unscanned_unique)} — DOKUNMA")
    add("")

    alone = [i for i in indexes if i.guards_uniqueness_alone]
    add("-" * 100)
    add(f"TEKİLLİĞİ TEK BAŞINA TUTAN UNIQUE INDEX'LER ({len(alone)}) — pg_constraint karşılığı YOK")
    add("-" * 100)
    for i in sorted(alone, key=lambda x: (x.table_name, x.index_name)):
        add(f"  {i.index_name:44} {i.table_name:24} idx_scan={i.idx_scan:<10,} {_pretty_size(i.size_bytes):>12}")
    add("")

    candidates = safe_drop_candidates(indexes)
    total = sum(i.size_bytes for i in candidates)
    add("-" * 100)
    add(f"GÜVENLİ DÜŞÜRME ADAYLARI ({len(candidates)} index, {_pretty_size(total)})")
    add("-" * 100)
    for verdict, baslik in ((ADAY_IKIZ, "A) YAPISAL — birebir ikiz (istatistikten bağımsız güvenli)"),
                            (ADAY_TARANMAMIS, "B) İSTATİSTİKSEL — hiç taranmamış (yalnız PROD ölçümünde geçerli)")):
        grup = [i for i in candidates if i.verdict == verdict]
        add("")
        add(f"{baslik} — {len(grup)} index, {_pretty_size(sum(i.size_bytes for i in grup))}")
        for i in sorted(grup, key=lambda x: (-x.size_bytes, x.index_name)):
            add(f"  {i.index_name:44} {i.table_name:24} {_pretty_size(i.size_bytes):>12}  {i.reason}")
    add("")
    add("=" * 100)
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Index envanteri ve güvenli düşürme listesi (salt okunur)")
    parser.add_argument("--json", action="store_true", help="raporu değil ham envanteri JSON olarak bas")
    args = parser.parse_args(argv)

    import database

    with database.engine.connect() as conn:
        indexes = classify(collect_indexes(conn))
        reset = _stats_reset(conn)

    if args.json:
        payload: Dict[str, Any] = {
            "stats_reset": reset,
            "toplam": len(indexes),
            "aday": [i.index_name for i in safe_drop_candidates(indexes)],
            "index": [asdict(i) for i in indexes],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(render_report(indexes, reset))
    return 0


if __name__ == "__main__":
    sys.exit(main())
