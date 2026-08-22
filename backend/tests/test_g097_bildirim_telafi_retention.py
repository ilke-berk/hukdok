"""G097 — bildirim tarayıcısı: boot telafisi + retention + tz/duruşma sınırı.

Kilitlenen davranışlar:
  1. lider boot'unda `boot_catch_up_scan` thread'i `is_leader` bloğunun İÇİNDE
     başlar (AST; kapı dışına çıkarsa N worker N kez tarar),
  2. telafi istisnayı yutar: lifespan devam eder, TEK WARNING, sıfır ERROR,
  3. aynı gün cron + telafi satır ikilemez; kaçırılan T-7 günü T-5'te en dar
     eşikle (`:7:`) telafi edilir; kaçan T-1 (son gün geçmiş) telafi EDİLMEZ,
  4. retention: okunmuş+eski silinir, okunmuş+yeni kalır, okunmamış+eski KALIR;
     süre tek yerde, env ile ayarlanır, bozuk env varsayılana düşer,
  5. purge `scan_deadlines` dönüşünde `purged`; okunmamış-eski sayacı loglanır,
  6. `bugun_tr()` UTC 22:30 → TR ertesi gün,
  7. duruşma sorgusu üst sınırlı: 30 gün sonraki duruşma SQL'de elenir
     (`esik_sec`'e hiç ulaşmaz).

Testler süreç içi sqlite (StaticPool) üzerinde GERÇEK sorgu koşar (G085 deseni).
"""
import ast
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

DOMAIN = "hanyaloglu-acar.av.tr"
MAIL_SERAP = f"serap.turgal@{DOMAIN}"

# Kaydırmasız zincir (G085 ile aynı): 01.10.2026 tebliğ → 15.10.2026 son gün.
TEBLIG = date(2026, 10, 1)
SON_GUN = date(2026, 10, 15)

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _notifications_index_ddls() -> list[str]:
    import database

    return [
        ddl
        for op in database._MIGRATIONS
        if op[0] == "index" and op[1] == "notifications"
        for ddl in op[2]
    ]


