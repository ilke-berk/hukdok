"""G085 — gece tarayıcısı: yaklaşan süre ve duruşma bildirimleri.

Kilitlenen davranışlar:
  1. kaynak `case_stage_decisions.teblig_tarihi` + `hearing_dates.hearing_date`
     (ölçüm: `cases.karar_teblig_tarihi` 0 dolu, oradan tarama boş dönerdi),
  2. eşikler: süreler T-15/7/3/1, duruşmalar T-3/1 — kalan güne uyan EN DAR
     eşik seçilir, eşik daraldıkça YENİ bildirim doğar,
  3. idempotency: aynı kayıt için ertesi gece İKİNCİ bildirim yazılmaz
     (`deadline:{id}:{esik}:…` / `hearing:{id}:{esik}:…`),
  4. geçmiş tarihli süre/duruşma için bildirim ÜRETİLMEZ,
  5. gövde dayanağını taşır (aşama, tebliğ tarihi, kural + kanun maddesi) ve
     "bilgilendirmedir" şerhini; G084 takvimi doğrulamadıysa bu da yazılır,
  6. alıcı G080'den çözülür; çözülemezse bildirim yok + WARNING + sayaç,
  7. log sözleşmesi: satır düzeyi hata WARNING ve tur DEVAM eder, tur başına
     en fazla TEK ERROR,
  8. zamanlayıcı kaydı `api.py`de `is_leader` bloğunun İÇİNDE, 06:00 TR
     (AST ile denetlenir — iki worker'da çift bildirim üretmesin).

Testler süreç içi sqlite (StaticPool) üzerinde GERÇEK sorgu koşar; dedupe UNIQUE
kısıtı `database._MIGRATIONS`'taki gerçek DDL'den kurulur (G081/G082 deseni).
"""
import ast
import logging
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

DOMAIN = "hanyaloglu-acar.av.tr"
MAIL_SERAP = f"serap.turgal@{DOMAIN}"
MAIL_TUGCE = f"tugce.ungor@{DOMAIN}"

# Kaydırmasız zincir: 01.10.2026 (Per) tebliğ → +14 gün → 15.10.2026 (Per),
# hafta sonuna/resmî tatile/adli tatile rastlamaz → son gün aynen.
TEBLIG = date(2026, 10, 1)
SON_GUN = date(2026, 10, 15)


def _notifications_index_ddls() -> list[str]:
    """Migrasyondaki `notifications` index op'unun DDL'leri (tek kaynak)."""
    import database

    return [
        ddl
        for op in database._MIGRATIONS
        if op[0] == "index" and op[1] == "notifications"
        for ddl in op[2]
    ]


