"""Kart alanı için hata bildirimi (02.10.2026) — `/api/hata-bildirimleri*`.

Avukat dava ya da müvekkil kartında yanlış gördüğü bilgiyi alanın yanındaki zilden
bildirir; idari personel uygulama içi bildirimle (zil) görür, kaydı düzeltir ve
bildirimi kapatır. E-posta/mesajlaşma yerine geçer; kanal YALNIZ uygulama içidir.

Sözleşme (frontend `lib/hataBildirimleri.ts` ile ORTAK):

* `GET  /api/hata-bildirimleri/alicilar`     → 200 alıcı adayları (`schemas.HataAliciAdayi`):
  idari personel + iç avukatlar + yönetici, istek sahibi hariç; `varsayilan` ön-seçili
* `POST /api/hata-bildirimleri`              → 201 + tek bildirim (`schemas.HataBildirimiCreate`);
  `alicilar` (e-posta listesi) aday listesine karşı doğrulanır, yoksa varsayılan alıcılar
  `dogrudan_duzelt=true`: bildiren doğru değeri karta KENDİSİ yazar (yalnız dava hedefi,
  `DOGRUDAN_DUZELTME_ALANLARI`, sorumlu avukat ya da yönetici; aksi 403/422, ekran bayatsa
  409) — kimseye bildirim gitmez, kayıt COZULDU olarak denetim izi kalır
* `GET  /api/hata-bildirimleri/dogrudan?case_id=` → 200 `{"alanlar": [...]}`: istek sahibinin
  bu davada doğrudan düzeltebileceği alanlar (yetkisizse boş)
* `GET  /api/hata-bildirimleri`              → 200 liste, en yeni üstte.
  `case_id` / `client_id` verilirse o kaydın bildirimleri; verilmezse görünür TÜM
  bildirimler (idari pano). `durum=acik` (varsayılan) | `hepsi`.
* `POST /api/hata-bildirimleri/{id}/kapat`   → 200 + tek bildirim; `sonuc` COZULDU |
  REDDEDILDI. Zaten kapalı → 409. Tek yönlü: kapanan bildirim yeniden açılmaz.

Yetki: sistemde rol yok (routes/notifications.py şerhi) — giriş yapmış her kullanıcı
bildirebilir, listeleyebilir ve kapatabilir; kapatan kişi satıra yazılır. Görünürlük
hedef kayıttan gelir (`get_tenant_owned_case` / `get_tenant_owned_client`: paylaşımlı
havuz + soft-delete) → görünmeyen hedefte uçlar 404.

Bildirimler (`services/notifications.create_notification`, dedupe'lu):
* açılışta `hata_bildirimi` → bildirenin seçtiği kişiler (`error_report_candidates`
  içinden; seçim yoksa `error_report_recipients` varsayılanları) − bildiren; seçilenler
  satıra da yazılır (`alicilar`);
* kapanışta `hata_sonucu` → bildiren (kendi bildirimini kapattıysa üretilmez); aynı
  anda diğer alıcıların okunmamış `hata_bildirimi` satırları okundu işaretlenir —
  biri çözünce ötekilerin zilinde bayat iş kalmasın.

Log sözleşmesi: bildirim yazımı bildirimin kendisini DÜŞÜRMEZ — satır commit
edildikten sonra bildirim hatası WARNING'dir (kayıt kartta ve panoda görünür).
"""
import datetime as dt
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from auth_helpers import get_tenant_owned_case, get_tenant_owned_client, tenant_filter_clause
from database import get_db
from dependencies import get_current_tenant, get_current_user
from schemas import (
    HATA_DURUM_ACIK,
    HataAliciAdayi,
    HataAlicisi,
    HataBildirimiCreate,
    HataBildirimiKapat,
    HataBildirimiRead,
)
from managers.case_manager import enrich_case
from routes.config import _admin_emails
from services.notification_targeting import error_report_candidates, resolve_case_recipients
from services.notifications import create_notification, normalize_email
import models

logger = logging.getLogger(__name__)

router = APIRouter()

