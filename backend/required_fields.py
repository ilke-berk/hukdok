"""Dava kartı zorunlu alan tanımı — tek kaynak (anket kararı, 2026-07-31 rev.2).

Kural: zorunlu alan eksikliği kaydı ENGELLEMEZ — dosya DERDEST olarak açılır;
eksikler dava kartında/listesinde uyarı olarak görünür ve panelden
filtrelenebilir (DANIŞ'a düşürme denendi, dönüşüm kaybı riski nedeniyle
vazgeçildi: DANIŞ yolunda müvekkil kaydı oluşturulmuyor).

Frontend bu listeyi GET /api/config/required_case_fields üzerinden okur;
ikinci bir liste tutulmaz.

ZORUNLULUK BAĞLAMSALDIR (FAZ F §2 / D2 + D8, G046). Bir alanın zorunlu sayılıp
sayılmadığı kaydın kendisine bağlı olabilir; kural KOD değil VERİ olarak yazılır
(`skip_when`). Sebebi tek kaynak zorunluluğudur: aynı kuralı üç tüketici okur —

  1. Python  : `compute_missing_fields` (dava kartı + liste uyarısı)
  2. SQL     : `missing_bucket_sql` (denormalize bayrağın backfill'i + denetimi)
  3. Frontend: /api/config/required_case_fields (liste JSON olarak gider)

Kuralı koda gömmek üçünü ayrıştırırdı; veriye yazınca SQL ikizi listeden
TÜRETİLİR. Bu dosyaya yeni bir kapı eklerken `missing_required_sql`in de o
kapıyı çevirdiğini doğrula — tests/test_g046_missing_required.py iki tarafı
birbirine kilitler.
"""

# ─── D2: esas numarası beklenmeyen yargı türleri (FAZ F §2) ──────────────────
#
# Bu dört türde dosyanın esas numarası YOKTUR (arabuluculuk/savcılık/danışmanlık/
# tahkim); "eksik esas" işaretlemek karşı tarafın S9 cevabına göre ~140, lokal
# ölçüme göre 2.751 dosyayı (2026-08-12, `SELECT file_type, count(*) FROM cases`)
# kalıcı olarak eksik filtresinde tutardı.
#
# Değerler `file_types` referans listesinin KANONİK yazımıdır (id 5/6/8/10) ve
# karşılaştırma bilinçli olarak TAM EŞLEŞMEDİR — küçük/büyük harf katlaması YOK:
# Türkçe 'İ/ı' katlaması Python ile Postgres'te aynı sonucu vermez (locale'e
# bağlı) ve iki taraf sessizce ayrışırdı. Alan zaten kapalı listeden seçilir;
# aktarım da kanonik değere eşlemek zorundadır (§1.4 ad kesinleşmesi).
ESAS_BEKLENMEYEN_TURLER = ("Arabuluculuk", "Savcılık", "Danışmanlık", "Tahkim")

REQUIRED_CASE_FIELDS = [
    # `skip_when`: kapı — kaydın <field> değeri <in> listesindeyse bu alan
    # zorunlu SAYILMAZ. JSON'a çevrilebilir olması şart (frontend'e gider).
    {"field": "esas_no", "label": "Esas No",
     "skip_when": {"field": "file_type", "in": list(ESAS_BEKLENMEYEN_TURLER)}},
    {"field": "court", "label": "Mahkeme"},
    {"field": "file_type", "label": "Yargı Türü"},
    {"field": "judicial_unit", "label": "Yargı Birimi"},
    # Etiket 2026-08-12'de değişti (FAZ F §1.4 / G044): "Dosya Alt Türü" →
    # "Uzmanlık Alanı". Kolon adı (`sub_type`) BİLİNÇLİ korundu; değişen alanın
    # Türkçe adıdır, taşıdığı veri değil (değer `specialties` listesinden gelir).
    {"field": "sub_type", "label": "Uzmanlık Alanı"},
    # Geçici olarak listeden çıkarıldı (2026-08-04): Ek Alt Kırılım alanı UI'da
    # gizlendi (dropdown güncellenecek); görünmeyen alan "eksik" uyarısı
    # üretmesin. Alan geri açılınca bu satırı da geri al.
    # {"field": "sub_type_extra", "label": "Uzmanlık / Tıbbi İşlem"},
    {"field": "opening_date", "label": "Dava Açılış Tarihi"},
    {"field": "subject", "label": "Dava Konusu"},
    {"field": "responsible_lawyer_name", "label": "Sorumlu Avukat"},
    {"field": "uyap_lawyer_name", "label": "UYAP Avukatı"},
    {"field": "service_type", "label": "Hizmet Türü"},
    {"field": "acceptance_date", "label": "Kabul Tarihi"},
    {"field": "bureau_type", "label": "Büro Özel Türü"},
    {"field": "atama_tarihi", "label": "Atama Tarihi"},
]