@pytest.fixture()
def env(monkeypatch):
    """sqlite motoru + oturum fabrikası + veri kurucular."""
    from database import Base
    import models  # noqa: F401 — Base.metadata dolsun
    from services import deadline_scanner as scanner

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

    def _avukat(code: str, name: str, email: str, gorev: str = "AVUKAT"):
        db = maker()
        try:
            db.add(models.Lawyer(code=code, name=name, email=email, gorev=gorev, active=True))
            db.commit()
        finally:
            db.close()

    def _dava(sorumlu: str = "Av. Serap Turgal", **kw) -> int:
        db = maker()
        try:
            row = models.Case(
                tracking_no=kw.pop("tracking_no", "2024/1234"),
                esas_no=kw.pop("esas_no", "2024/55"),
                court=kw.pop("court", "Ankara 1. Asliye Hukuk Mahkemesi"),
                responsible_lawyer_name=sorumlu,
                **kw,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return int(row.id)
        finally:
            db.close()

    def _karar(case_id: int, **kw) -> int:
        db = maker()
        try:
            row = models.CaseStageDecision(
                case_id=case_id,
                stage=kw.pop("stage", "YEREL"),
                sira_no=kw.pop("sira_no", 1),
                teblig_tarihi=kw.pop("teblig_tarihi", TEBLIG),
                dogrulama_durumu=kw.pop("dogrulama_durumu", "BELGE"),
                **kw,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return int(row.id)
        finally:
            db.close()

    def _durusma(case_id: int, hearing_date: date, **kw) -> int:
        db = maker()
        try:
            row = models.HearingDate(
                case_id=case_id,
                hearing_date=hearing_date,
                hearing_time=kw.pop("hearing_time", "09:43"),
                **kw,
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

    yield SimpleNamespace(
        models=models,
        scanner=scanner,
        sessions=maker,
        avukat=_avukat,
        dava=_dava,
        karar=_karar,
        durusma=_durusma,
        bildirimler=_bildirimler,
        tara=_tara,
    )
    engine.dispose()


def _serap(env) -> None:
    env.avukat("STG", "Serap Turgal", MAIL_SERAP)


# ─── eşik seçimi (saf) ───────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "kalan, beklenen",
    [(0, 1), (1, 1), (2, 3), (3, 3), (4, 7), (7, 7), (8, 15), (15, 15), (16, None), (-1, None)],
)
def test_esik_secimi_en_dar_esiktir(env, kalan, beklenen):
    assert env.scanner.esik_sec(kalan, env.scanner.SURE_ESIKLERI) == beklenen


@pytest.mark.parametrize(
    "kalan, beklenen",
    [(0, 1), (1, 1), (2, 3), (3, 3), (4, None), (-1, None)],
)
def test_durusma_esikleri_yalniz_uc_ve_bir(env, kalan, beklenen):
    assert env.scanner.esik_sec(kalan, env.scanner.DURUSMA_ESIKLERI) == beklenen


# ─── süre bildirimi: mutlu yol ───────────────────────────────────────────────

def test_sure_bildirimi_sorumlu_avukata_yazilir(env):
    _serap(env)
    case_id = env.dava()
    karar_id = env.karar(case_id)

    sayaclar = env.tara(SON_GUN - timedelta(days=7))

    rows = env.bildirimler()
    assert sayaclar["sure_bildirim"] == 1 and len(rows) == 1
    row = rows[0]
    assert row.recipient_email == MAIL_SERAP
    assert row.type == env.scanner.SURE_TYPE == "sure_yaklasti"
    assert row.case_id == case_id
    assert row.due_date == SON_GUN
    assert row.severity == "info"
    assert row.dedupe_key == f"deadline:{karar_id}:7:{MAIL_SERAP}"
    assert row.dedupe_key.startswith(f"deadline:{karar_id}:7")
    assert "7 gün kaldı" in row.title


def test_sure_govdesi_dayanagini_ve_serhi_tasir(env):
    _serap(env)
    karar_id = env.karar(env.dava())

    env.tara(SON_GUN - timedelta(days=3))

    body = env.bildirimler()[0].body
    assert "2024/1234" in body                      # dava künyesi
    assert "YEREL" in body                          # aşama
    assert "01.10.2026" in body                     # tebliğ tarihi
    assert "İstinaf başvuru süresi" in body         # kural adı
    assert "HMK m. 345/1" in body                   # dayanak
    assert "15.10.2026" in body                     # son gün
    assert env.scanner.SERH in body
    assert "süre takibi yerine geçmez" in body
    assert str(karar_id)  # kayıt gerçekten yazıldı


def test_yakin_sure_uyari_seviyesine_yukselir(env):
    _serap(env)
    env.karar(env.dava())

    env.tara(SON_GUN - timedelta(days=1))

    row = env.bildirimler()[0]
    assert row.severity == "warning"
    assert row.dedupe_key.endswith(f":1:{MAIL_SERAP}")


def test_son_gun_bugunse_hala_bildirim_var(env):
    _serap(env)
    env.karar(env.dava())

    env.tara(SON_GUN)

    row = env.bildirimler()[0]
    assert "son gün bugün" in row.title
    assert row.due_date == SON_GUN


# ─── geçmiş / uzak tarih ─────────────────────────────────────────────────────

def test_gecmis_sure_icin_bildirim_uretilmez(env):
    _serap(env)
    env.karar(env.dava())

    sayaclar = env.tara(SON_GUN + timedelta(days=1))

    assert env.bildirimler() == []
    assert sayaclar["sure_bildirim"] == 0
    assert sayaclar["atlanan"] == 1


def test_en_genis_esikten_uzak_sure_icin_bildirim_uretilmez(env):
    _serap(env)
    env.karar(env.dava())

    sayaclar = env.tara(SON_GUN - timedelta(days=16))

    assert env.bildirimler() == []
    assert sayaclar["atlanan"] == 1


# ─── idempotency ─────────────────────────────────────────────────────────────

def test_ayni_gece_iki_kez_kosmak_satir_ikilemez(env):
    _serap(env)
    env.karar(env.dava())
    gun = SON_GUN - timedelta(days=7)

    env.tara(gun)
    ilk = len(env.bildirimler())
    env.tara(gun)

    assert ilk == 1
    assert len(env.bildirimler()) == 1


def test_ertesi_gece_ayni_satir_ikinci_bildirim_uretmez(env):
    _serap(env)
    env.karar(env.dava())

    env.tara(SON_GUN - timedelta(days=7))
    env.tara(SON_GUN - timedelta(days=6))
    env.tara(SON_GUN - timedelta(days=5))
    env.tara(SON_GUN - timedelta(days=4))

    # Dördü de T-7 bandında: tek satır.
    assert len(env.bildirimler()) == 1


def test_esik_daralinca_yeni_bildirim_dogar(env):
    _serap(env)
    karar_id = env.karar(env.dava())

    env.tara(SON_GUN - timedelta(days=7))
    env.tara(SON_GUN - timedelta(days=3))
    env.tara(SON_GUN - timedelta(days=1))

    anahtarlar = [row.dedupe_key for row in env.bildirimler()]
    assert anahtarlar == [
        f"deadline:{karar_id}:7:{MAIL_SERAP}",
        f"deadline:{karar_id}:3:{MAIL_SERAP}",
        f"deadline:{karar_id}:1:{MAIL_SERAP}",
    ]


def test_iki_sorumlu_iki_ayri_bildirim_alir(env):
    _serap(env)
    env.avukat("TUY", "Tuğçe Üngör Yanık", MAIL_TUGCE)
    karar_id = env.karar(env.dava(sorumlu="Serap Turgal;Tuğçe Üngör Yanık"))

    env.tara(SON_GUN - timedelta(days=7))

    rows = env.bildirimler()
    assert {r.recipient_email for r in rows} == {MAIL_SERAP, MAIL_TUGCE}
    assert {r.dedupe_key for r in rows} == {
        f"deadline:{karar_id}:7:{MAIL_SERAP}",
        f"deadline:{karar_id}:7:{MAIL_TUGCE}",
    }


# ─── kural / hedef / kapsam ──────────────────────────────────────────────────

@pytest.mark.parametrize("stage", ["TEMYIZ", "KARAR_DUZELTME"])
def test_kanuni_suresi_olmayan_asama_bildirim_uretmez(env, stage):
    _serap(env)
    env.karar(env.dava(), stage=stage)

    sayaclar = env.tara(SON_GUN - timedelta(days=7))

    assert env.bildirimler() == []
    assert sayaclar["kuralsiz"] == 1


def test_istinaf_asamasi_temyiz_suresini_uretir(env):
    _serap(env)
    env.karar(env.dava(), stage="ISTINAF")

    env.tara(SON_GUN - timedelta(days=7))

    body = env.bildirimler()[0].body
    assert "Temyiz başvuru süresi" in body
    assert "HMK m. 361/1" in body


def test_hedefsiz_dava_bildirim_uretmez_warning_loglanir(env, caplog):
    _serap(env)
    env.karar(env.dava(sorumlu="ARSIV DOSYA YONETICISI"))

    with caplog.at_level(logging.DEBUG):
        sayaclar = env.tara(SON_GUN - timedelta(days=7))

    assert env.bildirimler() == []
    assert sayaclar["hedefsiz"] == 1
    uyarilar = [r for r in caplog.records if r.levelname == "WARNING" and "hedefsiz" in r.getMessage()]
    assert len(uyarilar) == 1
    assert [r for r in caplog.records if r.levelname == "ERROR"] == []


def test_silinen_dava_taranmaz(env):
    from datetime import datetime, timezone

    _serap(env)
    case_id = env.dava()
    env.karar(case_id)
    db = env.sessions()
    try:
        case = db.query(env.models.Case).filter(env.models.Case.id == case_id).first()
        case.deleted_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

    sayaclar = env.tara(SON_GUN - timedelta(days=7))

    assert env.bildirimler() == []
    assert sayaclar["sure_bildirim"] == 0


def test_teblig_tarihsiz_karar_bildirim_uretmez(env):
    _serap(env)
    env.karar(env.dava(), teblig_tarihi=None)

    sayaclar = env.tara(SON_GUN - timedelta(days=7))

    assert env.bildirimler() == []
    assert sayaclar == {k: 0 for k in sayaclar}


# ─── G084 "takvim doğrulanmadı" izi ──────────────────────────────────────────

def test_takvim_dogrulanmadi_govdede_gorunur(env):
    _serap(env)
    # 2030 `legal_deadlines.TAKVIMLI_YILLAR` dışında: kaydırma uygulanmaz ve
    # sonuç "takvim doğrulanmadı" damgalı döner — uyarı bunu SÖYLEMEK zorunda.
    env.karar(env.dava(), teblig_tarihi=date(2030, 10, 1))

    env.tara(date(2030, 10, 8))

    body = env.bildirimler()[0].body
    assert "takvimi doğrulanmadı" in body
    assert env.scanner.TAKVIM_UYARISI in body


def test_takvimli_yilda_uyari_yazilmaz(env):
    _serap(env)
    env.karar(env.dava())

    env.tara(SON_GUN - timedelta(days=7))

    assert "takvimi doğrulanmadı" not in env.bildirimler()[0].body


# ─── duruşma bildirimleri ────────────────────────────────────────────────────

def test_durusma_bildirimi_uc_gun_kala_yazilir(env):
    _serap(env)
    case_id = env.dava()
    gun = date(2026, 11, 10)
    hearing_id = env.durusma(case_id, gun + timedelta(days=3))

    sayaclar = env.tara(gun)

    rows = env.bildirimler()
    assert sayaclar["durusma_bildirim"] == 1 and len(rows) == 1
    row = rows[0]
    assert row.type == env.scanner.DURUSMA_TYPE == "durusma_yaklasti"
    assert row.dedupe_key == f"hearing:{hearing_id}:3:{MAIL_SERAP}"
    assert row.due_date == gun + timedelta(days=3)
    assert row.severity == "warning"
    assert "13.11.2026" in row.body and "09:43" in row.body
    assert env.scanner.SERH in row.body


def test_durusmada_yedi_gun_esigi_yoktur(env):
    _serap(env)
    case_id = env.dava()
    gun = date(2026, 11, 10)
    env.durusma(case_id, gun + timedelta(days=7))

    sayaclar = env.tara(gun)

    assert env.bildirimler() == []
    assert sayaclar["atlanan"] == 1


def test_gecmis_durusma_icin_bildirim_uretilmez(env):
    _serap(env)
    case_id = env.dava()
    gun = date(2026, 11, 10)
    env.durusma(case_id, gun - timedelta(days=1))

    env.tara(gun)

    assert env.bildirimler() == []


def test_durusma_ertesi_gece_ikinci_bildirim_uretmez(env):
    _serap(env)
    case_id = env.dava()
    gun = date(2026, 11, 10)
    env.durusma(case_id, gun + timedelta(days=3))

    env.tara(gun)
    env.tara(gun + timedelta(days=1))  # kalan 2 → hâlâ T-3 bandı

    assert len(env.bildirimler()) == 1


def test_durusma_alicisi_cozulemezse_zapttaki_avukata_dusulur(env):
    _serap(env)
    case_id = env.dava(sorumlu="ARSIV DOSYA YONETICISI")
    gun = date(2026, 11, 10)
    env.durusma(case_id, gun + timedelta(days=1), lawyer_name="Av. Serap Turgal")

    env.tara(gun)

    rows = env.bildirimler()
    assert len(rows) == 1 and rows[0].recipient_email == MAIL_SERAP


# ─── log sözleşmesi ──────────────────────────────────────────────────────────

def test_satir_hatasi_turu_durdurmaz_ve_tek_error_loglanir(env, caplog, monkeypatch):
    _serap(env)
    case_id = env.dava()
    ilk = env.karar(case_id)
    env.karar(case_id, sira_no=2)

    gercek = env.scanner.create_notification

    def _patlayan(db, **kw):
        if kw.get("dedupe_key", "").startswith(f"deadline:{ilk}:"):
            raise RuntimeError("bilerek patlatıldı")
        return gercek(db, **kw)

    monkeypatch.setattr(env.scanner, "create_notification", _patlayan)

    with caplog.at_level(logging.DEBUG):
        sayaclar = env.tara(SON_GUN - timedelta(days=7))

    # Tur DEVAM etti: ikinci karar için bildirim yazıldı.
    assert sayaclar["sure_bildirim"] == 1 and sayaclar["hata"] == 1
    assert len(env.bildirimler()) == 1
    hatalar = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(hatalar) == 1
    assert "1 kayıt işlenemedi" in hatalar[0].getMessage()
    assert [r for r in caplog.records if r.levelname == "WARNING" and "Bildirim yazılamadı" in r.getMessage()]


def test_tarama_sorgusu_duserse_tek_error_ve_istisna_tasmaz(env, caplog, monkeypatch):
    _serap(env)
    env.karar(env.dava())

    def _patlayan(*a, **kw):
        raise RuntimeError("DB düştü")

    monkeypatch.setattr(env.scanner, "_sure_adaylari", _patlayan)

    with caplog.at_level(logging.DEBUG):
        sayaclar = env.tara(SON_GUN - timedelta(days=7))

    assert sayaclar["sure_bildirim"] == 0
    hatalar = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(hatalar) == 1
    assert "yarıda kaldı" in hatalar[0].getMessage()


def test_mutlu_yolda_hic_error_loglanmaz(env, caplog):
    _serap(env)
    env.karar(env.dava())

    with caplog.at_level(logging.DEBUG):
        env.tara(SON_GUN - timedelta(days=7))

    assert [r for r in caplog.records if r.levelname == "ERROR"] == []


# ─── zamanlayıcı kaydı (AST) ─────────────────────────────────────────────────

def _api_agaci() -> ast.Module:
    return ast.parse(Path(__file__).resolve().parent.parent.joinpath("api.py").read_text(encoding="utf-8"))


def _lider_blogundaki_joblar() -> dict[str, ast.Call]:
    """`if is_leader:` bloklarının İÇİNDEKİ add_job çağrıları (id → çağrı)."""
    joblar: dict[str, ast.Call] = {}
    for node in ast.walk(_api_agaci()):
        if not isinstance(node, ast.If):
            continue
        if not (isinstance(node.test, ast.Name) and node.test.id == "is_leader"):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "add_job"
            ):
                for kw in inner.keywords:
                    if kw.arg == "id" and isinstance(kw.value, ast.Constant):
                        joblar[str(kw.value.value)] = inner
    return joblar


def _kw(call: ast.Call, ad: str):
    for kw in call.keywords:
        if kw.arg == ad:
            return kw.value
    return None


def test_tarayici_job_u_lider_blogunun_icinde_kayitli():
    assert "deadline_scan" in _lider_blogundaki_joblar()


def test_tarayici_job_u_06_00_tr_ve_idempotent_kayitli():
    job = _lider_blogundaki_joblar()["deadline_scan"]

    assert isinstance(_kw(job, "replace_existing"), ast.Constant)
    assert _kw(job, "replace_existing").value is True
    assert isinstance(_kw(job, "misfire_grace_time"), ast.Constant)
    assert _kw(job, "misfire_grace_time").value == 3600

    trigger = job.args[1]
    assert isinstance(trigger, ast.Call) and trigger.func.id == "CronTrigger"
    assert _kw(trigger, "hour").value == 6
    assert _kw(trigger, "minute").value == 0
    tz = _kw(trigger, "timezone")
    assert isinstance(tz, ast.Call) and tz.args[0].value == "Europe/Istanbul"

    assert isinstance(job.args[0], ast.Name) and job.args[0].id == "scan_deadlines"


def test_mevcut_gece_joblari_degismedi():
    joblar = _lider_blogundaki_joblar()
    for job_id, saat, dakika in (("daily_activity_report", 0, 0), ("conversion_retry", 2, 30)):
        trigger = joblar[job_id].args[1]
        assert _kw(trigger, "hour").value == saat
        assert _kw(trigger, "minute").value == dakika


def test_tarayici_aga_cikmaz():
    """Kanal yalnız uygulama içi: tarayıcı mail/HTTP kütüphanesi import ETMEZ."""
    kaynak = Path(__file__).resolve().parent.parent.joinpath(
        "services", "deadline_scanner.py"
    ).read_text(encoding="utf-8")
    agac = ast.parse(kaynak)
    ithal: set[str] = set()
    for node in ast.walk(agac):
        if isinstance(node, ast.Import):
            ithal.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            ithal.add(node.module.split(".")[0])
    assert not ithal & {"smtplib", "requests", "httpx", "email_sender", "urllib"}