HATA_BILDIRIMI_TYPE = "hata_bildirimi"
HATA_SONUCU_TYPE = "hata_sonucu"

# Doğrudan düzeltmeye açık alanlar (kullanıcı kararı, 02.10.2026): yalnız serbest
# metinli kimlik/numara alanları — "Doğrusu" kutusuna yazılan metin karta AYNEN
# yazılabildiği için. Liste/tarih/tutar/avukat/durum alanları bilinçli DIŞARIDA:
# serbest metinle yazılırlarsa kapalı listeyi, tarih/tutar biçimini ya da avukat
# yazım korumasını delerlerdi — onlar bildirimle gider, düzeltme dava formundan yapılır.
# Hepsi `case_manager.ENRICH_FIELDS` içindedir (yazım yolu `enrich_case`; test bekçili).
DOGRUDAN_DUZELTME_ALANLARI: tuple[str, ...] = (
    "esas_no", "hasar_dosya_no", "hukuk_no", "klasor_no_2", "judicial_unit",
)
# `case_history.source` imzası: kullanıcı düzeltmesidir (`HUKDOK_TESLIM` DEĞİL) →
# kesim-sonrası kullanıcı korumasında panel düzeltmesi gibi sayılır.
DOGRUDAN_KAYNAK = "HATA_DUZELTME"
DOGRUDAN_NOTU = "Bildiren tarafından doğrudan düzeltildi."

DEFAULT_LIMIT = 100
MAX_LIMIT = 500

SONUC_BASLIGI = {
    "COZULDU": "Hata bildiriminiz düzeltildi",
    "REDDEDILDI": "Hata bildiriminiz kapatıldı (değişiklik yapılmadı)",
}


def _user_email(user: dict) -> str:
    return normalize_email(
        user.get("preferred_username")
        or user.get("upn")
        or user.get("email")
        or ""
    )


def _require_user_email(user: dict) -> str:
    email = _user_email(user)
    if not email:
        # Bildireni/kapatanı belli olmayan kayıt bu tablonun amacına aykırı.
        raise HTTPException(status_code=403, detail="Kullanıcı e-postası alınamadı.")
    return email


