"""
Database configuration with PostgreSQL and SQLite support.

Environment Variables:
- DATABASE_URL: Full database connection string
  - PostgreSQL: postgresql://user:password@host:port/database
"""
import os
import logging
import re
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import sys
from typing import Dict, Any

# Zorunlu alan kuralının SQL ikizi (madde 33 backfill'i). required_fields hiçbir
# şey import etmez — döngü riski yok; kural tek kaynaktan gelsin diye buradan
# çağrılır (elle yazılmış ikinci bir SQL listesi tutulmaz).
from required_fields import missing_bucket_sql

logger = logging.getLogger(__name__)


# Get database URL from environment
# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

# Enforce PostgreSQL
if not DATABASE_URL or not DATABASE_URL.startswith("postgresql"):
    logger.error("❌ CRITICAL: DATABASE_URL is not set or not a PostgreSQL URL.")
    logger.error("   PostgreSQL is now MANDATORY. SQLite support has been removed.")
    logger.error("   Please set DATABASE_URL in .env file.")
    sys.exit(1)

# PostgreSQL Configuration
logger.info("🐘 Using PostgreSQL database")

# ─── DB dayanıklılık sınırları (Faz 3-E, plan 3.6) ───────────────────────────
# pool_timeout: havuz doluyken bekleyen istek 10 sn'de TimeoutError alır —
#   önceden 30 sn varsayılanla kuyruklanıp nginx 300 sn'lik pencereyi yiyordu.
# connect_timeout: PG'ye ulaşılamıyorsa bağlantı denemesi 5 sn'de düşer
#   (varsayılan libpq davranışı dakikalarca askıda kalabilir).
# statement_timeout: tek sorgu 30 sn'yi aşarsa sunucu iptal eder — kilitli
#   satır/kaçak sorgu tüm havuzu rehin alamaz. libpq "options" ile bağlantı
#   bazında gider: YALNIZ bu engine'den açılan bağlantıları kapsar —
#   * gece pg_dump kendi bağlantısını kurar → kapsanmaz (etkilenmez),
#   * migrate.py import'tan ÖNCE DB_STATEMENT_TIMEOUT_MS=0 set eder →
#     create_all + backfill UPDATE'ler sınırsız koşar (30 sn'yi meşru aşabilir).
DB_POOL_TIMEOUT_SECONDS = 10
DB_CONNECT_TIMEOUT_SECONDS = 5
DB_STATEMENT_TIMEOUT_MS = int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "30000"))


def _build_connect_args(statement_timeout_ms: int) -> Dict[str, Any]:
    """psycopg2 connect kwargs'ları; 0/negatif timeout = statement_timeout yok."""
    args: Dict[str, Any] = {"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS}
    if statement_timeout_ms > 0:
        args["options"] = f"-c statement_timeout={statement_timeout_ms}"
    return args


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,      # Verify connections before using
    pool_size=10,            # Connection pool size
    max_overflow=20,         # Max overflow connections
    pool_recycle=3600,       # Recycle connections after 1 hour
    pool_timeout=DB_POOL_TIMEOUT_SECONDS,
    connect_args=_build_connect_args(DB_STATEMENT_TIMEOUT_MS),
    echo=False               # Set to True for SQL query logging
)


# SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
class Base(DeclarativeBase):
    pass

