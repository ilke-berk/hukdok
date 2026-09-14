"""G195 — `cases.status` CHECK kısıtı (NOT VALID): durum veritabanı düzeyinde yalnız üçlü.

Karar 020: `cases.status` yalnız DERDEST | DANIŞ | MAHZEN; temyiz/istinaf/karar AŞAMADIR.
Bugüne dek bu kural yalnız uygulama kapısındaydı (`constants.normalize_case_status`);
migrasyon madde 52 onu `ck_cases_status_uclu` CHECK kısıtıyla veritabanına indirir.

İki katman:

* **DB'siz** — CHECK ifadesinin değer listesi `constants.CASE_STATUSES`'ten üretilir
  (üretici çağrılır; liste testte elle kopyalanmaz); migrasyon op'u koşulsuz, idempotent
  (`IF NOT EXISTS` pg_constraint), `NOT VALID`, `VALIDATE` yok ve madde 50'den SONRA.
* **`dbtest`** — scratch Postgres (`test_migration_path` altyapısı; gerçek `hukudok`
  DB'sine asla yazılmaz, DB yoksa SKIP): `init_db()` kısıtı `convalidated=false` kurar,
  TEMYIZ reddedilir (`CheckViolation`, 23514), üçlü kabul edilir, ikinci `init_db()`
  idempotenttir; kısıttan önce var olan bozuk satır migrasyonu durdurmaz.
"""
import logging
import re

import pytest
from psycopg2 import errors as pg_errors
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import database
import test_migration_path as mig
from constants import CASE_STATUSES

# Scratch DB fixture'ı `test_migration_path`'ten yeniden kullanılır (test_perf_olcum deseni).
admin_engine = mig.admin_engine

KISIT = "ck_cases_status_uclu"
CHECK_VIOLATION = "23514"

# SQL tek tırnaklı literal ('' kaçışlı) — üretim kodunun kendi biçimlemesinden BAĞIMSIZ
# ayrıştırıcı; Postgres'in `pg_get_constraintdef` çıktısına da aynen uygulanır.
_LITERAL_RE = re.compile(r"'((?:[^']|'')*)'")


def _literaller(sql):
    return tuple(parca.replace("''", "'") for parca in _LITERAL_RE.findall(sql))


# ─── DB'siz: üretici ve migrasyon op'u ───────────────────────────────────────

def test_check_ifadesi_degerleri_case_statuses_ile_birebir():
    ifade = database.case_status_check_expr()
    assert ifade.startswith("status IN (") and ifade.endswith(")")
    assert _literaller(ifade) == CASE_STATUSES


def test_uretici_verilen_listeyi_kullanir_ve_tirnagi_kacirir():
    """Liste gerçekten parametreden gelir (sabit metin değil); SQL literal kaçışı doğru."""
    assert database.case_status_check_expr(("A", "O'B")) == "status IN ('A', 'O''B')"
    assert "CHECK (status IN ('X')) NOT VALID" in database.case_status_check_ddl(("X",))
    with pytest.raises(ValueError):
        database.case_status_check_expr(())


def test_migrasyon_opu_kosulsuz_idempotent_not_valid_ve_madde_50den_sonra():
    eslesen = [
        (sira, op) for sira, op in enumerate(database._MIGRATIONS)
        if op[0] == "index" and any(KISIT in sql for sql in op[2])
    ]
    assert len(eslesen) == 1, "kısıt tam bir koşulsuz ('index', ...) op'unda olmalı"
    sira, op = eslesen[0]
    assert database.CASE_STATUS_CHECK_NAME == KISIT
    assert op[1] == "cases"
    assert op[2] == [database.case_status_check_ddl()]

    ddl = op[2][0]
    assert f"CHECK ({database.case_status_check_expr()}) NOT VALID" in ddl
    assert "IF NOT EXISTS" in ddl and "pg_constraint" in ddl and f"conname = '{KISIT}'" in ddl
    # VALIDATE bu görevde yok — prod'da üçlü dışı = 0 ölçülünce ayrı görev
    assert not [
        sql for o in database._MIGRATIONS if o[0] == "index"
        for sql in o[2] if "VALIDATE CONSTRAINT" in sql.upper()
    ]

    # Madde 50'nin veri düzeltmesi ÖNCE koşmalı: sonra olsaydı onun
    # `SET case_stage = status` UPDATE'i eski satırda kısıta takılırdı.
    sira_50 = next(
        i for i, o in enumerate(database._MIGRATIONS)
        if o[0] == "index" and any("migrasyon_50_durum_uclusu" in s for s in o[2])
    )
    assert sira_50 < sira