def _utc_iso(value: Optional[dt.datetime]) -> Optional[str]:
    """Ofsetli UTC ISO8601. Ofsetsiz değer (sqlite) UTC kabul edilir."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc).isoformat()


def _case_label(case: Any) -> str:
    parcalar = [
        (deger or "").strip()
        for deger in (getattr(case, "tracking_no", None), getattr(case, "esas_no", None))
    ]
    return " · ".join(p for p in parcalar if p)


def _link(row: Any) -> str:
    if row.case_id is not None:
        return f"/cases/{row.case_id}?hata={row.id}"
    return f"/clients?client={row.client_id}&hata={row.id}"


# `row` bilinçli `Any`: klasik `Column(...)` modelinde mypy örnek özniteliklerini
# `Column[str]` görür (routes/case_notes.py ile aynı desen).
def _serialize(row: Any, hedef_etiketi: Optional[str]) -> HataBildirimiRead:
    return HataBildirimiRead(
        id=row.id,
        case_id=row.case_id,
        client_id=row.client_id,
        hedef_etiketi=hedef_etiketi or None,
        link=_link(row),
        alan=row.alan,
        alan_etiketi=row.alan_etiketi,
        mevcut_deger=row.mevcut_deger,
        dogru_deger=row.dogru_deger,
        aciklama=row.aciklama,
        durum=row.durum,
        alicilar=[
            HataAlicisi(email=a["email"], ad=a.get("ad") or a["email"])
            for a in (row.alicilar or [])
            if isinstance(a, dict) and a.get("email")
        ],
        bildiren_ad=row.bildiren_ad,
        bildiren_email=row.bildiren_email,
        created_at=_utc_iso(row.created_at) or "",
        kapatan_ad=row.kapatan_ad,
        kapatan_email=row.kapatan_email,
        kapatma_notu=row.kapatma_notu,
        kapatildi_at=_utc_iso(row.kapatildi_at),
    )


def _hedef_etiketleri(db: Session, rows: list[Any]) -> dict[int, str]:
    """Bildirim id → hedefin okunur adı; dava ve müvekkiller İKİ sorguda toplanır."""
    case_ids = {r.case_id for r in rows if r.case_id is not None}
    client_ids = {r.client_id for r in rows if r.client_id is not None}
    davalar: dict[int, str] = {}
    muvekkiller: dict[int, str] = {}
    if case_ids:
        for case in db.query(models.Case).filter(models.Case.id.in_(case_ids)).all():
            davalar[int(case.id)] = _case_label(case)
    if client_ids:
        for client in db.query(models.Client).filter(models.Client.id.in_(client_ids)).all():
            muvekkiller[int(client.id)] = (client.name or "").strip()
    out: dict[int, str] = {}
    for r in rows:
        if r.case_id is not None:
            out[r.id] = davalar.get(r.case_id, "")
        else:
            out[r.id] = muvekkiller.get(r.client_id, "")
    return out


def _hedef_or_404(db: Session, tenant_id: str, case_id: Optional[int], client_id: Optional[int]) -> Any:
    if case_id is not None:
        case = get_tenant_owned_case(db, case_id, tenant_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Dava bulunamadı")
        return case
    client = get_tenant_owned_client(db, client_id, tenant_id) if client_id is not None else None
    if client is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı")
    return client


def _gorunur_bildirim_or_404(db: Session, tenant_id: str, bildirim_id: int) -> Any:
    row: Any = db.query(models.HataBildirimi).filter(models.HataBildirimi.id == bildirim_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Hata bildirimi bulunamadı")
    # Hedef görünmüyorsa (soft-silinmiş, tenant dışı) bildirim de görünmez.
    try:
        _hedef_or_404(db, tenant_id, row.case_id, row.client_id)
    except HTTPException:
        raise HTTPException(status_code=404, detail="Hata bildirimi bulunamadı") from None
    return row


def _bildirim_govdesi(row: Any, hedef_etiketi: str) -> str:
    satirlar = []
    if hedef_etiketi:
        satirlar.append(("Dava: " if row.case_id is not None else "Müvekkil: ") + hedef_etiketi)
    satirlar.append(f"Bildiren: {row.bildiren_ad or row.bildiren_email}")
    if row.mevcut_deger or row.dogru_deger:
        satirlar.append(f"Kayıtlı: {row.mevcut_deger or '—'} → Doğrusu: {row.dogru_deger or '—'}")
    if row.aciklama:
        satirlar.append(row.aciklama)
    return "\n".join(satirlar)


def _alicilari_sec(db: Session, secim: Optional[list[str]], bildiren: str) -> list[dict[str, str]]:
    """Bildirimin gideceği kişiler: `[{"email", "ad"}]` (satıra da bu yazılır).

    `secim` doluysa her adres aday listesinde (`error_report_candidates`) olmalı —
    serbest adrese bildirim yazılmaz (422). Boşsa varsayılan alıcılar. Bildiren her
    iki yolda da düşer: kişi kendi bildirimini almaz.
    """
    adaylar = error_report_candidates(db)
    if not secim:
        return [
            {"email": a["email"], "ad": a["ad"]}
            for a in adaylar if a["varsayilan"] and a["email"] != bildiren
        ]
    harita = {a["email"]: a for a in adaylar}
    secilen = [e for e in secim if e != bildiren]
    if any(e not in harita for e in secilen):
        raise HTTPException(status_code=422, detail="Seçilen alıcı listede yok.")
    if not secilen:
        raise HTTPException(status_code=422, detail="En az bir alıcı seçilmelidir.")
    return [{"email": e, "ad": harita[e]["ad"]} for e in secilen]


def _alicilara_bildir(db: Session, row: Any, hedef_etiketi: str) -> int:
    """Açılış bildirimi: satıra yazılmış alıcılara. Yazılan satır sayısı döner."""
    alicilar = [a["email"] for a in (row.alicilar or [])]
    if not alicilar:
        logger.warning(
            "Hata bildirimi hedefsiz: alıcı seçilmedi ve varsayılan alıcı tanımlı değil "
            "(bildirim=%s) — Yönetim > E-posta Alıcıları > 'Hata bildirimi'", row.id,
        )
        return 0
    govde = _bildirim_govdesi(row, hedef_etiketi)
    for email in alicilar:
        create_notification(
            db,
            recipient_email=email,
            type=HATA_BILDIRIMI_TYPE,
            title=f"Hata bildirimi: {row.alan_etiketi}",
            body=govde,
            severity="warning",
            tenant_id=row.tenant_id,
            case_id=row.case_id,
            dedupe_key=f"hata:{row.id}:{email}",
            link=_link(row),
        )
    return len(alicilar)


def _kapanisi_bildir(db: Session, row: Any, hedef_etiketi: str) -> None:
    """Kapanış: açılış bildirimleri okundu işaretlenir, bildirene sonuç yazılır."""
    (
        db.query(models.Notification)
        .filter(
            models.Notification.type == HATA_BILDIRIMI_TYPE,
            models.Notification.dedupe_key.like(f"hata:{row.id}:%"),
            models.Notification.read_at.is_(None),
        )
        .update({"read_at": dt.datetime.now(dt.timezone.utc)}, synchronize_session=False)
    )
    db.commit()

    if row.bildiren_email == row.kapatan_email:
        return
    satirlar = []
    if hedef_etiketi:
        satirlar.append(("Dava: " if row.case_id is not None else "Müvekkil: ") + hedef_etiketi)
    satirlar.append(f"Alan: {row.alan_etiketi}")
    satirlar.append(f"Kapatan: {row.kapatan_ad or row.kapatan_email}")
    if row.kapatma_notu:
        satirlar.append(row.kapatma_notu)
    create_notification(
        db,
        recipient_email=row.bildiren_email,
        type=HATA_SONUCU_TYPE,
        title=SONUC_BASLIGI[row.durum],
        body="\n".join(satirlar),
        severity="info",
        tenant_id=row.tenant_id,
        case_id=row.case_id,
        dedupe_key=f"hata-sonuc:{row.id}",
        link=_link(row),
    )


def _dogrudan_duzeltebilir(db: Session, case: Any, email: str) -> bool:
    """Bu kullanıcı bu davada doğrudan düzeltme yapabilir mi: sorumlu avukat ya da yönetici."""
    if not email:
        return False
    if email in _admin_emails():
        return True
    return email in resolve_case_recipients(db, case)


def _dogrudan_duzelt(
    db: Session, payload: HataBildirimiCreate, case: Any, user: dict, email: str, tenant_id: str,
) -> Any:
    """Bildirenin yazdığı doğru değeri karta yazar ve KAPALI (COZULDU) bir kayıt döner.

    Kapılar HİÇBİR şey yazılmadan koşar: alan beyaz listede mi (422), kullanıcı bu
    davada yetkili mi (403), ekrandaki değer hâlâ kayıtlı değer mi (409 — bayat ekranla
    başkasının düzeltmesi ezilmesin), yeni değer gerçekten farklı mı (422). Yazım
    `enrich_case`ten geçer: tarihçe (`source=DOGRUDAN_KAYNAK`, yapan kişi) + esas no'da
    `sync_current_esas`. Kimseye bildirim gitmez; kayıt denetim izi olarak kalır.
    """
    alan = payload.alan
    if alan not in DOGRUDAN_DUZELTME_ALANLARI:
        raise HTTPException(status_code=422, detail="Bu alan doğrudan düzeltilemez; bildirim olarak gönderin.")
    if not _dogrudan_duzeltebilir(db, case, email):
        raise HTTPException(
            status_code=403,
            detail="Doğrudan düzeltmeyi yalnız davanın sorumlu avukatı ya da yönetici yapabilir.",
        )
    kayitli = str(getattr(case, alan) or "").strip()
    if (payload.mevcut_deger or "") != kayitli:
        raise HTTPException(
            status_code=409,
            detail="Kayıt bu arada değişmiş. Sayfayı yenileyip güncel değeri kontrol edin.",
        )
    if payload.dogru_deger == kayitli:
        raise HTTPException(status_code=422, detail="Yeni değer kayıtlı değerle aynı.")

    yapan = (user.get("name") or "").strip() or email
    sonuc = enrich_case(
        case.id, {alan: payload.dogru_deger}, [],
        changed_by=yapan, source=DOGRUDAN_KAYNAK, tenant_id=tenant_id,
    )
    if sonuc is None:
        raise HTTPException(status_code=404, detail="Dava bulunamadı")
    if sonuc.get("error") or not sonuc.get("updated_fields"):
        # Nihai ERROR'u enrich_case yazdı (log sözleşmesi: TEK ERROR).
        raise HTTPException(status_code=500, detail="Düzeltme uygulanamadı. Lütfen tekrar deneyin.")

    simdi = dt.datetime.now(dt.timezone.utc)
    row: Any = models.HataBildirimi(
        tenant_id=case.tenant_id,
        case_id=payload.case_id,
        alan=alan,
        alan_etiketi=payload.alan_etiketi,
        mevcut_deger=payload.mevcut_deger,
        dogru_deger=payload.dogru_deger,
        aciklama=payload.aciklama,
        durum="COZULDU",
        alicilar=[],
        bildiren_email=email,
        bildiren_ad=(user.get("name") or "").strip() or None,
        created_at=simdi,
        kapatan_email=email,
        kapatan_ad=(user.get("name") or "").strip() or None,
        kapatma_notu=DOGRUDAN_NOTU,
        kapatildi_at=simdi,
    )
    db.add(row)
    db.commit()
    # Kart başka oturumda (enrich_case) yazıldı — künye güncel esas no'yu taşısın.
    db.expire_all()
    logger.info(
        "Hata doğrudan düzeltildi: id=%s case_id=%s alan=%s yapan=%s",
        row.id, row.case_id, alan, email,
    )
    return row


@router.get("/api/hata-bildirimleri/dogrudan")
def list_dogrudan_alanlar(
    case_id: int = Query(...),
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """İstek sahibinin bu davada doğrudan düzeltebileceği alan anahtarları (yetkisizse boş)."""
    case = _hedef_or_404(db, tenant_id, case_id, None)
    yetkili = _dogrudan_duzeltebilir(db, case, _user_email(user))
    return {"alanlar": list(DOGRUDAN_DUZELTME_ALANLARI) if yetkili else []}


@router.post("/api/hata-bildirimleri", response_model=HataBildirimiRead, status_code=201)
def create_hata_bildirimi(
    payload: HataBildirimiCreate,
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    email = _require_user_email(user)
    hedef = _hedef_or_404(db, tenant_id, payload.case_id, payload.client_id)
    if payload.dogrudan_duzelt:
        duzeltilen = _dogrudan_duzelt(db, payload, hedef, user, email, tenant_id)
        return _serialize(duzeltilen, _hedef_etiketleri(db, [duzeltilen]).get(duzeltilen.id, ""))
    alicilar = _alicilari_sec(db, payload.alicilar, email)
    row: Any = models.HataBildirimi(
        tenant_id=hedef.tenant_id,
        case_id=payload.case_id,
        client_id=payload.client_id,
        alan=payload.alan,
        alan_etiketi=payload.alan_etiketi,
        mevcut_deger=payload.mevcut_deger,
        dogru_deger=payload.dogru_deger,
        aciklama=payload.aciklama,
        durum=HATA_DURUM_ACIK,
        alicilar=alicilar,
        bildiren_email=email,
        bildiren_ad=(user.get("name") or "").strip() or None,
        created_at=dt.datetime.now(dt.timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    etiket = _hedef_etiketleri(db, [row]).get(row.id, "")
    try:
        alici_sayisi = _alicilara_bildir(db, row, etiket)
    except Exception as exc:  # bildirim yazımı kaydı düşürmez (modül şerhi)
        db.rollback()
        alici_sayisi = 0
        logger.warning("Hata bildirimi zile yazılamadı (bildirim=%s): %s", row.id, exc)
    logger.info(
        "Hata bildirimi açıldı: id=%s case_id=%s client_id=%s alan=%s alıcı=%s",
        row.id, row.case_id, row.client_id, row.alan, alici_sayisi,
    )
    return _serialize(row, etiket)


@router.get("/api/hata-bildirimleri/alicilar", response_model=list[HataAliciAdayi])
def list_hata_alicilari(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Alıcı seçicisi: idari personel + iç avukatlar + yönetici − istek sahibi."""
    email = _user_email(user)
    return [a for a in error_report_candidates(db) if a["email"] != email]