def get_db():
    """Dependency for FastAPI to get DB session.

    Faz 3-E (plan 3.6): handler istisnayla düşerse açık transaction burada
    rollback edilir — close() havuz reset'ine bırakmak, pool_pre_ping ve
    reset davranışına örtük güvenmekti; başarısız transaction'ın bağlantıda
    asılı kalması "idle in transaction (aborted)" birikimine yol açabiliyordu.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def init_db():
    """Initializes the database: Creates tables if not exist and runs migrations.

    Yapısal migrasyon hatası uygulamayı BAŞLATMAZ (sessiz şema sapması yerine
    fail-fast). Yalnızca performans amaçlı adımlar (pg_trgm) non-fatal'dır.
    """
    logger.info("🛠️ Initializing Database...")
    try:
        # Modelleri gerçekten import et ki Base.metadata dolsun: migrate.py
        # (Faz 1-A) yalnız bu modülü import eder — bu satır yokken create_all
        # sessiz no-op'tu ve YENİ tablolar ancak lifespan'deki yedek init_db
        # çağrısında (modeller route'lar üzerinden yüklüyken) oluşuyordu.
        # Faz 3-A'da upload_outbox ile tespit edildi; 3-E lifespan çağrısını
        # kaldıracağı için migrasyonun tek başına eksiksiz koşması şart.
        import models  # noqa: F401
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Tables created/verified.")

        # Run additional migrations (column updates etc.)
        check_and_migrate_tables()
    except Exception as e:
        logger.error(f"❌ Database Initialization Failed: {e}")
        raise e


# ─── ŞEMA MİGRASYONLARI (bildirimsel) ────────────────────────────────────────
#
# Sıra önemlidir (rename'ler ilgili kolon eklemelerinden önce gelmeli).
# Op türleri:
#   ("rename",  tablo, {eski_kolon: yeni_kolon})
#   ("columns", tablo, {kolon: DDL | (DDL, [kolon eklendikten sonra çalışacak SQL, ...])})
#   ("table",   tablo, CREATE_SQL, [index SQL, ...])
#   ("index",   tablo, [idempotent index DDL, ...])  — CREATE INDEX IF NOT EXISTS ya da
#                                       DROP INDEX IF EXISTS; koşulsuz koşar (bkz. madde 29)
#   ("drop",    tablo, [kolon, ...])  — kolonu VERİYLE BİRLİKTE siler; modeldeki tanım ve
#                                       "columns" op'undaki satır da kaldırılmış olmalı,
#                                       yoksa sonraki açılışta kolon geri eklenir
#
# DİKKAT — "table" ve "columns" op'ları KOŞULLUDUR: init_db() önce create_all() koşturur,
# migrasyon tablo/kolon listesini SONRA okur. Modelde tanımlı bir tablo/kolon create_all
# tarafından zaten yaratılmışsa ilgili op atlanır → gövdesine iliştirilmiş CREATE INDEX /
# UNIQUE kısıt ifadeleri o kurulumda HİÇ çalışmaz. Kalıcı olması istenen kısıt ve index
# DAİMA ayrı bir ("index", ...) op'una yazılır (madde 28 bu boşluğun kapatılmasıdır);
# "index" op'u koşulsuz koşar, IF NOT EXISTS onu idempotent kılar.
_MIGRATIONS = [
    # 1. SEQUENCE for Lawyers, DocTypes, Statuses
    ("columns", "lawyers",  {"sequence": "INTEGER DEFAULT 0"}),
    ("columns", "doctypes", {"sequence": "INTEGER DEFAULT 0"}),
    ("columns", "statuses", {"sequence": "INTEGER DEFAULT 0"}),

    # 2. CLIENTS (cari_kod, category, demografi + Excel import alanları)
    ("columns", "clients", {
        "cari_kod":           "VARCHAR(20)",
        "category":           "VARCHAR(50)",
        "birth_year":         "INTEGER",
        "gender":             "VARCHAR(20)",
        "specialty":          "VARCHAR(100)",
        "mobile_phone":       "VARCHAR(50)",
        # Excel import alanları (cari_mikro_guncellendi.xlsx)
        "il":                 "VARCHAR(100)",
        "sektor":             "VARCHAR(200)",
        "yevmiye_no":         "VARCHAR(50)",
        "noterlik":           "VARCHAR(200)",
        "vekaletname_tarihi": "DATE",
        "vekil_avukatlar":    "TEXT",
        "gecerlilik_tarihi":  "DATE",
        "vekalet_no":         "VARCHAR(50)",
        "buro_vekalet_no":    "VARCHAR(50)",
    }),

    # 3. CASES (service_type + Dava Açılış Excel alanları)
    ("columns", "cases", {
        "service_type":    "VARCHAR(20)",
        "acceptance_date": "DATE",             # İş Kabul Tarihi
        "bureau_type":     "VARCHAR(100)",     # Büro Özel Türü
        "sub_type_extra":  "VARCHAR(200)",     # Ek Alt Kırılım
        "judicial_unit":   "VARCHAR(200)",     # Yargı Birimi (2026-07-31 — formda vardı, kaydedilmiyordu)
    }),

    # 4. CASE_PARTIES (birth_year, gender)
    ("columns", "case_parties", {
        "birth_year": "INTEGER",
        "gender":     "VARCHAR(20)",
    }),

    # 5. CASE_DOCUMENTS (sharepoint_url, email_sent, email_error, case_party_id)
    ("columns", "case_documents", {
        "sharepoint_url": "TEXT",
        "email_sent":     "BOOLEAN",
        "email_error":    "TEXT",
        "case_party_id": (
            "INTEGER REFERENCES case_parties(id) ON DELETE SET NULL",
            # Backfill: mevcut muvekkil_adi değerlerini case_parties ile eşleştir
            ["""
                UPDATE case_documents cd
                SET case_party_id = cp.id
                FROM case_parties cp
                WHERE cd.case_id = cp.case_id
                  AND cd.muvekkil_adi IS NOT NULL
                  AND cd.case_party_id IS NULL
                  AND UPPER(cd.muvekkil_adi) = UPPER(cp.name)
            """],
        ),
    }),

    # 6. CASE_RELATIONS
    ("table", "case_relations", """
        CREATE TABLE case_relations (
            id SERIAL PRIMARY KEY,
            source_case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            target_case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            relation_type VARCHAR(30) NOT NULL DEFAULT 'ILGILI',
            note TEXT,
            created_by VARCHAR(100),
            created_at TIMESTAMPTZ DEFAULT now(),
            CONSTRAINT uq_case_relation UNIQUE (source_case_id, target_case_id)
        )
    """, [
        "CREATE INDEX idx_case_relations_source ON case_relations(source_case_id)",
        "CREATE INDEX idx_case_relations_target ON case_relations(target_case_id)",
    ]),

    # 7. CASES TRACKING — önce eski kolon adları düzeltilir, sonra yeniler eklenir
    ("rename", "cases", {
        "istinaf_tarihi": "istinaf_basvuru_tarihi",
        "istinaf_sonucu": "istinaf_karar_durumu",
        "temyiz_tarihi":  "temyiz_basvuru_tarihi",
        "temyiz_sonucu":  "temyiz_karar_durumu",
    }),
    ("columns", "cases", {
        # Mevcut (ilk set)
        "case_stage":                   "VARCHAR(50)",
        "dosya_son_durumu":             "VARCHAR(100)",
        "karar_tarihi":                 "DATE",
        "karar_turu":                   "VARCHAR(50)",
        "karar_lehine":                 "VARCHAR(20)",
        "istinaf_basvuru_tarihi":       "DATE",
        "istinaf_karar_durumu":         "VARCHAR(100)",
        "istinaf_karar_tarihi":         "DATE",
        "temyiz_basvuru_tarihi":        "DATE",
        "temyiz_karar_durumu":          "VARCHAR(100)",
        "temyiz_karar_tarihi":          "DATE",
        "kesinlesme_tarihi":            "DATE",
        "infaz_tarihi":                 "DATE",
        # Yeni — Yerel Karar
        "karar_no":                     "VARCHAR(50)",
        "karar_teblig_tarihi":          "DATE",
        "karar_aciklama":               "TEXT",
        # Yeni — İstinaf
        "istinaf_mahkemesi":            "VARCHAR(200)",
        "istinaf_esas_no":              "VARCHAR(50)",
        "istinaf_karar_no":             "VARCHAR(50)",
        "istinaf_karar_aciklama":       "TEXT",
        "istinaf_teblig_tarihi":        "DATE",
        # Yeni — Temyiz
        "temyiz_mahkemesi":             "VARCHAR(200)",
        "temyiz_esas_no":               "VARCHAR(50)",
        "temyiz_karar_no":              "VARCHAR(50)",
        "temyiz_eden_durumu":           "VARCHAR(100)",
        "temyiz_karar_aciklama":        "TEXT",
        "temyiz_teblig_tarihi":         "DATE",
        # Yeni — Karar Düzeltme
        "karar_duzeltme_durumu":        "VARCHAR(100)",
        "karar_duzeltme_esas_no":       "VARCHAR(50)",
        "karar_duzeltme_karar_no":      "VARCHAR(50)",
        "karar_duzeltme_tarihi":        "DATE",
        "karar_duzeltme_teblig_tarihi": "DATE",
        "karar_duzeltme_aciklama":      "TEXT",
        "yeni_esas_no":                 "VARCHAR(100)",
    }),

    # 8. EXCEL IMPORT ALANLARI (BIRLESIK_SONUC_v5)
    ("columns", "cases", {
        "klasor_no_2":    "TEXT",            # Eski sistem no — gizli, aranabilir
        "atama_tarihi":   "DATE",            # Atama Tarihi
        "hasar_dosya_no": "VARCHAR(200)",    # Hasar Dosya Numarası
        "hukuk_no":       "VARCHAR(100)",    # Hukuk Numarası
    }),

    # 8b. HEARING_DATES (hearing_time)
    ("columns", "hearing_dates", {"hearing_time": "VARCHAR(10)"}),

    # 10. TENANT ISOLATION — cases.tenant_id
    ("columns", "cases", {
        "tenant_id": ("VARCHAR(100)", ["CREATE INDEX IF NOT EXISTS idx_cases_tenant ON cases(tenant_id)"]),
    }),

    # 10b. TENANT ISOLATION — clients.tenant_id (IDOR-1)
    # Mevcut müvekkiller NULL ile bırakılır → her iki tenant erişmeye devam eder.
    # Yeni eklenenler add_client(data, tenant_id=...) ile damgalanır.
    ("columns", "clients", {
        "tenant_id": ("VARCHAR(100)", ["CREATE INDEX IF NOT EXISTS idx_clients_tenant ON clients(tenant_id)"]),
    }),

    # 9. CASE_STAGE_LOGS
    ("table", "case_stage_logs", """
        CREATE TABLE case_stage_logs (
            id SERIAL PRIMARY KEY,
            case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            stage VARCHAR(50) NOT NULL,
            changed_at TIMESTAMPTZ DEFAULT NOW(),
            changed_by VARCHAR(100),
            source VARCHAR(20) DEFAULT 'MANUAL',
            note TEXT
        )
    """, [
        "CREATE INDEX idx_stage_logs_case ON case_stage_logs(case_id)",
    ]),

    # 11. CASE_DOCUMENTS — uploaded_by_email
    ("columns", "case_documents", {
        "uploaded_by_email": (
            "VARCHAR(200)",
            ["CREATE INDEX IF NOT EXISTS idx_case_docs_uploader_email ON case_documents(uploaded_by_email)"],
        ),
    }),

    # 12. DAILY_ACTIVITY_REPORTS
    ("table", "daily_activity_reports", """
        CREATE TABLE daily_activity_reports (
            id SERIAL PRIMARY KEY,
            tenant_id VARCHAR(200),
            user_email VARCHAR(200) NOT NULL,
            report_date DATE NOT NULL,
            total_documents INTEGER DEFAULT 0,
            mailed_documents INTEGER DEFAULT 0,
            unmailed_documents INTEGER DEFAULT 0,
            error_documents INTEGER DEFAULT 0,
            unmailed_doc_ids TEXT,
            is_acknowledged BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT uq_daily_report UNIQUE (user_email, report_date)
        )
    """, [
        "CREATE INDEX idx_daily_reports_user ON daily_activity_reports(user_email, is_acknowledged)",
    ]),

    # 12b. DAILY_ACTIVITY_REPORTS — mailed_doc_ids, error_doc_ids
    ("columns", "daily_activity_reports", {
        "mailed_doc_ids": "TEXT",
        "error_doc_ids":  "TEXT",
    }),

    # 14. EXPORT_OUTBOX — hukukbot aktarım kuyruğu (docs/hukukbot-aktarim/PLAN.md §1)
    ("table", "export_outbox", """
        CREATE TABLE export_outbox (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL UNIQUE REFERENCES case_documents(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            nack_reason TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            delivered_at TIMESTAMPTZ
        )
    """, [
        "CREATE INDEX idx_export_outbox_status ON export_outbox(status)",
    ]),

    # 15. PERFORMANS INDEX'LERİ (KALITE_DENETIM_RAPORU §index eksikleri)
    # cases(updated_at, id): liste sıralaması ORDER BY updated_at DESC, id DESC ile birebir.
    ("index", "cases", [
        "CREATE INDEX IF NOT EXISTS idx_cases_updated_at_id ON cases (updated_at DESC, id DESC)",
    ]),
    ("index", "case_parties", [
        "CREATE INDEX IF NOT EXISTS idx_case_parties_case ON case_parties (case_id)",
    ]),
    ("index", "case_lawyers", [
        "CREATE INDEX IF NOT EXISTS idx_case_lawyers_case ON case_lawyers (case_id)",
    ]),
    ("index", "case_history", [
        "CREATE INDEX IF NOT EXISTS idx_case_history_case ON case_history (case_id)",
    ]),
    # case_id index'i models.HearingDate'te index=True ile zaten var (ix_ adı bilinçli
    # yeniden kullanılıyor → mevcut kurulumlarda no-op); hearing_date acil filtre için yeni.
    ("index", "hearing_dates", [
        "CREATE INDEX IF NOT EXISTS ix_hearing_dates_case_id ON hearing_dates (case_id)",
        "CREATE INDEX IF NOT EXISTS idx_hearing_dates_date ON hearing_dates (hearing_date)",
    ]),

    # 16. TANIDIK SORGU — case_parties.tc_no + TC lookup index'leri
    ("columns", "case_parties", {"tc_no": "VARCHAR(20)"}),
    ("index", "case_parties", [
        "CREATE INDEX IF NOT EXISTS idx_case_parties_tc_no ON case_parties (tc_no)",
    ]),
    ("index", "clients", [
        "CREATE INDEX IF NOT EXISTS idx_clients_tc_no ON clients (tc_no)",
    ]),

    # 17. AVUKAT ŞEHRİ — yönetim panelinde şehir listesinden seçilir
    ("columns", "lawyers", {"city": "VARCHAR(100)"}),

    # 18. CLIENT_POLICIES — otonom dava açma Faz 3 (plan Kararlar #3):
    # hekim başına kalıcı poliçe kaydı; intake analizinden beslenir,
    # müvekkil kartında listelenir, dönem çakışması uyarısı bu veriyle çalışır.
    ("table", "client_policies", """
        CREATE TABLE client_policies (
            id SERIAL PRIMARY KEY,
            client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
            police_no VARCHAR(100),
            police_turu VARCHAR(20),
            sigorta_sirketi VARCHAR(200),
            baslangic_tarihi DATE,
            bitis_tarihi DATE,
            retroaktif_tarihi DATE,
            sigortali_kurum VARCHAR(300),
            teminat_limiti NUMERIC(20,2),
            source_document TEXT,
            created_by VARCHAR(200),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """, [
        "CREATE INDEX idx_client_policies_client ON client_policies(client_id)",
    ]),

    # 19. TAZMINAT_TALEP_TARIHI GERI ALIMI — anket kararı (2026-07-31):
    # alan 2026-07-30'da eklendi, ofis "kaldırılsın" dedi; veri kaybı kabul.
    ("drop", "cases", ["tazminat_talep_tarihi"]),

    # 20. CASE_HISTORY İMZASI — otonom dava açma Faz 7 (zenginleştirme modu):
    # kim + hangi kaynaktan ("intake-enrich: tensip.pdf", "auto-enrich").
    # Mevcut kayıtlar NULL kalır (elle/legacy değişiklik).
    ("columns", "case_history", {
        "changed_by": "VARCHAR(200)",
        "source":     "VARCHAR(300)",
    }),

    # 21. SOFT-DELETE (dava + müvekkil) — 2026-08-05 büro mutabakatı:
    # silme kaydı korur (deleted_at/by/reason), listelerden gizler, admin geri alır.
    # Partial index: canlı sorgular deleted_at IS NULL filtresinden index beklemez;
    # admin "Silinenler" listesi IS NOT NULL tarar — index minik kalır.
    ("columns", "cases", {
        "deleted_at": ("TIMESTAMPTZ", [
            "CREATE INDEX IF NOT EXISTS idx_cases_deleted_at ON cases(deleted_at) WHERE deleted_at IS NOT NULL",
        ]),
        "deleted_by":    "VARCHAR(200)",
        "delete_reason": "TEXT",
    }),
    ("columns", "clients", {
        "deleted_at": ("TIMESTAMPTZ", [
            "CREATE INDEX IF NOT EXISTS idx_clients_deleted_at ON clients(deleted_at) WHERE deleted_at IS NOT NULL",
        ]),
        "deleted_by":    "VARCHAR(200)",
        "delete_reason": "TEXT",
    }),

    # 22. TKU NO + SISTEM NO — Full_Rapor_TKU aktarım hazırlığı (2026-08-05):
    # tku_no olay grup anahtarı (unique değil), sistem_no eski sistem kaydı (unique).
    # Yalnız DB + arama; UI gösterimi yok. PG'de unique index çoklu NULL'a izin verir.
    ("columns", "cases", {
        "tku_no":    ("VARCHAR(100)", ["CREATE INDEX IF NOT EXISTS idx_cases_tku_no ON cases(tku_no)"]),
        "sistem_no": ("VARCHAR(100)", ["CREATE UNIQUE INDEX IF NOT EXISTS uq_cases_sistem_no ON cases(sistem_no)"]),
    }),

    # 23. HÜKMEDILEN TUTARLAR — büro mutabakatı (2026-08-05): karar bloğuna
    # yapısal alanlar; NULL = girilmedi (default 0 bilinçli YOK).
    ("columns", "cases", {
        "hukmedilen_maddi":  "NUMERIC(20,2)",
        "hukmedilen_manevi": "NUMERIC(20,2)",
        "hukmedilen_toplam": "NUMERIC(20,2)",
    }),

    # 24. CASE_DOCUMENTS ARŞİV DURUMU — Faz 2-C (sertleştirme planı madde 2.6):
    # işlenmiş kopyanın SharePoint yükleme durumu; Faz 3-A retry kuyruğunun ve
    # belge kartındaki "arşivleme başarısız" göstergesinin temeli.
    # Backfill: URL'i olan eski kayıtlar uploaded; olmayanlar failed — URL yoksa
    # arşiv linki kullanılamaz, nedeni (yükleme mi URL kaydı mı) fark etmez.
    # Partial index: retry taraması failed/pending arar, uploaded çoğunluk dışarıda.
    ("columns", "case_documents", {
        "upload_status": (
            "VARCHAR(20) DEFAULT 'pending'",
            [
                "UPDATE case_documents SET upload_status = CASE "
                "WHEN sharepoint_url IS NOT NULL AND sharepoint_url <> '' "
                "THEN 'uploaded' ELSE 'failed' END",
                "CREATE INDEX IF NOT EXISTS idx_case_docs_upload_status "
                "ON case_documents(upload_status) WHERE upload_status <> 'uploaded'",
            ],
        ),
        "upload_attempts": "INTEGER DEFAULT 0",
    }),

    # 25. CASE_DOCUMENTS SOFT-DELETE — madde 21'deki dava/müvekkil kalıbının
    # belgelere genişletilmesi: silme kaydı korur, listelerden gizler, admin
    # geri alır; SharePoint arşiv kopyasına dokunulmaz. Partial index madde 21
    # ile aynı gerekçe: canlı sorgular IS NULL, admin listesi IS NOT NULL tarar.
    ("columns", "case_documents", {
        "deleted_at": ("TIMESTAMPTZ", [
            "CREATE INDEX IF NOT EXISTS idx_case_docs_deleted_at ON case_documents(deleted_at) WHERE deleted_at IS NOT NULL",
        ]),
        "deleted_by":    "VARCHAR(200)",
        "delete_reason": "TEXT",
    }),

    # 26. UPLOAD_OUTBOX PARTIAL INDEX — Faz 3-A: tablo create_all'dan gelir;
    # worker taraması yalnız pending satırları arar, uploaded/failed çoğunluk
    # dışarıda kalsın (idx_case_docs_upload_status ile aynı gerekçe).
    ("index", "upload_outbox", [
        "CREATE INDEX IF NOT EXISTS idx_upload_outbox_pending "
        "ON upload_outbox(next_attempt_at) WHERE status = 'pending'",
    ]),

    # 27. CASE_DOCUMENTS DÖNÜŞÜM KATMANI — Faz 3-F (plan 3.8 Katman 2):
    # dönüşüm başarısızsa orijinal kendi uzantısıyla arşivlenir, kayıt
    # conversion_status='pending' açılır, gece job'ı spool'daki orijinalden
    # yeniden dener. Mevcut kayıtlar NULL kalır (backfill YOK — 3-A kararı:
    # geçmiş failed belgelerin kaynak dosyası artık mevcut değil).
    # Partial index: gece taraması yalnız pending arar, çoğunluk (NULL) dışarıda.
    ("columns", "case_documents", {
        "conversion_status": (
            "VARCHAR(20)",
            [
                "CREATE INDEX IF NOT EXISTS idx_case_docs_conversion_pending "
                "ON case_documents(id) WHERE conversion_status = 'pending'",
            ],
        ),
        "conversion_attempts":   "INTEGER DEFAULT 0",
        "conversion_spool_path": "TEXT",
    }),

    # 28. TABLO OP'LARINA GÖMÜLÜ KISIT/INDEX'LERİN KURTARILMASI (FAZ D 6.1, G041)
    #
    # 6/9/12/14/18. maddelerdeki ("table", ...) op'ları modelde de tanımlı tabloları
    # yaratır; create_all onları önce yarattığı için op atlanır ve gövdesindeki
    # UNIQUE kısıt + CREATE INDEX ifadeleri hiç koşmaz (yukarıdaki DİKKAT şerhi).
    # Aşağısı o kalemleri GERÇEKTEN koşan "index" op'una taşır. Özgün satırlar
    # tablo op'larında bilinçli KALDI: tablo gerçekten yoksa (client_policies prod'da
    # böyle doğdu — ölçüldü) index'ler oradan gelir, IF NOT EXISTS iki yolu çakıştırmaz.
    #
    # UNIQUE'ler ALTER TABLE ADD CONSTRAINT ile DEĞİL, CREATE UNIQUE INDEX ile:
    # ADD CONSTRAINT idempotent değildir, ikinci açılışta patlar. İşlevsel fark yok
    # (PG unique kısıtı zaten unique index ile uygular), mükerrer veride ikisi de
    # migrasyonu DURDURUR — kasıtlı; bkz. _unique_index_duplicate_report.
    #
    # BURAYA ALINMAYAN ÜÇ KALEM (2026-08-12 ölçümü, mükerrer index üretirdi):
    #   idx_stage_logs_case        → case_stage_logs.case_id modelde index=True,
    #                                ix_case_stage_logs_case_id mevcut kurulumlarda VAR
    #   idx_export_outbox_status   → export_outbox.status modelde index=True,
    #                                ix_export_outbox_status VAR
    #   idx_client_policies_client → client_policies tablo op'undan doğduğu için
    #                                bu ad zaten VAR (create_all yolunda ise
    #                                ix_client_policies_client_id oluşur)
    # Üçünde de kolon her iki kurulum yolunda da index'li — eksik olan yalnız ADdır,
    # kapsama değil. Aynı kolona ikinci index eklemek G042'nin temizlik listesine
    # düşerdi. Testi ad değil KAPSAMA üzerinden kilitliyoruz
    # (tests/test_migration_path.py::test_table_op_index_niyetleri_semada_karsilikli).
    ("index", "case_relations", [
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_case_relation "
        "ON case_relations (source_case_id, target_case_id)",
        "CREATE INDEX IF NOT EXISTS idx_case_relations_source ON case_relations (source_case_id)",
        "CREATE INDEX IF NOT EXISTS idx_case_relations_target ON case_relations (target_case_id)",
    ]),
    ("index", "daily_activity_reports", [
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_daily_report "
        "ON daily_activity_reports (user_email, report_date)",
        "CREATE INDEX IF NOT EXISTS idx_daily_reports_user "
        "ON daily_activity_reports (user_email, is_acknowledged)",
    ]),
    # clients.name modelde index=True ama clients tablosu o tanımdan ÖNCE vardı:
    # create_all MEVCUT tabloya index eklemez → prod'da ix_clients_name yok (ölçüldü).
    # Sıfırdan kurulumda create_all zaten yaratır, burası no-op'a düşer.
    ("index", "clients", [
        "CREATE INDEX IF NOT EXISTS ix_clients_name ON clients (name)",
    ]),

    # ─── 30. EKSİK INDEX'LER (FAZ D 6.2-b, G043) ─────────────────────────────
    #
    # Madde 29 düşürür, burası ekler; ikisi birlikte 6.2'yi tamamlar.
    #
    # (a) INDEX'SİZ FK KOLONLARI. Liste tahminle değil sorguyla üretildi
    #     (pg_constraint contype='f' ∩ index'i olmayan kolonlar, 2026-08-12 lokal
    #     prod kopyası): 14 FK'nın 12'si zaten kapsanıyor, kapsanmayan İKİ tane
    #     çıktı — plan "4 kolon" diyordu, gerçek 2. Kapsayan index arayışı ADLA
    #     değil `indkey` önekiyle yapıldı; ör. case_relations.source_case_id'yi
    #     uq_case_relation (çok kolonlu UNIQUE) zaten karşılıyor.
    #     Index'siz FK'nın bedeli yalnız JOIN değil: referans verilen satır
    #     silinince/güncellenince PG referans eden tabloyu SEQ SCAN'le doğrular
    #     (case_documents.case_party_id ON DELETE SET NULL, case_lawyers.lawyer_id).
    ("index", "case_documents", [
        "CREATE INDEX IF NOT EXISTS idx_case_documents_case_party "
        "ON case_documents (case_party_id)",
    ]),
    ("index", "case_lawyers", [
        "CREATE INDEX IF NOT EXISTS idx_case_lawyers_lawyer "
        "ON case_lawyers (lawyer_id)",
    ]),
    #     ÜÇÜNCÜSÜ AYRI BİR SINIF: case_parties.client_id mevcut kurulumlarda
    #     index'li (ix_case_parties_client_id — ölçüldü), SIFIRDAN kurulumda ise
    #     DEĞİL: models.CaseParty.client_id'de `index=True` yok, index eski bir
    #     model tanımından kalmış. İki kurulum yolu farklı şema üretiyordu; bunu
    #     yeni testin FK sorgusu yakaladı (tahminle bulunmazdı). Mevcut ADI
    #     bilinçli yeniden kullanıyoruz — yeni bir ad prod'da aynı kolona İKİNCİ
    #     index koyar ve G042'nin temizlik listesine düşerdi. `ix_clients_name`
    #     (madde 27) ile aynı desen.
    ("index", "case_parties", [
        "CREATE INDEX IF NOT EXISTS ix_case_parties_client_id "
        "ON case_parties (client_id)",
    ]),

    # (b) cases.status KISMİ index'i. Sıcak değerler ÖLÇÜLDÜ, tahmin edilmedi
    #     (SELECT status, count(*) FROM cases GROUP BY 1 — 2026-08-12):
    #       MAHZEN  11.324 (%79)   ← arşiv; tüm tablonun dörtte üçü
    #       DERDEST  3.021 (%21)
    #     Tam index MAHZEN için de satır tutardı ve o değerde planlayıcı zaten
    #     seq scan seçerdi (seçicilik yok) — boşuna yazma maliyeti. Koşul
    #     `<> 'MAHZEN'` biçiminde yazıldı, IN listesiyle DEĞİL: yarın eklenecek
    #     bir statü (DANIŞ/TEMYIZ/KAPALI — routes/clients.py:85, required_fields)
    #     listede unutulursa index'e sessizce girmez; "arşiv hariç" kuralı ise
    #     kendiliğinden kapsar. PG kısmi index'i `status = 'DERDEST'` gibi bir
    #     koşulun predicate'i ima ettiğini görüp kullanır (EXPLAIN ile doğrulandı:
    #     count sorgusu 6,3 ms → 2,3 ms).
    ("index", "cases", [
        "CREATE INDEX IF NOT EXISTS idx_cases_status_sicak "
        "ON cases (status) WHERE status <> 'MAHZEN'",
    ]),

    # (c) substr(tracking_no, 4, 10) FONKSİYONEL index'i. routes/cases.py:139
    #     her dava açma formunda bu ifadeyle sıra numarası tahsis ediyor; düz
    #     kolon index'i ifadeye uygulanmaz, tek çare fonksiyonel index.
    #     Ölçüm (14.345 satır, lokal prod kopyası): seq scan 6,1 ms / 1.358 buffer
    #     → bitmap index scan 0,2 ms / 20 buffer (~30×).
    ("index", "cases", [
        "CREATE INDEX IF NOT EXISTS idx_cases_tracking_name_block "
        "ON cases (substr(tracking_no, 4, 10))",
    ]),

    # ─── 31. FAZ F ŞEMASI: 10 YENİ CASES KOLONU (G044) ───────────────────────
    #
    # Kaynak: docs/plan/faz-f-aktarim-gereksinimleri-2026-08-12.md §1.1.
    # Şartname bu kalemi "11 yeni kolon" diye sayar; on birincisi kolon DEĞİL
    # `case_esas_numbers` TABLOSUDUR (§1.3) ve G045'in işidir — burada 10 kolon var.
    #
    # Hepsi NULL kabul eder ve DEFAULT'suzdur: aktarım partiler hâlinde gelecek,
    # "henüz gelmedi" ile "boş bırakıldı" ayrımı 0/'' ile karartılmamalı
    # (hukmedilen_* kolonlarıyla aynı gerekçe, madde 23).
    #
    # İki alan KAPALI referans listesine bağlıdır — `iddia_edilen_kusur` →
    # alleged_faults, `istinaf_basvuran_taraf` → appealing_parties. Liste
    # TABLOLARI modelde tanımlı olduğu için create_all yaratır (calendar_events
    # / upload_outbox ile aynı yol); burada yalnız adı taşıyan denormalize
    # kolonlar açılır — diğer 13 liste de tam olarak böyle çalışır.
    # Kısıt/index EKLENMEDİ: bu on kolonun hiçbiri tekil değil ve bugün hiçbir
    # sorgunun filtresi değil; ölçülmemiş index eklemek G042'nin temizlediği
    # sınıftan borç üretirdi. FAZ F'nin sorguları ölçülünce eklenir.
    ("columns", "cases", {
        "islah_tutari":              "NUMERIC(20,2)",   # ıslahla EKLENEN miktar
        "arsiv_tarihi":              "DATE",            # dosya kapanış süresi analizi
        "istinaf_basvuran_taraf":    "VARCHAR(50)",     # kapalı liste (appealing_parties)
        "arabuluculuk_no":           "VARCHAR(100)",    # 435 föyde esas no yerine geçiyor
        "arabuluculuk_karar_tarihi": "DATE",
        "tibbi_surec":               "VARCHAR(300)",    # büyüyen sözlük
        "tibbi_olay":                "VARCHAR(300)",    # büyüyen sözlük (bugün 214 değer)
        "iddia_edilen_kusur":        "VARCHAR(200)",    # KAPALI liste (alleged_faults)
        "hastada_olusan_zarar":      "VARCHAR(300)",    # büyüyen sözlük (bugün 89 değer)
        "uygulanan_yontem":          "VARCHAR(200)",    # branşa göre kapalı liste
    }),

    # ─── 32. ESAS NUMARASI TARİHÇESİ TABLOSU (G045) ──────────────────────────
    #
    # Kaynak: docs/plan/faz-f-aktarim-gereksinimleri-2026-08-12.md §1.3.
    # Şartnamenin "11 yeni kolon" saydığı kalemin on birincisi kolon DEĞİL
    # tablodur; G044 on kolonu açtı, bu madde tabloyu tamamlıyor.
    #
    # TABLO burada ("table", ...) op'uyla YARATILMAZ — modelde tanımlı olduğu
    # için create_all yaratır (calendar_events / upload_outbox / G044'ün iki
    # referans listesiyle aynı yol). Yazılsaydı ölü kod olurdu: init_db önce
    # create_all koşturur, tablo listesini SONRA okur → op her kurulumda atlanır.
    #
    # KISIT VE INDEX'LER BU YÜZDEN ("index", ...) OP'UNDA — G041'in tamir ettiği
    # hatanın tekrarı tam olarak bunları tablo op'unun gövdesine gömmek olurdu;
    # oradan HİÇ koşmazlardı. "index" op'u koşulsuz koşar, IF NOT EXISTS
    # idempotent kılar.
    #
    #   uq_case_esas         → aynı davada aynı (esas, aşama) ikinci kez yazılamaz;
    #                          aktarım idempotency'sinin dayanağı (§0: teslim
    #                          partiler hâlinde ve düzeltme listeleriyle tekrar gelecek).
    #   uq_case_esas_current → dava başına EN FAZLA BİR is_current satırı. Türetme
    #                          kuralı ("cases.esas_no = is_current satırının kopyası")
    #                          bir yorum değil, ŞEMA kısıtıdır: ikinci doğruluk
    #                          kaynağı doğamaz. Kısmi index yalnız güncel satırları
    #                          tutar (dava sayısı kadar giriş).
    #   esas_no index'i      → aramanın müşterisi. Trigram BİLİNÇLİ YOK: G042
    #                          prod'da hiç taranmamış `idx_cases_esas_no_trgm`'i
    #                          (3.328 kB) düşürdü; ölçülmeden ikincisini eklemek
    #                          aynı borcu geri getirirdi. B-tree tam/önek
    #                          eşleşmesini karşılar — eski esasla arama tam
    #                          numarayla yapılır ("2021/588").
    ("index", "case_esas_numbers", [
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_case_esas "
        "ON case_esas_numbers (case_id, esas_no, stage)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_case_esas_current "
        "ON case_esas_numbers (case_id) WHERE is_current",
        "CREATE INDEX IF NOT EXISTS idx_case_esas_numbers_esas_no "
        "ON case_esas_numbers (esas_no)",
    ]),

    # ─── 33. EKSİK ZORUNLU ALAN BAYRAĞI (FAZ E 6 + FAZ F D2/D8, G046) ────────
    #
    # `missing_required` filtresi bugüne kadar satır başına korele EXISTS'lerle
    # (karşı taraf TC kuralı) + 13 kolonun trim kontrolüyle hesaplanıyordu.
    # Denormalize kova kolonu bunu tek kolon okumasına indirir; kolonu
    # `case_manager.refresh_missing_required` yazar, kural `required_fields`te.
    #
    # BACKFILL post-SQL'i required_fields'tan TÜRETİLİR — burada ikinci bir
    # kural listesi YOKTUR. Yalnız kolon YENİ EKLENDİĞİNDE koşar; bu doğrudur,
    # çünkü sıfırdan kurulan bir şemada (create_all kolonu zaten yaratır)
    # doldurulacak satır da yoktur. Kalıcı olması gereken bir kısıt/index
    # DEĞİLDİR — G041 tuzağı buraya uygulanmaz.
    #
    # INDEX BİLİNÇLİ EKLENMEDİ: lokal prod kopyasında (14.345 aktif dava,
    # 2026-08-12) zorunlu alanların en az biri kayıtların %100'ünde boş
    # (`service_type` 14.345, `uyap_lawyer_name` 14.344 satırda boş) — yani
    # bayrak bugün hiç seçici değil ve planlayıcı zaten seq scan seçer.
    # Ölçülmemiş index eklemek G042'nin temizlediği borcu geri getirirdi;
    # aktarım sonrası kova dağılımı ölçülünce yeniden değerlendirilir.
    ("columns", "cases", {
        "missing_required_bucket": (
            "VARCHAR(20) DEFAULT 'MANUAL'",
            [f"UPDATE cases SET missing_required_bucket = {missing_bucket_sql('cases')}"],
        ),
    }),

    # ─── 34. YEREL KARAR DURUMU KOLONU (G060) ────────────────────────────────
    #
    # Karar sonuçları resmi havuzlara bağlanır (DEGER_HAVUZLARI 2026-08-10).
    # Dört kapalı liste TABLOSU (local/appeal/cassation/revision_decisions)
    # modelde tanımlı olduğu için create_all yaratır — madde 31'deki
    # alleged_faults/appealing_parties ile aynı yol, tablo op'u gerekmez.
    # İstinaf/temyiz/karar düzeltme durum kolonları zaten var; YEREL kararın
    # liste bağlı kolonu yoktu — `karar_turu` 6 değere ezen AYRI bir kaba
    # alandır, davranışı değişmez. NULL + DEFAULT'suz (madde 31 gerekçesi:
    # "henüz girilmedi" '' ile karartılmaz). Index BİLİNÇLİ yok: alan bugün
    # tüm kayıtlarda boş (18.08 prod kopyası ölçümü) ve hiçbir sorgunun
    # filtresi değil; ölçülmeden index eklenmez (G042 dersi).
    ("columns", "cases", {
        "yerel_karar_durumu": "VARCHAR(100)",   # kapalı liste (local_decisions)
    }),

    # ─── 35. AŞAMA/KARAR TARİHÇESİ KISITI (G062) ─────────────────────────────
    #
    # `case_stage_decisions`: aynı yargı aşamasının birden çok kararını taşıyan
    # tarihçe tablosu (kanıt vakası id-2271: Danıştay 2023 Bozma + 2026 Onama —
    # cases'teki tek slot ikinciyi birincinin üstüne yazardı). Desen madde
    # 32'deki `case_esas_numbers`ın karar ikizi: tablo modelde tanımlı olduğu
    # için create_all yaratır, ("table", ...) op'u yazılsaydı ölü kod olurdu;
    # kısıt bu yüzden koşulsuz çalışan ("index", ...) op'unda (G041 kuralı).
    # Tek yazma yolu `managers/stage_decisions.py`; her yazım sonrası aşamanın
    # en yüksek sira_no'lu satırı cases'teki tek-slot kolonlara fotoğraf olarak
    # senkronlanır.
    #
    #   uq_case_stage_decision → aynı davada aynı aşamanın sıra numarası tekil.
    #                            Sıralama ve "son karar" seçimi (fotoğraf) bu
    #                            üçlüye dayanır, TARİHE DEĞİL (tasarım paketi:
    #                            170 föyde karar tarihleri güvenilmez). FAZ F
    #                            aktarımı tekrar tekrar koşacağı için
    #                            idempotency'nin de dayanağıdır.
    #
    #   idx_..._kaynak         → kaynak_id self-FK'sının index'i. Sorgu filtresi
    #                            olduğu için DEĞİL, G043'ün FK kuralı gereği:
    #                            index'siz FK, referans verilen satırın
    #                            silinmesini (admin düzeltme yolu tam da bunu
    #                            yapar) tabloyu SEQ SCAN'le doğrulamaya zorlar;
    #                            test_g043_index_ve_avukat_filtresi.py'nin
    #                            "index'siz FK kolonu kalmadı" bekçisi bunu
    #                            şema kuralı olarak kilitler.
    #
    # Başka index YOK (G042 dersi): `case_id`yi unique'in ÖNEK kolonu zaten
    # karşılar; kalan kolonlar bugün hiçbir sorgunun filtresi değil ve tablo
    # sıfırdan doğuyor (slot alanları prod'da 0 dolu, 18.08 ölçümü) —
    # ölçülmeden index eklenmez.
    ("index", "case_stage_decisions", [
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_case_stage_decision "
        "ON case_stage_decisions (case_id, stage, sira_no)",
        "CREATE INDEX IF NOT EXISTS idx_case_stage_decisions_kaynak "
        "ON case_stage_decisions (kaynak_id)",
    ]),
]

# ─── 29. KULLANILMAYAN/MÜKERRER INDEX TEMİZLİĞİ (FAZ D 6.2, G042) ─────────────
#
# PAZARLIKSIZ KURAL: `idx_scan` index TARAMALARINI sayar; UNIQUE kısıt doğrulaması
# (INSERT/UPDATE tekillik kontrolü) o sayacı ARTIRMAZ. Görevini kusursuz yapan bir
# UNIQUE index ömrü boyunca `idx_scan = 0` görünür. Prod ölçümünde (2026-08-12)
# `idx_scan = 0` olan 96 index'in 44'ü unique/primary'ydi — "kullanılmayanı düşür"
# körlemesine uygulansaydı ofis no tekilliğini TEK BAŞINA tutan `ix_cases_tracking_no`
# (indisunique=true, pg_constraint karşılığı YOK) da silinirdi.
#
# Bu liste bu yüzden iki dar ölçütle üretildi (scripts/index_envanteri.py):
#
#   (A) YAPISAL İKİZ — `indkey` + opclass + access method + kısmi koşul imzası
#       birebir aynı ikinci bir index var. İstatistikten BAĞIMSIZ güvenli: kalan
#       ikiz planlayıcı için aynı işi görür. `ix_cases_id` prod'da 38.993 kez
#       tarandı — "kullanılıyor" ama `cases_pkey` ile birebir aynı, tarama ona
#       geçer. İmza ADLA değil `pg_index.indkey` ile karşılaştırılır: bu şemada
#       `ix_`/`idx_` isimlendirmesi tutarlı DEĞİL.
#   (B) PROD'DA HİÇ TARANMAMIŞ TRIGRAM — yalnız §6.0'da PROD'da ölçülmüş altı
#       `cases` GIN index'i (~26 MB). Ölçülmemiş trigram index'lerine (özellikle
#       `idx_case_parties_name_trgm` — routes/cases.py:162 taraf aramasının
#       müşterisi) DOKUNULMADI. Lokal restore kopyasında sayaçlar sıfırlanmış
#       olduğu için "lokalde 0" tek başına gerekçe SAYILMAZ.
#
# Üç `*_case_id` ikizinde modelin `index=True` ürettiği taraf düşürülür, migrasyonun
# yarattığı `idx_*_case` KALIR: prod'da `idx_case_parties_case` 1.810.671 taramayla
# şemanın en sıcak index'i; ikizini düşürmek planı hiç oynatmaz. models.py DEĞİŞMEZ
# (kapsam dışı) — sıfırdan kurulumda create_all bu index'leri yaratır, migrasyon
# hemen sonra düşürür; sonuç iki kurulum yolunda da AYNI şemadır.
#
# DROP'lar ("index", ...) op'una yazılır (koşulsuz koşar) ve IF EXISTS ile
# idempotenttir. Trigram index'leri AYRICA `_TRGM_INDEXES` sözlüğünden çıkarıldı —
# yoksa aşağıdaki pg_trgm bloğu her açılışta yeniden yaratır ve temizlik hiç tutmaz.
_DUSURULECEK_INDEXLER = {
    # (A) PK ikizi — `ix_<tablo>_id`, modeldeki `id = Column(..., index=True)`den
    # doğar ve tablonun PRIMARY KEY index'iyle birebir aynıdır.
    "analysis_cache":         ["ix_analysis_cache_file_hash"],   # PK = file_hash
    "bureau_types":           ["ix_bureau_types_id"],
    "calendar_events":        ["ix_calendar_events_id"],
    "case_relations":         ["ix_case_relations_id"],
    "case_stage_logs":        ["ix_case_stage_logs_id"],
    "case_subjects":          ["ix_case_subjects_id"],
    "cities":                 ["ix_cities_id"],
    "client_categories":      ["ix_client_categories_id"],
    "court_types":            ["ix_court_types_id"],
    "daily_activity_reports": ["ix_daily_activity_reports_id"],
    "doctypes":               ["ix_doctypes_id"],
    "email_recipients":       ["ix_email_recipients_id"],
    "export_outbox":          ["ix_export_outbox_id"],
    "file_statuses":          ["ix_file_statuses_id"],
    "file_types":             ["ix_file_types_id"],
    "hearing_dates":          ["ix_hearing_dates_id"],
    "lawyers":                ["ix_lawyers_id"],
    "party_roles":            ["ix_party_roles_id"],
    "specialties":            ["ix_specialties_id"],
    "statuses":               ["ix_statuses_id"],
    "sync_logs":              ["ix_sync_logs_id"],
    "upload_outbox":          ["ix_upload_outbox_id"],
    "clients":                ["ix_clients_id"],
    "case_documents":         ["ix_case_documents_id"],
    # (A) PK ikizi + kolon ikizi aynı tabloda
    "case_history":           ["ix_case_history_id", "ix_case_history_case_id"],
    "case_lawyers":           ["ix_case_lawyers_id", "ix_case_lawyers_case_id"],
    "case_parties":           ["ix_case_parties_id", "ix_case_parties_case_id"],
    # (A) PK ikizi + (B) prod'da hiç taranmamış altı GIN trigram index'i
    "cases": [
        "ix_cases_id",
        "idx_cases_subject_trgm",       # 6.112 kB (prod)
        "idx_cases_tracking_no_trgm",   # 5.472 kB
        "idx_cases_court_trgm",         # 5.424 kB
        "idx_cases_klasor_no_2_trgm",   # 3.528 kB
        "idx_cases_esas_no_trgm",       # 3.328 kB
        "idx_cases_resp_lawyer_trgm",   # 3.032 kB
    ],
}

_MIGRATIONS += [
    ("index", tablo, [f"DROP INDEX IF EXISTS {ad}" for ad in adlar])
    for tablo, adlar in _DUSURULECEK_INDEXLER.items()
]

# 13. TRIGRAM ARAMA INDEX'LERI (pg_trgm) — yalnızca performans, hatası fatal değil.
# Arama ilike '%term%' (baştan wildcard) kullanıyor → B-tree index işe yaramaz,
# her sorgu full table scan. GIN + gin_trgm_ops index'i bu kalıbı hızlandırır.
#
# G042: `cases` üzerindeki altı büyük trigram index'i (esas_no, tracking_no,
# klasor_no_2, court, subject, responsible_lawyer_name) BURADAN ÇIKARILDI —
# prod'da hiçbiri hiç taranmamıştı (~26 MB) ve madde 29 onları düşürüyor.
# Sözlükte kalsalardı bu blok her açılışta yeniden yaratır, temizlik hiç tutmazdı.
# Kalanlar bilinçli duruyor: prod'da taranıp taranmadıkları ÖLÇÜLMEDİ ve
# `idx_case_parties_name_trgm`'in gerçek müşterisi var (routes/cases.py:162).

# ─── AVUKAT ADI ASCII KATLAMASININ SQL KARŞILIĞI (G043) ──────────────────────
#
# managers/lawyer_resolver._TR_FOLD'un birebir SQL ikizi. Avukat filtresi artık
# eşleştirmeyi SQL'de ön-eliyor (managers/case_manager._lawyer_filter_case_ids);
# katlama olmadan '%ungor%' ile "ÜNGÖR" bulunamaz.
#
# PAZARLIKSIZ: aşağıdaki fonksiyonel trigram index'i ile sorgunun ürettiği ifade
# BİREBİR aynı olmalıdır — Postgres ifade index'ini metin olarak değil ayrıştırılmış
# ifade ağacı olarak eşler; translate() argümanlarının bir karakteri bile farklıysa
# index sorguya HİÇ uygulanmaz (sessiz performans kaybı, hata vermez). Bu yüzden
# harita tek kaynak olarak burada durur ve case_manager BURADAN import eder.
# tests/test_g043_index_ve_avukat_filtresi.py üç tarafı da (Python haritası, bu
# sabitler, index DDL'i) birbirine kilitler.
SQL_FOLD_FROM = "ıİIşŞçÇğĞöÖüÜâÂîÎûÛ"
SQL_FOLD_TO = "iiissccggoouuaaiiuu"


def sql_folded_expr(column_sql: str) -> str:
    """`column_sql` için ASCII'ye katlanmış küçük harf SQL ifadesi."""
    return (
        f"lower(translate(coalesce({column_sql}, ''), "
        f"'{SQL_FOLD_FROM}', '{SQL_FOLD_TO}'))"
    )


# NOT (G043): trigram index'leri BİLİNÇLİ olarak ("index", ...) op'una değil bu
# sözlüğe yazılır. "index" op'ları migrasyon döngüsünde, yani aşağıdaki
# `CREATE EXTENSION IF NOT EXISTS pg_trgm`den ÖNCE koşar; sıfırdan bir kurulumda
# gin_trgm_ops henüz yoktur ve DDL patlayınca migrasyon FAIL-FAST ile konteyneri
# durdurur. Bu blok ise hata-toleranslıdır (index yoksa sorgu yavaşlar, uygulama
# ayakta kalır). Sözlük değeri kolon ADI ya da parantezli İFADE olabilir; ikisi de
# aynı `USING gin (<x> gin_trgm_ops)` şablonuna girer.
_TRGM_INDEXES = {
    # cases — kimlik ve metin alanları
    "idx_cases_uyap_lawyer_trgm": ("cases", "uyap_lawyer_name"),
    "idx_cases_tku_no_trgm":      ("cases", "tku_no"),
    "idx_cases_sistem_no_trgm":   ("cases", "sistem_no"),
    # ilişkili tablolar — taraf / avukat adları
    "idx_case_parties_name_trgm": ("case_parties", "name"),
    "idx_case_lawyers_name_trgm": ("case_lawyers", "name"),
    # G043 — avukat filtresinin SQL ön-elemesinin müşterisi. G042 ham kolonun
    # trigram index'ini (idx_cases_resp_lawyer_trgm) düşürdü: prod'da hiç
    # taranmamıştı, çünkü o gün filtre SQL'de DEĞİL Python'daydı. Yerine geçen
    # bu index katlanmış ifadeyi indeksler ve gerçek müşterisi vardır — ölçüm:
    # 159 avukat seçimi, ortalama 47,4 ms → 3,0 ms (~16×), boyut 304 kB.
    "idx_cases_resp_lawyer_fold_trgm": (
        "cases", f"({sql_folded_expr('responsible_lawyer_name')})",
    ),
}


# ─── UNIQUE index savunması ──────────────────────────────────────────────────
#
# Mükerrer veri üzerinde CREATE UNIQUE INDEX patlar ve migrasyon durur; DURMASI
# doğrudur (sessizce atlamak şemayı sessizce saptırır, sonraki adımlar tekilliğin
# var olduğunu varsayar). Kusurlu olan mesajdır: PG "duplicate key value violates
# unique constraint" der, hangi tabloda kaç grup olduğunu söylemez. Aşağıdaki
# ön kontrol mükerrerleri sayıp örnek anahtarlarla raporlar — konteyner yine
# kalkmaz, ama nöbetçi ne yapacağını bilir.
_UNIQUE_INDEX_RE = re.compile(
    r"CREATE\s+UNIQUE\s+INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>\w+)\s+"
    r"ON\s+(?P<table>\w+)\s*\((?P<cols>[^()]*)\)\s*(?P<rest>.*)$",
    re.IGNORECASE | re.DOTALL,
)
_SIMPLE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _unique_index_duplicate_report(conn, sql: str):
    """UNIQUE index SQL'i mükerrer veriye takılacaksa anlaşılır özet, değilse None.

    Yalnız `CREATE UNIQUE INDEX ... ON tablo (kolon, ...) [WHERE ...]` biçimindeki
    düz kolon index'lerini denetler; ifade index'i gibi ayrıştırılamayan biçimlerde
    None döner — koruma o zaman Postgres'in kendi hatasıdır (migrasyon yine durur,
    yalnız mesaj ham kalır).

    NULL içeren satırlar dışlanır: PG'de çoklu NULL unique index'i ihlal etmez,
    GROUP BY ise NULL'ları eşit sayar → dışlanmasa yanlış alarm üretirdi.
    """
    from sqlalchemy import text

    match = _UNIQUE_INDEX_RE.match(sql.strip())
    if not match:
        return None
    name, table = match.group("name"), match.group("table")
    rest = match.group("rest").strip().rstrip(";")
    if rest and not rest.upper().startswith("WHERE"):
        return None
    columns = [col.strip() for col in match.group("cols").split(",")]
    if not _SIMPLE_IDENTIFIER_RE.match(table) or not all(
        _SIMPLE_IDENTIFIER_RE.match(col) for col in columns
    ):
        return None

    # Index zaten varsa mükerrer de olamaz (index'in kendisi engelliyor) — her
    # açılışta tabloyu boşuna taramayalım.
    if conn.execute(text("SELECT to_regclass(:n)"), {"n": name}).scalar() is not None:
        return None

    conditions = [f"{col} IS NOT NULL" for col in columns]
    if rest:
        conditions.append(f"({rest[len('WHERE'):].strip()})")
    where_sql = " AND ".join(conditions)
    col_list = ", ".join(columns)

    group_count = conn.execute(text(
        f"SELECT COUNT(*) FROM (SELECT 1 FROM {table} WHERE {where_sql} "
        f"GROUP BY {col_list} HAVING COUNT(*) > 1) d"
    )).scalar() or 0
    if not group_count:
        return None

    samples = conn.execute(text(
        f"SELECT {col_list}, COUNT(*) AS n FROM {table} WHERE {where_sql} "
        f"GROUP BY {col_list} HAVING COUNT(*) > 1 ORDER BY n DESC, {col_list} LIMIT 3"
    )).all()
    ornekler = "; ".join(
        "(" + ", ".join(repr(value) for value in row[:-1]) + f") ×{row[-1]}"
        for row in samples
    )
    return (
        f"UNIQUE index '{name}' oluşturulamaz: {table}({col_list}) üzerinde "
        f"{group_count} mükerrer grup var. Örnekler: {ornekler}. "
        "Migrasyon bilinçli olarak durdu — önce mükerrer satırları temizleyin."
    )


def check_and_migrate_tables():
    """Şemayı _MIGRATIONS listesine göre günceller (idempotent).

    Yapısal bir adım başarısız olursa RuntimeError fırlatır → init_db başarısız
    olur ve uygulama ayağa kalkmaz. Önceki davranış (logla ve devam et) sessiz
    şema sapmasına yol açıyordu.
    """
    from sqlalchemy import text, inspect

    db_type = engine.dialect.name
    logger.info(f"Running migrations for {db_type}")

    with engine.connect() as conn:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())

        def _exec(sql: str, context: str):
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Migration error for {context}: {e}")
                raise RuntimeError(f"Migration failed for {context}: {e}") from e

        def _guard_unique_index(sql: str, context: str):
            """UNIQUE index'ten önce mükerrer ön kontrolü; sorun varsa fail-fast.

            Ön kontrolün KENDİSİ patlarsa (yetki, beklenmedik biçim) migrasyon
            durdurulmaz — WARNING'le geçilir ve asıl DDL yine denenir; mükerrer
            varsa PG'nin ham hatası kapıyı zaten kapatır. Nihai ERROR init_db'de
            tek satır olarak basılır (log sözleşmesi).
            """
            try:
                report = _unique_index_duplicate_report(conn, sql)
            except Exception as e:
                conn.rollback()
                logger.warning(f"Mükerrer ön kontrolü koşturulamadı ({context}): {e}")
                return
            if report:
                raise RuntimeError(report)

        for op in _MIGRATIONS:
            kind, table = op[0], op[1]
            if kind == "rename":
                if table not in tables:
                    continue
                columns = {col["name"] for col in inspector.get_columns(table)}
                for old_name, new_name in op[2].items():
                    if old_name in columns and new_name not in columns:
                        _exec(f'ALTER TABLE {table} RENAME COLUMN {old_name} TO {new_name}',
                              f"{table}.{old_name}→{new_name}")
                        logger.info(f"Renamed {table}.{old_name} → {new_name}")

            elif kind == "columns":
                if table not in tables:
                    continue
                columns = {col["name"] for col in inspector.get_columns(table)}
                for col_name, spec in op[2].items():
                    if col_name in columns:
                        continue
                    ddl, post_sql = (spec, []) if isinstance(spec, str) else spec
                    _exec(f'ALTER TABLE {table} ADD COLUMN {col_name} {ddl}', f"{table}.{col_name}")
                    for sql in post_sql:
                        _exec(sql, f"{table}.{col_name} (post)")
                    logger.info(f"Added {col_name} to {table}")

            elif kind == "drop":
                if table not in tables:
                    continue
                columns = {col["name"] for col in inspector.get_columns(table)}
                for col_name in op[2]:
                    if col_name not in columns:
                        continue
                    _exec(f'ALTER TABLE {table} DROP COLUMN {col_name}', f"{table}.{col_name} (drop)")
                    logger.info(f"Dropped {col_name} from {table}")

            elif kind == "table":
                if table in tables:
                    continue
                create_sql, index_sqls = op[2], op[3]
                _exec(create_sql, table)
                for sql in index_sqls:
                    _exec(sql, f"{table} (index)")
                tables.add(table)
                logger.info(f"Created {table} table")

            elif kind == "index":
                if table not in tables:
                    continue
                for sql in op[2]:
                    _guard_unique_index(sql, f"{table} (index)")
                    _exec(sql, f"{table} (index)")

        # pg_trgm — performans amaçlı; yetki/uzantı eksikse uygulamayı durdurmaz
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            conn.commit()
            for idx_name, (tbl, col) in _TRGM_INDEXES.items():
                if tbl not in tables:
                    continue
                try:
                    conn.execute(text(
                        f"CREATE INDEX IF NOT EXISTS {idx_name} "
                        f"ON {tbl} USING gin ({col} gin_trgm_ops)"
                    ))
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Trigram index error for {idx_name}: {e}")
            logger.info("Trigram (pg_trgm) arama index'leri hazır")
        except Exception as e:
            conn.rollback()
            logger.error(f"pg_trgm extension/index migration error: {e}")

# --- CLIENT DATA HELPERS ---

def get_normalized_clients() -> Dict[str, Any]:
    """
    Fetches all clients from DB and normalizes them for FlashText/Search.
    Returns: Dict[normalized_name -> List[original_name]]
    """
    from models import Client
    from client_normalizer import clean_name, PRE_COMPILED_SPLIT_PATTERN

    db = SessionLocal()
    try:
        clients = db.query(Client).filter(
            Client.active.is_(True),
            Client.deleted_at.is_(None),
        ).all()
        normalized_map: Dict[str, list] = {}
        for c in clients:
            raw_name = c.name
            parts = PRE_COMPILED_SPLIT_PATTERN.split(raw_name)
            for part in parts:
                cleaned = clean_name(part)
                if cleaned:
                    if cleaned not in normalized_map:
                        normalized_map[cleaned] = []
                    if raw_name not in normalized_map[cleaned]:
                        normalized_map[cleaned].append(raw_name)
        return normalized_map
    except Exception as e:
        logger.error(f"Error fetching normalized clients: {e}")
        return {}
    finally:
        db.close()