# ─── dbtest: scratch veritabanında gerçek kısıt ──────────────────────────────

def _kisit_satirlari(engine):
    with engine.connect() as conn:
        return conn.execute(text(
            "SELECT convalidated, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = :ad AND conrelid = to_regclass('cases')"
        ), {"ad": KISIT}).all()


def _ekle(engine, tracking_no, status):
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO cases (tracking_no, status) VALUES (:t, :s)"),
            {"t": tracking_no, "s": status},
        )


def _check_ihlali(exc_info):
    orig = exc_info.value.orig
    assert isinstance(orig, pg_errors.CheckViolation), type(orig)
    assert orig.pgcode == CHECK_VIOLATION
    assert KISIT in str(orig)


@pytest.mark.dbtest
def test_init_db_kisiti_not_valid_kurar_ve_ucluyu_zorlar(admin_engine):
    with mig._scratch_database(admin_engine, "g195chk") as engine:
        mig._run_init_db(engine)

        satirlar = _kisit_satirlari(engine)
        assert len(satirlar) == 1, satirlar
        convalidated, tanim = satirlar[0]
        assert convalidated is False
        assert tanim.endswith("NOT VALID"), tanim
        # Postgres'in KENDİ çıktısındaki değerler — üçlüyle birebir (Türkçe Ş dahil)
        assert _literaller(tanim) == CASE_STATUSES, tanim

        for sira, durum in enumerate(CASE_STATUSES):
            _ekle(engine, f"G195/OK{sira}", durum)

        with pytest.raises(IntegrityError) as exc:
            _ekle(engine, "G195/TEMYIZ", "TEMYIZ")
        _check_ihlali(exc)

        with pytest.raises(IntegrityError) as exc:
            with engine.begin() as conn:
                conn.execute(text("UPDATE cases SET status = 'TEMYIZ' WHERE tracking_no = 'G195/OK0'"))
        _check_ihlali(exc)

        mig._run_init_db(engine)          # idempotent: hata yok, kısıt tek
        assert [satir[0] for satir in _kisit_satirlari(engine)] == [False]
        with engine.connect() as conn:
            durumlar = conn.execute(text(
                "SELECT status FROM cases WHERE tracking_no LIKE 'G195/OK_' ORDER BY tracking_no"
            )).scalars().all()
        assert durumlar == list(CASE_STATUSES)


@pytest.mark.dbtest
def test_kisittan_once_var_olan_bozuk_satir_init_dbyi_durdurmaz(admin_engine, caplog):
    with mig._scratch_database(admin_engine, "g195eski") as engine:
        mig._run_init_db(engine)
        # Kısıt yokken yazılmış eski satırlar (prod'daki durumun taklidi)
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE cases DROP CONSTRAINT {KISIT}"))
            conn.execute(text(
                "INSERT INTO cases (tracking_no, status) VALUES "
                "('G195/ESKI', 'TEMYIZ'), ('G195/SERBEST', 'Arşivde')"
            ))
        assert _kisit_satirlari(engine) == []

        caplog.clear()
        with caplog.at_level(logging.INFO, logger="database"):
            mig._run_init_db(engine)
        mesajlar = [kayit.getMessage() for kayit in caplog.records]
        assert any("Running migrations" in m for m in mesajlar), "log yakalanmadı — kontrol boşa geçerdi"
        assert [k.getMessage() for k in caplog.records if k.levelno >= logging.ERROR] == []

        assert [satir[0] for satir in _kisit_satirlari(engine)] == [False]
        with engine.connect() as conn:
            satirlar = dict(conn.execute(text(
                "SELECT tracking_no, status || '|' || coalesce(case_stage, '') FROM cases "
                "WHERE tracking_no IN ('G195/ESKI', 'G195/SERBEST')"
            )).all())
        # TEMYIZ satırı yerinde: madde 50 (kısıttan ÖNCE koşar) durumu üçlüye çekti, aşamayı korudu
        assert satirlar["G195/ESKI"] == "DERDEST|TEMYIZ"
        # Madde 50'nin tanımadığı serbest metin: NOT VALID mevcut satırı taramaz → dokunulmadı
        assert satirlar["G195/SERBEST"] == "Arşivde|"

        # Uyarı (dava-acma-akisi.md): bozuk eski satırın BAŞKA kolonunu değiştiren UPDATE de reddedilir
        with pytest.raises(IntegrityError) as exc:
            with engine.begin() as conn:
                conn.execute(text("UPDATE cases SET esas_no = '2026/1' WHERE tracking_no = 'G195/SERBEST'"))
        _check_ihlali(exc)
