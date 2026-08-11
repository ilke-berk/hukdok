"""Veritabanı hata sınıflandırması (Faz 5-B, plan 5.3).

Benzersizlik ihlali tespiti MESAJ METNİNE değil SQLSTATE koduna ve ihlal
edilen kısıt/indeks adına bakar. Eski yol (`"tracking_no" in str(e)`) iki
yönden de yanılıyordu:

  * yanlış pozitif — `cases` tablosunda `uq_cases_sistem_no` da UNIQUE'tir ve
    o ihlalin DETAIL satırında da tablo/kolon adları geçebilir; "ofis numarası
    çakıştı" denip kullanıcı boşuna sıra numarası artırır,
  * yanlış negatif — mesaj biçimi sürücü/PostgreSQL sürümüne bağlıdır; metin
    değişirse çakışma sessizce "bilinmeyen hata" (500) olur.

PostgreSQL ihlal edilen indeksin adını hata alanlarında gönderir; psycopg2
bunu `exc.orig.diag.constraint_name` olarak açar (UNIQUE INDEX ihlalinde de
dolar — `ix_cases_tracking_no` üzerinde doğrulandı).
"""
from typing import Any, Optional

# PostgreSQL SQLSTATE: unique_violation
UNIQUE_VIOLATION_SQLSTATE = "23505"


def _dbapi_error(exc: Any) -> Any:
    """SQLAlchemy sarmalayıcısının (IntegrityError) altındaki sürücü hatası."""
    return getattr(exc, "orig", None) or exc


def unique_violation_constraint(exc: Any) -> Optional[str]:
    """23505 ise ihlal edilen kısıt/indeks adını döner, değilse None.

    Kısıt adı sürücüden okunamazsa boş string döner (23505 olduğu kesin ama
    hangi kısıt olduğu bilinmiyor) — çağıran ad eşlemesi yapıyorsa bunu
    "eşleşme yok" saymalıdır; `is_unique_violation` bunu uygular.
    """
    orig = _dbapi_error(exc)
    # psycopg2: pgcode · psycopg3: sqlstate (ikisi de destekli — sürücü
    # değişimi bu tespiti sessizce bozmasın)
    code = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
    if code != UNIQUE_VIOLATION_SQLSTATE:
        return None
    diag = getattr(orig, "diag", None)
    return getattr(diag, "constraint_name", None) or ""


def is_unique_violation(exc: Any, constraint: Optional[str] = None) -> bool:
    """Hata bir UNIQUE ihlali mi? `constraint` verilirse ADI da eşleşmeli.

    constraint=None → tabloda hangi kısıt olursa olsun True (referans
    listelerinde tek anlam var: "bu kayıt zaten mevcut").
    """
    name = unique_violation_constraint(exc)
    if name is None:
        return False
    if constraint is None:
        return True
    return name == constraint