# Müvekkil TC'si Client kaydında yaşar (CaseParty'de toplanmıyor); form yalnız
# karşı taraf TC'si girebildiği için denetim COUNTER taraflarla sınırlı —
# aksi halde her yeni dosya yanlış "eksik" işaretlenir.
PARTY_TC_FIELD = {"field": "counter_party_tc_no", "label": "Karşı Taraf TC Kimlik No"}

# Bayrağı hesaplamak için kayıttan okunması gereken kolonlar: zorunlu alanların
# kendisi + kapıların baktığı alanlar. Elle tekrarlanmaz, listeden türetilir.
MISSING_FLAG_INPUT_FIELDS = tuple(dict.fromkeys(
    [f["field"] for f in REQUIRED_CASE_FIELDS]
    + [f["skip_when"]["field"] for f in REQUIRED_CASE_FIELDS if f.get("skip_when")]
))

# ─── D8: aktarım kaynaklı kayıtların ayrı kovası (FAZ F §4 K1, ADR-014) ──────
#
# UYAP Avukatı 8.409 aktarım kaydında BOŞ gelecek (ön-doldurma reddedildi).
# Aktarılan kayıtlar eksik filtresinde ayrı kovada durur: filtre "her zaman
# ateşleyen" hâle gelmez ama borç da gizlenmez. Provenance TEK kaynaktan okunur —
# `case_history.source` imzası; ikinci bir "bu kayıt aktarımdan geldi" bayrağı
# TUTULMAZ (tutulsaydı imzayla sessizce ayrışabilirdi).
AKTARIM_SOURCE_PREFIX = "HUKDOK_TESLIM"

MISSING_BUCKET_MANUAL = "MANUAL"     # elle açılmış kayıt — normal kova
MISSING_BUCKET_AKTARIM = "AKTARIM"   # aktarım kaynaklı kayıt — ayrı kova
MISSING_BUCKETS = (MISSING_BUCKET_MANUAL, MISSING_BUCKET_AKTARIM)