@pytest.fixture()
def env(monkeypatch):
    from database import Base
    import models  # noqa: F401
    from services import deadline_scanner as scanner
    from services import notifications as svc

    monkeypatch.setenv("NOTIFICATION_DOMAINS", DOMAIN)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for ddl in _notifications_index_ddls():
            conn.execute(text(ddl))
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def _avukat():
        db = maker()
        try:
            db.add(models.Lawyer(code="STG", name="Serap Turgal", email=MAIL_SERAP, gorev="AVUKAT", active=True))
            db.commit()
        finally:
            db.close()

    def _dava() -> int:
        db = maker()
        try:
            row = models.Case(
                tracking_no="2024/1234", esas_no="2024/55",
                court="Ankara 1. Asliye Hukuk Mahkemesi",
                responsible_lawyer_name="Av. Serap Turgal",
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return int(row.id)
        finally:
            db.close()

    def _karar(case_id: int) -> int:
        db = maker()
        try:
            row = models.CaseStageDecision(
                case_id=case_id, stage="YEREL", sira_no=1,
                teblig_tarihi=TEBLIG, dogrulama_durumu="BELGE",
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return int(row.id)
        finally:
            db.close()

    def _durusma(case_id: int, hearing_date: date) -> int:
        db = maker()
        try:
            row = models.HearingDate(case_id=case_id, hearing_date=hearing_date, hearing_time="09:43")
            db.add(row)
            db.commit()
            db.refresh(row)
            return int(row.id)
        finally:
            db.close()

    def _bildirim(*, created_at: datetime, read: bool, key: str) -> int:
        """Doğrudan satır: created_at/read_at test tarafından belirlenir."""
        db = maker()
        try:
            row = models.Notification(
                recipient_email=MAIL_SERAP, type="sure_yaklasti", severity="info",
                title="t", body="b", dedupe_key=key, created_at=created_at,
                read_at=created_at if read else None,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return int(row.id)
        finally:
            db.close()

    def _bildirimler():
        db = maker()
        try:
            return db.query(models.Notification).order_by(models.Notification.id).all()
        finally:
            db.close()

    def _tara(bugun: date):
        db = maker()
        try:
            return scanner.scan_deadlines(bugun=bugun, db=db)
        finally:
            db.close()

    def _purge(bugun: date) -> int:
        db = maker()
        try:
            return svc.purge_old_notifications(bugun=bugun, db=db)
        finally:
            db.close()

    yield SimpleNamespace(
        models=models, scanner=scanner, svc=svc, sessions=maker,
        avukat=_avukat, dava=_dava, karar=_karar, durusma=_durusma,
        bildirim=_bildirim, bildirimler=_bildirimler, tara=_tara, purge=_purge,
    )
    engine.dispose()


# ─── (a) boot telafisi ───────────────────────────────────────────────────────

def _lifespan_node() -> ast.AST:
    tree = ast.parse((BACKEND_DIR / "api.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == "lifespan":
            return node
    raise AssertionError("api.py'de lifespan bulunamadı")


def test_boot_telafisi_yalniz_lider_blogunda_baslar():
    """`is_leader` False → thread hiç kurulmaz: çağrının TAMAMI kapının içinde."""
    lifespan = _lifespan_node()
    total = ast.dump(lifespan).count("boot_catch_up_scan")
    gated = sum(
        ast.dump(node).count("boot_catch_up_scan")
        for node in ast.walk(lifespan)
        if isinstance(node, ast.If) and "is_leader" in ast.dump(node.test)
    )
    assert total > 0, "lifespan'de boot_catch_up_scan yok"
    assert total == gated, "boot_catch_up_scan is_leader kapısı DIŞINDA çağrılıyor"


def test_boot_telafisi_thread_hedefidir():
    """Tarama DB'ye gider; lifespan'i bloklamaması için Thread(target=...)."""
    lifespan = _lifespan_node()
    hedefler = [
        kw.value.id
        for node in ast.walk(lifespan)
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "Thread"
        for kw in node.keywords
        if kw.arg == "target" and isinstance(kw.value, ast.Name)
    ]
    assert "boot_catch_up_scan" in hedefler
    assert "catch_up_missed_reports" in hedefler  # mevcut desen korunur


def test_boot_telafisi_istisnayi_yutar_tek_warning(env, caplog, monkeypatch):
    def _patlayan(*a, **kw):
        raise RuntimeError("DB yok")

    monkeypatch.setattr(env.scanner, "scan_deadlines", _patlayan)

    with caplog.at_level(logging.DEBUG):
        sonuc = env.scanner.boot_catch_up_scan()  # istisna TAŞMAZ

    assert sonuc is None
    uyarilar = [r for r in caplog.records if r.levelname == "WARNING" and "Boot telafi" in r.getMessage()]
    assert len(uyarilar) == 1
    assert [r for r in caplog.records if r.levelname == "ERROR"] == []


def test_boot_telafisi_basarida_sayaclari_doner(env, monkeypatch):
    monkeypatch.setattr(env.scanner, "scan_deadlines", lambda: {"sure_bildirim": 2})
    assert env.scanner.boot_catch_up_scan() == {"sure_bildirim": 2}


def test_ayni_gun_cron_ve_telafi_satir_ikilemez(env, monkeypatch):
    """G085 `test_ayni_gece_iki_kez_kosmak_satir_ikilemez` ile aynı güvence;
    burada telafi yolu üzerinden (scan_deadlines'ı telafi sarmalayıcısı çağırır)."""
    env.avukat()
    env.karar(env.dava())
    gun = SON_GUN - timedelta(days=7)

    env.tara(gun)  # cron

    # Telafi: sarmalayıcı argümansız çağırır; test DB'si için scan_deadlines
    # aynı gün + test oturumuna bağlanır.
    gercek = env.scanner.scan_deadlines
    db = env.sessions()
    try:
        monkeypatch.setattr(env.scanner, "scan_deadlines", lambda: gercek(bugun=gun, db=db))
        sonuc = env.scanner.boot_catch_up_scan()
    finally:
        db.close()

    assert sonuc is not None and sonuc["sure_bildirim"] == 1  # dedupe mevcut id'yi döndü
    assert len(env.bildirimler()) == 1


def test_kacirilan_t7_gunu_t5te_en_dar_esikle_telafi_edilir(env):
    env.avukat()
    karar_id = env.karar(env.dava())

    # T-7 günü (08.10) tarama kaçtı; boot T-5'te (10.10) koşuyor.
    env.tara(SON_GUN - timedelta(days=5))

    rows = env.bildirimler()
    assert [r.dedupe_key for r in rows] == [f"deadline:{karar_id}:7:{MAIL_SERAP}"]
    assert "5 gün kaldı" in rows[0].title


def test_kacan_t1_telafi_edilmez(env):
    """Son gün geçti: kalan<0 → eşik yok → bildirim yok (bilinçli kabul)."""
    env.avukat()
    env.karar(env.dava())

    sayaclar = env.tara(SON_GUN + timedelta(days=1))

    assert env.bildirimler() == []
    assert sayaclar["sure_bildirim"] == 0 and sayaclar["atlanan"] == 1


# ─── (b) retention ───────────────────────────────────────────────────────────

BUGUN = date(2026, 8, 22)
_UTC = timezone.utc


def _gun_once(n: int) -> datetime:
    return datetime(BUGUN.year, BUGUN.month, BUGUN.day, 12, 0, tzinfo=_UTC) - timedelta(days=n)


def test_okunmus_ve_eski_satir_silinir(env, monkeypatch):
    monkeypatch.setattr(env.svc, "NOTIFICATION_RETENTION_DAYS", 90)
    env.bildirim(created_at=_gun_once(91), read=True, key="k1")

    assert env.purge(BUGUN) == 1
    assert env.bildirimler() == []


def test_okunmus_ama_yeni_satir_kalir(env, monkeypatch):
    monkeypatch.setattr(env.svc, "NOTIFICATION_RETENTION_DAYS", 90)
    env.bildirim(created_at=_gun_once(89), read=True, key="k1")

    assert env.purge(BUGUN) == 0
    assert len(env.bildirimler()) == 1


def test_okunmamis_ve_eski_satir_ASLA_silinmez(env, monkeypatch):
    monkeypatch.setattr(env.svc, "NOTIFICATION_RETENTION_DAYS", 90)
    env.bildirim(created_at=_gun_once(400), read=False, key="k1")

    assert env.purge(BUGUN) == 0
    assert len(env.bildirimler()) == 1


def test_purge_karisik_kumede_yalniz_okunmus_eskiyi_secer(env, monkeypatch):
    monkeypatch.setattr(env.svc, "NOTIFICATION_RETENTION_DAYS", 30)
    env.bildirim(created_at=_gun_once(31), read=True, key="sil")
    env.bildirim(created_at=_gun_once(29), read=True, key="yeni")
    env.bildirim(created_at=_gun_once(31), read=False, key="okunmamis")

    assert env.purge(BUGUN) == 1
    assert {r.dedupe_key for r in env.bildirimler()} == {"yeni", "okunmamis"}


def test_retention_suresi_env_ile_ayarlanir_bozuk_env_varsayilana_duser(env, caplog):
    parse = env.svc._parse_retention_days
    varsayilan = env.svc.DEFAULT_NOTIFICATION_RETENTION_DAYS

    assert varsayilan == 90
    assert parse(None) == 90
    assert parse("") == 90
    assert parse(" 30 ") == 30
    with caplog.at_level(logging.DEBUG):
        assert parse("hizli") == 90
        assert parse("0") == 90
        assert parse("-5") == 90
    uyarilar = [r for r in caplog.records if r.levelname == "WARNING" and "NOTIFICATION_RETENTION_DAYS" in r.getMessage()]
    assert len(uyarilar) == 3
    assert [r for r in caplog.records if r.levelname == "ERROR"] == []


def test_retention_tek_yerde_tanimli():
    """Tarayıcı süreyi kendi kopyasıyla değil, notifications'tan okur."""
    kaynak = (BACKEND_DIR / "services" / "deadline_scanner.py").read_text(encoding="utf-8")
    assert "RETENTION" not in kaynak.replace("NOTIFICATION_RETENTION_DAYS", "")
    assert "purge_old_notifications" in kaynak


def test_scan_donusunde_purged_var_ve_okunmamis_eski_loglanir(env, caplog, monkeypatch):
    monkeypatch.setattr(env.svc, "NOTIFICATION_RETENTION_DAYS", 90)
    env.bildirim(created_at=_gun_once(100), read=True, key="eski-okunmus")
    env.bildirim(created_at=_gun_once(100), read=False, key="eski-okunmamis-1")
    env.bildirim(created_at=_gun_once(100), read=False, key="eski-okunmamis-2")

    with caplog.at_level(logging.DEBUG):
        sayaclar = env.tara(BUGUN)

    assert sayaclar["purged"] == 1
    assert sayaclar["okunmamis_eski"] == 2
    assert {r.dedupe_key for r in env.bildirimler()} == {"eski-okunmamis-1", "eski-okunmamis-2"}
    mesajlar = [r.getMessage() for r in caplog.records if r.levelname == "INFO"]
    assert any("Okunmamış ve retention" in m and "2" in m for m in mesajlar)
    assert [r for r in caplog.records if r.levelname == "ERROR"] == []


def test_purge_hatasi_turu_dusurmez_warning(env, caplog, monkeypatch):
    env.avukat()
    env.karar(env.dava())

    def _patlayan(*a, **kw):
        raise RuntimeError("DELETE düştü")

    monkeypatch.setattr(env.scanner, "purge_old_notifications", _patlayan)

    with caplog.at_level(logging.DEBUG):
        sayaclar = env.tara(SON_GUN - timedelta(days=7))

    assert sayaclar["sure_bildirim"] == 1 and sayaclar["purged"] == 0
    assert len(env.bildirimler()) == 1
    assert [r for r in caplog.records if r.levelname == "WARNING" and "retention" in r.getMessage()]
    assert [r for r in caplog.records if r.levelname == "ERROR"] == []


# ─── (c) tz sınırı + duruşma üst sınırı ──────────────────────────────────────

def test_bugun_tr_utc_gece_yarisi_sinirinda_ertesi_gundur(env, monkeypatch):
    """UTC 22:30 = TR 01:30 ertesi gün (yaz saati yok, sabit UTC+3)."""
    sabit = datetime(2026, 8, 22, 22, 30, tzinfo=timezone.utc)

    class _Sabit(datetime):
        @classmethod
        def now(cls, tz=None):
            return sabit.astimezone(tz) if tz else sabit.replace(tzinfo=None)

    monkeypatch.setattr(env.scanner, "datetime", _Sabit)

    assert env.scanner.bugun_tr() == date(2026, 8, 23)
    assert sabit.date() == date(2026, 8, 22)  # UTC günü hâlâ 22'si


def test_uzak_durusma_sorguda_elenir_python_a_ulasmaz(env, monkeypatch):
    env.avukat()
    case_id = env.dava()
    gun = date(2026, 11, 10)
    yakin = env.durusma(case_id, gun + timedelta(days=3))
    env.durusma(case_id, gun + timedelta(days=30))

    gorulen: list[int] = []
    gercek = env.scanner.esik_sec

    def _kaydet(kalan, esikler):
        if esikler is env.scanner.DURUSMA_ESIKLERI:
            gorulen.append(kalan)
        return gercek(kalan, esikler)

    monkeypatch.setattr(env.scanner, "esik_sec", _kaydet)

    sayaclar = env.tara(gun)

    assert gorulen == [3]                 # 30 günlük duruşma Python'a hiç ulaşmadı (SQL'de elendi)
    assert sayaclar["atlanan"] == 1       # sayaç anlamı korunur: COUNT ile sayıldı, satır çekilmedi
    assert [r.dedupe_key for r in env.bildirimler()] == [f"hearing:{yakin}:3:{MAIL_SERAP}"]


def test_durusma_ust_siniri_en_genis_esik_kadardir(env):
    """Sınır tam eşik gününü KAPSAR (T-3 duruşması üretilir)."""
    env.avukat()
    case_id = env.dava()
    gun = date(2026, 11, 10)
    env.durusma(case_id, gun + timedelta(days=max(env.scanner.DURUSMA_ESIKLERI)))

    assert env.tara(gun)["durusma_bildirim"] == 1
