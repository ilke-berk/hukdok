"""Tanıdık sorgu: girilen tarafları cari ve geçmiş dosya taraflarıyla eşleştirir.

Tek route: `POST /api/parties/check` (`api.py` include_router). Eşleştirme mantığı
`party_check.check_parties`'te; buradaki iş yalnız tenant filtresiyle aday satırları
(müvekkiller + `CaseParty`) DB'den toplamaktır. Salt okunur — kayıt yazmaz, akışı
engellemez; yalnız kullanıcıya uyarı gösterir.

Aday indeksi süreç-içi TTL cache'te (G017): iki tam tablo sorgusu (ölçüldü:
1.998 + 49.857 satır, ~550 ms) ve satır başına isim normalizasyonu her istekte
yeniden yapılıyordu. Cache satırları `party_check.prepare_candidate_rows`ten
geçmiş, yani normalizasyon anahtarları da hazır tutulur.
"""
import logging
import threading
import time

from fastapi import APIRouter, Depends

from auth_helpers import tenant_filter_clause
from dependencies import get_current_tenant
from managers.ttl_cache import TTLCache
from schemas import PartyCheckRequest, PartyCheckResponse
from database import SessionLocal
from party_check import check_parties, prepare_candidate_rows
import models

router = APIRouter()
logger = logging.getLogger(__name__)

# TTL 60 sn — İNVALİDASYON YOK, bilinçli:
# backend uvicorn'u 2 worker ile koşar (docker-entrypoint.sh) ve bu cache
# süreç-içidir; A worker'ında yapılan cari/taraf yazması B worker'ının
# cache'ini temizleyemez. Süreçler-arası invalidasyon (ör. DB damgası
# yoklaması) her isteğe bir sorgu ekler, kazancın bir kısmını geri verir.
# Bu yüzden tazelik garantisi yalnız TTL'dir ve kısa tutulmuştur: yeni
# eklenen müvekkil/taraf tanıdık sorguda EN GEÇ 60 sn içinde görünür.
# Salt okunur bir UYARI ucu olduğu için bu gecikme kabul edilebilir; bir dava
# açma oturumunda üst üste gelen sorgular tek ısınmayı paylaşır.
_CANDIDATE_TTL_SECONDS = 60

# TEK GİRDİ politikası: hazırlanmış indeks ölçülen veride ~34 MB ve iki worker
# ayrı ayrı tutar (konteyner limiti 2g, 2026-07-29 OOM dersleri). Anahtar
# tenant_id İÇERİR — izolasyon şart — ama bellekte aynı anda yalnız son
# tenant'ın indeksi kalır; tenant değişince eskisi düşürülür. İki tenant
# dönüşümlü sorgularsa her istek soğuk olur: bugünkü davranış, gerileme değil.
_candidate_cache = TTLCache(_CANDIDATE_TTL_SECONDS)
_cache_lock = threading.Lock()
_cached_key: str | None = None


def _load_candidates(tenant_id: str) -> tuple[list[dict], list[dict]]:
    """Aday satırlarını (cariler + geçmiş dosya tarafları) tenant süzgeciyle çeker
    ve karşılaştırmaya hazırlar."""
    db = SessionLocal()
    try:
        client_rows = [
            {
                "id": r.id, "name": r.name, "tc_no": r.tc_no,
                "cari_kod": r.cari_kod, "category": r.category,
                "contact_type": r.contact_type,
            }
            for r in (
                db.query(
                    models.Client.id, models.Client.name, models.Client.tc_no,
                    models.Client.cari_kod, models.Client.category,
                    models.Client.contact_type,
                )
                .filter(models.Client.active.is_(True))
                .filter(models.Client.deleted_at.is_(None))
                .filter(tenant_filter_clause(models.Client, tenant_id))
                .all()
            )
        ]

        party_rows = [
            {
                "id": r.id, "name": r.name, "tc_no": r.tc_no, "role": r.role,
                "party_type": r.party_type, "client_id": r.client_id,
                "case_id": r.case_id, "tracking_no": r.tracking_no,
                "case_subject": r.subject, "case_status": r.status,
            }
            for r in (
                db.query(
                    models.CaseParty.id, models.CaseParty.name,
                    models.CaseParty.tc_no, models.CaseParty.role,
                    models.CaseParty.party_type, models.CaseParty.client_id,
                    models.CaseParty.case_id, models.Case.tracking_no,
                    models.Case.subject, models.Case.status,
                )
                .join(models.Case, models.CaseParty.case_id == models.Case.id)
                .filter(tenant_filter_clause(models.Case, tenant_id))
                .filter(models.Case.deleted_at.is_(None))
                .all()
            )
        ]
    finally:
        db.close()
    return prepare_candidate_rows(client_rows), prepare_candidate_rows(party_rows)


def _candidate_rows(tenant_id: str) -> tuple[list[dict], list[dict]]:
    """(cariler, geçmiş taraflar) — TTL cache'ten, yoksa DB'den.

    Anahtar tenant_id'yi İÇERİR: aksi halde bir tenant'ın adayları diğerine
    sızardı (satırlar `tenant_filter_clause` ile süzülü geliyor).
    """
    global _cached_key

    key = f"candidates:{tenant_id}"
    # TTLCache süresi yalnız cleanup_stale'de işlenir (get bayat girdiyi de
    # döndürür) → süre kapısı burada. Sözlük en fazla bir girdi tutuyor, ucuz.
    _candidate_cache.cleanup_stale()
    entry = _candidate_cache.get(key)
    if entry is not None:
        return entry["clients"], entry["parties"]

    started = time.perf_counter()
    clients, parties = _load_candidates(tenant_id)
    elapsed_ms = (time.perf_counter() - started) * 1000
    with _cache_lock:
        if _cached_key is not None and _cached_key != key:
            _candidate_cache.delete(_cached_key)
        _candidate_cache.set(key, {"clients": clients, "parties": parties})
        _cached_key = key
    logger.info(
        "Tanıdık sorgu aday indeksi yenilendi: %d cari + %d taraf, %.0f ms "
        "(TTL %d sn)", len(clients), len(parties), elapsed_ms, _CANDIDATE_TTL_SECONDS
    )
    return clients, parties


def reset_candidate_cache_for_tests(ttl_seconds: int | None = None) -> None:
    """Süreç-global aday cache'ini boşaltır (yalnız testler için)."""
    global _candidate_cache, _cached_key

    with _cache_lock:
        _candidate_cache = TTLCache(
            _CANDIDATE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        )
        _cached_key = None


@router.post("/api/parties/check", response_model=PartyCheckResponse)
def api_check_parties(req: PartyCheckRequest, tenant_id: str = Depends(get_current_tenant)):
    """Tanıdık sorgu: girilen taraf isimlerini/TC'lerini cari kayıtları ve
    geçmiş dosya taraflarıyla karşılaştırır. Salt okunur; kayıt engellemez."""
    client_rows, party_rows = _candidate_rows(tenant_id)
    results = check_parties(
        [q.model_dump() for q in req.parties],
        client_rows,
        party_rows,
        exclude_case_id=req.exclude_case_id,
    )
    return {"results": results}
