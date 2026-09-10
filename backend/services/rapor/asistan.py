"""Rapor asistanı — doğal dil → `RaporTanimi` (G132, plan §2.6, K6-K9).

Akış: kullanıcı mesajları (son 20) `contents` dizisi olur, sistem talimatı
kataloğu registry'den kompakt gömer (`katalog_metni`), Gemini JSON şemalı
(`RaporAsistanCevabi`) tek atış cevap verir; cevaptaki `tanim` sunucuda
`asistan_tanimini_cevir` → `RaporTanimi` → `motor.tanimi_dogrula` yolundan
geçer (manuel tanımla AYNI doğrulama, K6). Geçmezse `warning` + `tanim=null`
ile yine `complete` — kullanıcı asistanın metnini görür, ama geçersiz tanım
istemciye hiçbir zaman `tanim` olarak gitmez.

Bu modül DB'YE DOKUNMAZ (K6): oturum fabrikası import etmez, satır görmez.
Seçenek listeleri `registry.secenekleri_getir(kolon, db=None)` ile yalnız
sabit çekirdekten gelir. İndirme frontend'in `/export` çağrısıyladır (K7);
burada yalnız `eylem` önerilir.

Olay sözleşmesi (plan §2.6, `analyzer._failed_event` ile uyumlu):
    {"status":"info","message":...}
    {"status":"warning","message":...}          # tanım doğrulanamadı, tanim=null
    {"status":"complete","cevap","tanim","eylem"}
    {"status":"failed","error_ozet","error_kod"}
`complete`/`failed` SON olaydır. Log sözleşmesi: denemeler WARNING
(`_gemini_call_with_retry` içinde), nihai başarısızlık TEK ERROR (burada).

`analyzer` BİLEREK tembel import edilir: modül import'unda `GEMINI_MODEL_NAME`
env'i zorunlu (yoksa ValueError) — `routes/reports.py` bu modülü import eder ve
CI/lokal testler o env olmadan da `routes.reports`'u yüklemeli
(`routes/case_intake.py` aynı nedenle intake motorunu route içinde import eder).
Gemini çağrısı YALNIZ `analyzer._gemini_call_with_retry` üzerinden gider
(devre kesici + retry + health sayacı tek yerde); doğrudan SDK istemcisi burada yok.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import uuid
from decimal import Decimal, InvalidOperation
from types import ModuleType
from typing import Any, AsyncIterator, Optional, Sequence

from google.genai import types as genai_types
from pydantic import ValidationError

import gemini_client
from config.settings import settings
from prompts import get_rapor_asistani_instruction
from schemas_rapor import (
    DEGERSIZ_OPLAR, SOHBET_MESAJ_MAX, AsistanFiltre, AsistanTanimi, RaporAsistanCevabi, RaporDogrulamaHatasi,
    RaporTanimi, SohbetMesaji, SohbetTamamlandi, pydantic_hatasini_cevir,
)
from services.rapor import motor, registry
from services.rapor.registry import Iliski, Kolon, VeriKaynagi

logger = logging.getLogger(__name__)

# Gemini `contents` rolü: kullanıcı → "user", asistan → "model".
_GEMINI_ROLU = {"user": "user", "assistant": "model"}
_TRUE_METINLERI = frozenset({"true", "1", "evet", "doğru", "dogru", "aktif"})
_FALSE_METINLERI = frozenset({"false", "0", "hayır", "hayir", "yanlış", "yanlis", "pasif"})
# `in` listesinde "(boş)" → `null` (plan §5.2, G141): Gemini şeması metin listesi taşır, sözleşme
# `null` öğesi ister; küçük harf + boşluksuz karşılaştırılır.
BOS_SABITLERI = frozenset({"(boş)", "(bos)"})


# ─── Model seçimi (K9) ───────────────────────────────────────────────────────

def get_rapor_model() -> str:
    """`GEMINI_RAPOR_MODEL` (settings, boot'ta donar); boşsa `GEMINI_INTAKE_MODEL`
    (`case_intake_analyzer.get_intake_model`, her çağrıda env). Devre kesici
    model-başına olduğundan asistanın modeli intake'ten ayrılabilir."""
    secilen = (settings.gemini_rapor_model or "").strip()
    if secilen:
        return secilen
    from case_intake_analyzer import get_intake_model  # tembel: analyzer zinciri (modül şerhi)

    return get_intake_model()


def _analyzer() -> ModuleType:
    """Tembel `analyzer` (modül docstring'i). Testler `analyzer._gemini_call_with_retry`'ı
    monkeypatch'ler — erişim çağrı anında modül özniteliğinden yapılır."""
    import analyzer

    return analyzer


# ─── Katalog metni (registry'den, elle liste YOK) ────────────────────────────

def _kolon_satiri(kolon: Kolon) -> str:
    parcalar = [kolon.anahtar, kolon.etiket, kolon.tip]
    if kolon.tip == "liste":
        secenekler = registry.secenekleri_getir(kolon, None)
        if secenekler:
            parcalar.append("|".join(secenekler))
    if not kolon.secilebilir:
        # Sanal `arama` (G141): kolon listesine/sıralamaya giremez, yalnız filtre
        parcalar.append(f"yalnız filtre (kolon listesine girmez; op: {'|'.join(kolon.oplar)})")
    elif kolon.turetilmis:
        if kolon.filtrelenebilir:
            parcalar.append(f"türetilmiş (filtre yalnız: {'|'.join(kolon.oplar)}; sıralama yok)")
        else:
            parcalar.append("türetilmiş (filtre/sıralama yok)")
    return " · ".join(parcalar)


def katalog_metni() -> str:
    """Sistem talimatına gömülen kompakt katalog: her kaynak için başlık +
    varsayılan kolonlar + `anahtar · etiket · tip[ · seçenekler]` satırları.
    G137'nin kullanılabilirlik alanları (`grup`, `kontrol`, `hizli_filtreler`,
    `kolon_setleri`, `oneriler`) BİLEREK gömülmez — prompt gürültüsü (öneriler
    300'e kadar değer); yalnız yeni kolonlar doğal olarak girer (plan §4.2).
    G141'in veriden seçenekleri de gömülmez (DB yok, K6; `secenekleri_getir(db=None)`
    yalnız sabit çekirdek); sanal `arama` kolonu "yalnız filtre" şerhiyle girer."""
    bloklar: list[str] = []
    for kaynak in registry.KAYNAKLAR.values():
        satirlar = [
            f"## {kaynak.anahtar} — {kaynak.etiket}: {kaynak.aciklama}",
            f"varsayılan kolonlar: {', '.join(kaynak.varsayilan_kolonlar)}",
        ]
        satirlar.extend(_kolon_satiri(k) for k in kaynak.kolonlar.values() if k.bag is None)
        satirlar.extend(_iliski_satiri(kaynak, i) for i in kaynak.iliskiler)
        bloklar.append("\n".join(satirlar))
    return "\n\n".join(bloklar)


def _iliski_satiri(kaynak: VeriKaynagi, iliski: Iliski) -> str:
    """G166 bağlı kaynak satırı: bağlı kolonlar tek tek değil, ilişki başına bir satır
    (hedef kaynağın kolon listesi zaten metinde; `haric`/türetilmiş atlananlar sayılır).
    Prompt gürültüsünü sınırlar: davalar'a 56 bağlı kolon 3 satırla girer."""
    anahtarlar = [k.anahtar[len(iliski.anahtar) + 1:] for k in kaynak.kolonlar.values() if k.bag == iliski.anahtar]
    hedef = registry.CEKIRDEK[iliski.hedef]
    atlanan = [k.anahtar for k in hedef.kolonlar.values() if k.secilebilir and k.anahtar not in anahtarlar]
    parcalar = [
        f"{iliski.anahtar}.<kolon> · {iliski.etiket} · BAĞLI: '{iliski.hedef}' kaynağının kolonları "
        f"'{iliski.anahtar}.' önekiyle (ör. {iliski.anahtar}.{anahtarlar[0]})",
    ]
    if atlanan:
        parcalar.append(f"hariç: {', '.join(atlanan)}")
    if iliski.coklu:
        parcalar.append("çoklu: değerler ' ; ' ile birleşik; filtre = herhangi bir bağlı kaydın kolonu; sıralama yok")
    else:
        parcalar.append("tekil: filtre/sıralama düz kolon gibi")
    return " · ".join(parcalar)


# ─── Asistan tanımı → RaporTanimi (tip çevirisi + aynı doğrulama) ────────────

def _mantik(deger: str) -> Any:
    d = deger.strip().lower()
    if d in _TRUE_METINLERI:
        return True
    if d in _FALSE_METINLERI:
        return False
    return deger   # motor "mantık değeri true/false olmalı" ile reddeder


def _sayi(deger: str) -> Any:
    d = deger.strip().replace(" ", "")
    try:
        sayi = Decimal(d)
    except InvalidOperation:
        return deger   # motor "sayısal değer bekleniyor" ile reddeder
    if not sayi.is_finite():
        return deger
    if sayi == sayi.to_integral_value():
        return int(sayi)
    return float(sayi)


def _tekil_deger(kolon: Optional[Kolon], deger: str) -> Any:
    """Metin değeri kolon tipine göre Python tipine çevirir; kolon katalogda
    yoksa metin kalır (motor `katalogda olmayan kolon` ile reddeder)."""
    if kolon is None:
        return deger
    if kolon.tip == "mantik":
        return _mantik(deger)
    if kolon.tip in ("sayi", "para"):
        return _sayi(deger)
    return deger.strip() if kolon.tip == "tarih" else deger


def _bos_mu(deger: str) -> bool:
    return deger.strip().lower() in BOS_SABITLERI


def _filtre_degeri(kolon: Optional[Kolon], f: AsistanFiltre) -> Any:
    if f.op in DEGERSIZ_OPLAR:
        return None
    if f.op in ("in", "between"):
        liste = list(f.degerler) if f.degerler is not None else ([f.deger] if f.deger is not None else [])
        if f.op == "in":
            # "(boş)" → null (plan §5.2); `between`de çevrilmez — Pydantic "null yalnız 'in' listesinde" der
            return [None if _bos_mu(str(d)) else _tekil_deger(kolon, str(d)) for d in liste]
        return [_tekil_deger(kolon, str(d)) for d in liste]
    if f.deger is None and f.degerler:
        return _tekil_deger(kolon, str(f.degerler[0]))
    return None if f.deger is None else _tekil_deger(kolon, f.deger)


def asistan_tanimini_cevir(tanim: AsistanTanimi) -> dict[str, Any]:
    """Gemini şemasındaki (metin değerli) tanımı `RaporTanimi` gövdesine çevirir.
    Doğrulama YAPMAZ — `tanimi_dogrula` yapar."""
    kaynak = registry.kaynak_bul(tanim.veri_kaynagi)
    kolonlar = kaynak.kolonlar if kaynak is not None else {}
    filtreler = []
    for f in tanim.filtreler:
        govde: dict[str, Any] = {"alan": f.alan, "op": f.op}
        deger = _filtre_degeri(kolonlar.get(f.alan), f)
        if deger is not None:
            govde["deger"] = deger
        filtreler.append(govde)
    return {
        "veri_kaynagi": tanim.veri_kaynagi,
        "kolonlar": list(tanim.kolonlar),
        "filtreler": filtreler,
        "siralama": [{"alan": s.alan, "yon": s.yon} for s in tanim.siralama],
    }


def tanimi_dogrula(tanim: AsistanTanimi) -> RaporTanimi:
    """Asistan tanımı → `RaporTanimi` (Pydantic sınırlar) → `motor.tanimi_dogrula`
    (registry: anahtar/op/tip/değer). Manuel tanımla TEK doğrulama yolu (K6);
    her iki katman da `RaporDogrulamaHatasi` yükseltir."""
    try:
        rapor_tanimi = RaporTanimi.model_validate(asistan_tanimini_cevir(tanim))
    except ValidationError as e:
        raise pydantic_hatasini_cevir(e) from None
    motor.tanimi_dogrula(rapor_tanimi)
    return rapor_tanimi


# ─── Gemini isteği ───────────────────────────────────────────────────────────

def icerikleri_kur(mesajlar: Sequence[SohbetMesaji]) -> list[genai_types.Content]:
    """Son `SOHBET_MESAJ_MAX` mesaj → Gemini `contents`. Baştaki asistan
    mesajları atılır (Gemini dizinin kullanıcıyla başlamasını ister; arayüz
    karşılama metniyle açabilir)."""
    son = list(mesajlar)[-SOHBET_MESAJ_MAX:]
    while son and son[0].rol != "user":
        son.pop(0)
    return [
        genai_types.Content(role=_GEMINI_ROLU[m.rol], parts=[genai_types.Part(text=m.icerik)])
        for m in son
    ]


def _talimat(mevcut_tanim: Optional[RaporTanimi], bugun: Optional[dt.date] = None) -> str:
    mevcut = json.dumps(mevcut_tanim.model_dump(), ensure_ascii=False) if mevcut_tanim is not None else None
    return get_rapor_asistani_instruction(
        katalog_metni(), (bugun or dt.date.today()).isoformat(), mevcut_tanim_json=mevcut,
    )


def _hata_esle(exc: BaseException, analyzer: ModuleType, hata_id: str) -> tuple[str, str]:
    """İstisna → (`error_kod`, kullanıcı özeti). Etiketler `analyzer._failed_event`
    sözlüğünden; sınıflandırma kod bazlı (`analyzer._api_error_kod`)."""
    if isinstance(exc, analyzer.GeminiTruncatedError):
        return "gemini_truncated", f"Asistanın cevabı uzunluk sınırına takıldı; isteği kısaltıp tekrar deneyin. (Kod: {hata_id})"
    if isinstance(exc, analyzer.GeminiBlockedError):
        return "gemini_blocked", f"Asistanın cevabı içerik filtresine takıldı; isteği farklı ifade edin. (Kod: {hata_id})"
    if isinstance(exc, (ValidationError, json.JSONDecodeError)):
        return "schema_invalid", f"Asistanın cevabı beklenen yapıda değildi; tekrar deneyin. (Kod: {hata_id})"
    kod = analyzer._api_error_kod(exc)
    if kod == "gemini_saturated":
        if isinstance(exc, gemini_client.GeminiCircuitOpenError):
            ozet = ("Yapay zeka servisi art arda hata verdiği için kısa süreliğine devre dışı bırakıldı "
                    f"(koruma devrede). Lütfen 1 dakika sonra tekrar deneyin. (Kod: {hata_id})")
        else:
            ozet = f"Yapay zeka servisi şu an yoğun; lütfen kısa süre sonra tekrar deneyin. (Kod: {hata_id})"
        return kod, ozet
    return "analysis_error", f"Rapor asistanı teknik bir sorun nedeniyle cevap veremedi. (Kod: {hata_id})"


async def sohbet(
    mesajlar: Sequence[SohbetMesaji],
    mevcut_tanim: Optional[RaporTanimi],
    tenant_id: str,
) -> AsyncIterator[dict[str, Any]]:
    """Plan §2.6 olay akışı. `tenant_id` yalnız log bağlamıdır — asistan tenant
    verisine dokunmaz; tanım tenant filtresini çalıştırıldığı uçta alır (K2)."""
    analyzer = _analyzer()
    yield {"status": "info", "message": "Rapor tanımı hazırlanıyor"}

    hata_id = str(uuid.uuid4())[:8]
    model = get_rapor_model()
    try:
        config = genai_types.GenerateContentConfig(
            system_instruction=_talimat(mevcut_tanim),
            response_mime_type="application/json",
            response_schema=RaporAsistanCevabi,
        )
        stats: dict[str, Any] = {"retry_count": 0, "retry_wait_ms": 0}
        response = await analyzer._gemini_call_with_retry(config, icerikleri_kur(mesajlar), stats=stats, model=model)
        metin = analyzer._ensure_response_text(response, context="Rapor asistanı")
        cevap = RaporAsistanCevabi.model_validate_json(metin)
    except Exception as exc:
        kod, ozet = _hata_esle(exc, analyzer, hata_id)
        # Nihai başarısızlık: TEK ERROR (denemeler _gemini_call_with_retry'da WARNING)
        logger.error(
            "Rapor asistani basarisiz [ID: %s] kod=%s model=%s tenant=%s: %s: %s",
            hata_id, kod, model, tenant_id, type(exc).__name__, exc,
        )
        yield analyzer._failed_event(ozet, kod)
        return

    tanim: Optional[RaporTanimi] = None
    eylem = cevap.eylem
    if cevap.tanim is not None:
        try:
            tanim = tanimi_dogrula(cevap.tanim)
        except RaporDogrulamaHatasi as e:
            logger.warning("Rapor asistani tanimi dogrulanamadi (%s: %s) — tanim=null", e.alan, e.sebep)
            eylem = None   # geçersiz tanım üzerinde eylem önerilmez
            yield {
                "status": "warning",
                "message": f"Asistanın ürettiği tanım doğrulanamadı ({e.alan}: {e.sebep}); tanım olmadan devam ediliyor.",
            }
    if tanim is None and eylem is not None:
        # Sözleşme (prompt + K7): tanım yoksa eylem de yok. Gerçek Gemini duman testinde
        # (07.09) model "davaları listele" için tanim=null + eylem=onizle döndürdü; istemci
        # bu eylemi mevcut tanım üzerinde yürütürdü. Model kuralı ihlal etse de sunucu keser.
        logger.warning("Rapor asistani tanim=null ile eylem=%s dondurdu — eylem dusuruldu", eylem)
        eylem = None
    # G167 teşhis izi (INFO, değer yok — yalnız anahtar/op): "tamam" turunda modelin tanımı değiştirip
    # değiştirmediği prod'da buradan okunur (10.09 dersi: log yokken sözle onay arızası körlemesine kaldı).
    logger.info(
        "Rapor asistani cevabi: eylem=%s kaynak=%s kolon=%s filtre=%s siralama=%s mevcut_ile_ayni=%s son_mesaj=%r",
        eylem, tanim.veri_kaynagi if tanim else None, len(tanim.kolonlar) if tanim else 0,
        [f"{f.alan}:{f.op}" for f in tanim.filtreler] if tanim else None,
        [f"{s.alan}:{s.yon}" for s in tanim.siralama] if tanim else None,
        (tanim.model_dump() == mevcut_tanim.model_dump()) if (tanim and mevcut_tanim) else None,
        (list(mesajlar)[-1].icerik[:60] if mesajlar else ""),
    )
    yield SohbetTamamlandi(cevap=cevap.cevap, tanim=tanim, eylem=eylem).model_dump()