@router.get("/api/hata-bildirimleri", response_model=list[HataBildirimiRead])
def list_hata_bildirimleri(
    case_id: Optional[int] = Query(default=None),
    client_id: Optional[int] = Query(default=None),
    durum: str = Query(default="acik", pattern="^(acik|hepsi)$"),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    if case_id is not None and client_id is not None:
        raise HTTPException(status_code=422, detail="case_id ve client_id birlikte verilemez.")

    q = db.query(models.HataBildirimi)
    if case_id is not None or client_id is not None:
        _hedef_or_404(db, tenant_id, case_id, client_id)
        if case_id is not None:
            q = q.filter(models.HataBildirimi.case_id == case_id)
        else:
            q = q.filter(models.HataBildirimi.client_id == client_id)
    else:
        # Pano listesi: paylaşımlı havuz deseni + soft-silinmiş hedefler hariç.
        q = (
            q.outerjoin(models.Case, models.Case.id == models.HataBildirimi.case_id)
            .outerjoin(models.Client, models.Client.id == models.HataBildirimi.client_id)
            .filter(tenant_filter_clause(models.HataBildirimi, tenant_id))
            .filter(models.Case.deleted_at.is_(None), models.Client.deleted_at.is_(None))
        )
    if durum == "acik":
        q = q.filter(models.HataBildirimi.durum == HATA_DURUM_ACIK)

    rows: list[Any] = (
        q.order_by(models.HataBildirimi.created_at.desc(), models.HataBildirimi.id.desc())
        .limit(limit)
        .all()
    )
    etiketler = _hedef_etiketleri(db, rows)
    return [_serialize(r, etiketler.get(r.id)) for r in rows]


@router.post("/api/hata-bildirimleri/{bildirim_id}/kapat", response_model=HataBildirimiRead)
def close_hata_bildirimi(
    bildirim_id: int,
    payload: HataBildirimiKapat,
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    email = _require_user_email(user)
    _gorunur_bildirim_or_404(db, tenant_id, bildirim_id)

    # Koşullu UPDATE: iki kişi aynı anda kapatırsa yalnız biri satırı alır,
    # öteki 409 görür (ikinci "çözüldü" bildirimi üretilmez).
    guncellenen = (
        db.query(models.HataBildirimi)
        .filter(
            models.HataBildirimi.id == bildirim_id,
            models.HataBildirimi.durum == HATA_DURUM_ACIK,
        )
        .update(
            {
                "durum": payload.sonuc,
                "kapatan_email": email,
                "kapatan_ad": (user.get("name") or "").strip() or None,
                "kapatma_notu": payload.kapatma_notu,
                "kapatildi_at": dt.datetime.now(dt.timezone.utc),
            },
            synchronize_session=False,
        )
    )
    db.commit()
    if not guncellenen:
        raise HTTPException(status_code=409, detail="Bu hata bildirimi zaten kapatılmış.")

    db.expire_all()
    row: Any = db.query(models.HataBildirimi).filter(models.HataBildirimi.id == bildirim_id).first()
    etiket = _hedef_etiketleri(db, [row]).get(bildirim_id, "")
    try:
        _kapanisi_bildir(db, row, etiket)
    except Exception as exc:  # bildirim yazımı kapanışı düşürmez (modül şerhi)
        db.rollback()
        logger.warning("Hata bildirimi sonucu zile yazılamadı (bildirim=%s): %s", bildirim_id, exc)
    logger.info("Hata bildirimi kapatıldı: id=%s sonuç=%s", bildirim_id, payload.sonuc)
    return _serialize(row, etiket)