def _is_empty(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _norm(value) -> str:
    """Kapı karşılaştırmasının anahtarı: NULL→'', iç boşluk sadeleştir, kırp."""
    return " ".join(str(value or "").split())


def _party_field(party, name):
    if isinstance(party, dict):
        return party.get(name)
    return getattr(party, name, None)


def _is_counter(party) -> bool:
    """party_type boş gelirse KARŞI TARAF sayılır (eski kayıtlarda boş olabilir)."""
    return (_norm(_party_field(party, "party_type")) or "COUNTER") == "COUNTER"


def is_field_required(field_def: dict, case_data: dict) -> bool:
    """Alan BU kayıt için zorunlu mu? (kapı yoksa daima evet)"""
    gate = field_def.get("skip_when")
    if not gate:
        return True
    return _norm(case_data.get(gate["field"])) not in gate["in"]


def compute_missing_fields(case_data: dict, parties=None) -> list:
    """Eksik zorunlu alanları [{field, label}] listesi olarak döndürür."""
    missing = [
        {"field": f["field"], "label": f["label"]}
        for f in REQUIRED_CASE_FIELDS
        if is_field_required(f, case_data) and _is_empty(case_data.get(f["field"]))
    ]

    if parties is None:
        parties = case_data.get("parties") or []
    counters = [p for p in parties if _is_counter(p)]
    has_counter_tc = any(not _is_empty(_party_field(p, "tc_no")) for p in counters)
    if counters and not has_counter_tc:
        missing.append({"field": PARTY_TC_FIELD["field"], "label": PARTY_TC_FIELD["label"]})

    return missing


def compute_missing_bucket(missing_fields: list, is_aktarim: bool):
    """Kayıt hangi kovada? None = eksik yok (denormalize bayrağın değeri)."""
    if not missing_fields:
        return None
    return MISSING_BUCKET_AKTARIM if is_aktarim else MISSING_BUCKET_MANUAL


def is_aktarim_source(source) -> bool:
    """`case_history.source` imzası aktarımı mı gösteriyor? (SQL ikizi: starts_with)"""
    return str(source or "").startswith(AKTARIM_SOURCE_PREFIX)


# ─── SQL İKİZİ (Postgres) ────────────────────────────────────────────────────
#
# Yukarıdaki Python kurallarının SQL karşılığı. İKİNCİ BİR LİSTE DEĞİLDİR:
# aynı REQUIRED_CASE_FIELDS + kapı verisi gezilerek üretilir. Müşterileri:
#   * database.py madde 33 — `missing_required_bucket` kolonunun backfill'i
#   * case_manager.audit_missing_required_flags — bayat bayrak nöbetçisi
# Sıcak yol (liste filtresi) bunu KULLANMAZ; orada tek iş kolonu okumaktır (E6).
#
# Postgres'e özgüdür (regexp_replace/starts_with); sqlite testleri Python
# tarafını koşar, SQL tarafı `dbtest` işaretli testlerde gerçek DB'ye vurur.


def _sql_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _sql_norm(column_sql: str) -> str:
    """`_norm`un SQL ikizi: NULL→'', tüm boşluk dizileri tek boşluk, uçlar kırpık.

    `::text` cast'i tarih kolonlarını da kapsar (trim(date) Postgres'te hata
    verir); dolu bir tarih hiçbir zaman '' üretmez, dolayısıyla Python'daki
    "tarihte yalnız NULL boştur" kuralıyla aynı sonucu verir.
    """
    return f"btrim(regexp_replace(coalesce({column_sql}::text, ''), '\\s+', ' ', 'g'))"


def _sql_counter_party(table: str, extra: str = "") -> str:
    """COUNTER taraf EXISTS'i — `_is_counter` ile aynı boş-değer davranışı."""
    counter = f"coalesce(nullif({_sql_norm('p.party_type')}, ''), 'COUNTER') = 'COUNTER'"
    return (
        f"EXISTS (SELECT 1 FROM case_parties p "
        f"WHERE p.case_id = {table}.id AND {counter}{extra})"
    )


def missing_required_sql(table: str = "cases") -> str:
    """`compute_missing_fields(...) != []` ifadesinin SQL ikizi."""
    parts = []
    for f in REQUIRED_CASE_FIELDS:
        cond = f"{_sql_norm(table + '.' + f['field'])} = ''"
        gate = f.get("skip_when")
        if gate:
            values = ", ".join(_sql_literal(v) for v in gate["in"])
            gate_sql = f"{_sql_norm(table + '.' + gate['field'])} NOT IN ({values})"
            cond = f"({gate_sql} AND {cond})"
        parts.append(cond)

    has_counter = _sql_counter_party(table)
    has_tc = _sql_counter_party(table, f" AND {_sql_norm('p.tc_no')} <> ''")
    parts.append(f"({has_counter} AND NOT {has_tc})")
    return "(" + " OR ".join(parts) + ")"


def aktarim_kaydi_sql(table: str = "cases") -> str:
    """`case_history.source` imzasının SQL ikizi (LIKE DEĞİL: '_' joker olurdu)."""
    return (
        f"EXISTS (SELECT 1 FROM case_history h WHERE h.case_id = {table}.id "
        f"AND starts_with(h.source, {_sql_literal(AKTARIM_SOURCE_PREFIX)}))"
    )


def missing_bucket_sql(table: str = "cases") -> str:
    """`compute_missing_bucket`ın SQL ikizi — kova adı ya da NULL üretir."""
    return (
        f"CASE WHEN NOT {missing_required_sql(table)} THEN NULL "
        f"WHEN {aktarim_kaydi_sql(table)} THEN {_sql_literal(MISSING_BUCKET_AKTARIM)} "
        f"ELSE {_sql_literal(MISSING_BUCKET_MANUAL)} END"
    )
