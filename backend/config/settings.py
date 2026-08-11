"""Merkezi limit ve zaman-bütçesi ayarları (Faz 5-A, plan 5.1 + 5.2).

Koda saçılmış limitlerin tek evi: her alan env ile ayarlanabilir, tüm
varsayılanlar taşınma ÖNCESİ koddaki değerlerle birebir aynıdır (davranış-nötr
göç; test_faz5_settings_budget bekçileri bunu kilitler).

Tasarım kararları:

- **Boot'ta donma:** değerler süreç başlangıcında (ilk import) bir kez okunur.
  Konteynerde env zaten boot'ta sabittir (compose `env_file` .env'i süreç
  env'ine enjekte eder — Python import'larından ÖNCE hazırdır); eski
  `os.getenv`-her-çağrıda deseniyle pratik fark yoktur. Testler env yerine
  settings attribute'unu monkeypatch'ler.
- **Yalnız süreç env'i okunur:** pydantic-settings'in kendi .env okuması
  bilinçli KAPALI — host'ta koşan testler geliştiricinin .env'inden değer
  kapmasın (konteynerde compose enjekte ettiği için fark yaratmaz).
- **Toleranslı ayrıştırma:** bozuk env değeri (örn. GS_TIMEOUT_SECONDS=hizli)
  uygulamayı DÜŞÜRMEZ; WARNING loglanıp alan varsayılanına düşülür. Bu, eski
  `_gs_timeout()`'un int()-ValueError fallback sözleşmesinin genellenmiş hali
  ("settings import'u asla patlamamalı").
- **Modül alias'ları korunur:** tüketici modüller sabitlerini buradan
  başlatır (örn. `file_utils.MAX_UPLOAD_BYTES`) — mevcut import'lar ve
  testlerin monkeypatch noktaları aynen çalışmaya devam eder.

Taşınmayanlar (bilinçli — limit değil, başka paketlerin politika sabitleri):
görüntü boyut korumaları (MAX_IMAGE_*, 2026-07-29 OOM kararı), dönüşüm
semafor SAYILARI (2/1/1, aynı karar), `wait_for_files_active` 120 sn tavanı
(3-C'de bilinçli ayrı bütçe), retry/backoff sabitleri (3-A/3-B/3-C/3-D
politikaları), DB timeout env'leri (3-E'de kendi evinde zaten env-tunable),
cache DİZİN env'leri (yol konfigürasyonu), confirm idempotency eşikleri
(3-D, PROCESS_CACHE TTL hizası kendi modülünde belgeli), upload_queue
backoff merdiveni (3-A).
"""
import logging

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    # ── Yükleme boyutları ────────────────────────────────────────────────
    # Tek dosya limiti (file_utils + upload route'ları). Env: MAX_UPLOAD_MB
    max_upload_mb: int = 50
    # Tüm istek gövdesi limiti (api.py RequestSizeLimitMiddleware). Ayrı
    # düğme: multipart ek yükü tek-dosya limitinden bağımsız ayarlanabilsin.
    request_size_limit_mb: int = 50

    # ── PDF işleme ───────────────────────────────────────────────────────
    max_pdf_pages: int = 500
    # load_and_analyze_pdf / metin çıkarma executor bekleme tavanı
    pdf_parse_timeout_seconds: float = 60.0

    # ── Dönüşüm zaman tavanları (5.2 bütçesiyle birlikte çalışır) ────────
    # GhostScript alt-süreç tavanı; istek yolunda kalan bütçeyle kırpılır.
    gs_timeout_seconds: int = 240
    # LibreOffice alt-süreç tavanı. Plan 5.1'deki env adı LIBREOFFICE_TIMEOUT;
    # birimli varyant da kabul edilir.
    libreoffice_timeout_seconds: int = Field(
        default=120,
        validation_alias=AliasChoices(
            "LIBREOFFICE_TIMEOUT", "LIBREOFFICE_TIMEOUT_SECONDS"
        ),
    )

    # ── İstek zaman bütçesi (5.2) ────────────────────────────────────────
    # nginx (host + konteyner) proxy_read_timeout penceresi — hizalama çıpası.
    request_time_budget_seconds: float = 300.0
    # /confirm PDF/A dönüşüm zincirinin toplam payı: LO + GS + semafor
    # beklemeleri bu bütçeden pay alır (kalan ~30 sn DB/kuyruk/e-posta/yanıt).
    # Bekçi testi: bütçe + 30 ≤ request_time_budget (garanti 504 penceresi yok).
    confirm_conversion_budget_seconds: float = 270.0
    # Bütçeli yolda dönüşüm semaforu bekleme tavanı — dolarsa 503 "meşgul"
    # (sonsuz bekleyip nginx 504'üne çarpmak yerine hızlı ve dürüst sinyal).
    conversion_acquire_timeout_seconds: float = 30.0

    # ── E-posta ek limitleri (0-C: Graph /sendMail ~4 MB gövde tavanı) ───
    # int: kullanıcı mesajlarına "(3 MB)" olarak giriyor (eski biçim korunur)
    email_max_single_mb: int = 3
    email_max_total_mb: int = 3

    # ── SharePoint sayaç tahsisi (/process fetch_counter) ────────────────
    counter_fetch_timeout_seconds: float = 10.0

    # ── Cache TTL'leri (routes/processing DiskTTLCache) ──────────────────
    process_cache_ttl_seconds: int = 1800
    download_cache_ttl_seconds: int = 3600

    # ── Hız sınırı (slowapi varsayılan kovası) ───────────────────────────
    rate_limit_default: str = "100/minute"

    # ── Gemini zaman bütçesi (3-C deseni) ────────────────────────────────
    # Bekçi: deadline + tek deneme tavanı < request_time_budget (170+120=290).
    gemini_retry_deadline_seconds: float = 170.0
    gemini_http_timeout_ms: int = 120_000

    @field_validator("*", mode="before")
    @classmethod
    def _tolerant_env(cls, value, info):
        """Bozuk env değerinde alan varsayılanına düş (uygulamayı düşürme)."""
        if not isinstance(value, str):
            return value
        field = cls.model_fields[info.field_name]
        if field.annotation in (int, float):
            try:
                field.annotation(value.strip())
            except (TypeError, ValueError):
                logger.warning(
                    "Gecersiz env degeri %s=%r — varsayilan kullaniliyor: %s",
                    info.field_name, value, field.default,
                )
                return field.default
            return value.strip()
        return value


settings = Settings()
