# Otonom dava açma — çıkarım şemaları (Faz 2) + merge/hakem şemaları (Faz 3)
# + commit şemaları (Faz 4).
# Gemini'ye response_schema olarak verilir (structured output); kalibrasyon
# koşularıyla (calibration/run_calibration.py) itere edilmiş sürümdür.
from typing import Literal, Optional

from pydantic import BaseModel, Field

from schemas import CaseCreate, ClientPolicyCreate


class IntakeParty(BaseModel):
    ad: str
    # SIGORTALI / SIGORTA_SIRKETI poliçe belgeleri için: poliçede davacı/davalı
    # kavramı yoktur, merge adımında müvekkil eşleşmesiyle CLIENT/COUNTER'a çevrilir.
    rol: Literal[
        "DAVACI",
        "DAVALI",
        "MUDAHIL",
        "IHBAR_OLUNAN",
        "VEKIL",
        "SIGORTALI",
        "SIGORTA_SIRKETI",
        "DIGER",
    ]
    tc_no: Optional[str] = None


class CaseIntakeExtraction(BaseModel):
    # Belge kimliği
    belge_turu_tahmini: Optional[str] = None   # serbest metin; koda map merge'de
    belge_tarihi: Optional[str] = None         # ISO (YYYY-MM-DD)

    # Dava kartı çekirdeği
    mahkeme: Optional[str] = None              # daire dahil tam ad
    esas_no: Optional[str] = None              # "YYYY/N"
    yargi_turu: Optional[str] = None           # Hukuk/Ceza/İcra/İdari/Arabuluculuk/Savcılık
    dava_konusu: Optional[str] = None
    dava_acilis_tarihi: Optional[str] = None   # ISO
    teblig_tarihi: Optional[str] = None        # tebligat mazbatası varsa (cevap süresi için)
    uzmanlik_tahmini: Optional[str] = None     # tıbbi işlem/uzmanlık (ör. RİNOPLASTİ)

    # Taraflar
    taraflar: list[IntakeParty] = []

    # Tazminat (dilekçe sonuç/talep bölümünden; harca esas değer)
    maddi_tazminat: Optional[float] = None
    manevi_tazminat: Optional[float] = None

    # Sigorta / poliçe alanları (poliçe + atama yazısından).
    # Bir hekimin birden fazla poliçesi olabilir: her poliçe PDF'i ayrı analiz
    # edilir, merge adımında bu alanlar ÇOĞUNLUK OYUNA GİRMEZ — belge başına
    # toplanıp hekim başına poliçe LİSTESİ olarak taşınır. Dönem tarihleri,
    # olay/açılış tarihine göre ilgili poliçeyi seçmek için gerekli.
    # Faz 3'te bu alanlar kalıcı client_policies tablosunu besleyecek — eksiksiz kalmalı.
    police_no: Optional[str] = None
    police_turu: Optional[Literal["ZORUNLU", "TAMAMLAYICI", "DIGER"]] = None
    sigorta_sirketi: Optional[str] = None
    police_baslangic_tarihi: Optional[str] = None  # ISO — poliçe dönemi başı
    police_bitis_tarihi: Optional[str] = None      # ISO — poliçe dönemi sonu
    retroaktif_tarihi: Optional[str] = None        # ISO — geçmişe etkinlik; teminatın asıl başlangıcı
    sigortali_kurum: Optional[str] = None      # hekimin bağlı olduğu kurum / sigorta ettiren hastane
    teminat_limiti: Optional[float] = None     # olay başına teminat limiti (TL)
    hasar_dosya_no: Optional[str] = None       # şimdilik UI'ya bağlanmaz (karar 8)
    hukuk_no: Optional[str] = None             # sigorta şirketi hukuk dosya no — UI'ya bağlanmaz

    ozet: Optional[str] = None                 # 2-3 cümle, dava kartı notu kalitesinde


# --- Katman 2: kritik alan doğrulayıcı geçişi ---
# İkinci Gemini çağrısının şeması: "değer belgede geçiyor mu, kanıt cümlesi ne?"
# Yalnız kritik alanlara uygulanır (esas_no, tc_no, taraf rolleri — karar 2).


class CriticalFieldCheck(BaseModel):
    alan: str                                  # iddia anahtarı ("esas_no", "tc_no:AD", "rol:AD")
    deger: str                                 # doğrulanan değer (aynen geri yazılır)
    belgede_geciyor: bool
    kanit: Optional[str] = None                # belgeden kısa kanıt cümlesi/ifadesi


class CaseIntakeVerification(BaseModel):
    kontroller: list[CriticalFieldCheck] = []


# --- Katman 3: belgeler-arası hakem (Faz 3) ---
# Merge esas_no/mahkeme çelişkisi bulduğunda tüm belge özetlerini gören bir
# hakem LLM çağrısı meşru farkları ayırt eder (yeni esas, istinaf, birleşen
# dosya) ve gerekçeli karar döner. Çelişki yoksa hakem çağrılmaz.


class ArbiterDecision(BaseModel):
    alan: str                                  # "esas_no" | "court"
    secilen_deger: str                         # adaylardan biri, AYNEN
    gerekce: str                               # sihirbazda gösterilen kısa gerekçe


class CaseIntakeArbitration(BaseModel):
    kararlar: list[ArbiterDecision] = []


# --- Merge endpoint istek şemaları (Faz 3) ---


class MergeDocumentIn(BaseModel):
    process_id: str
    filename: str
    # /analyze terminal olayındaki data aynen geri gelir — alan seti motora
    # bağlı evrildiğinden serbest şekilli tutulur (merge servisi toleranslı okur)
    extraction: dict


class CaseIntakeMergeRequest(BaseModel):
    documents: list[MergeDocumentIn] = Field(..., min_length=1, max_length=15)


class KeepaliveRequest(BaseModel):
    process_ids: list[str] = Field(..., min_length=1, max_length=50)


# --- Commit endpoint şemaları (Faz 4) ---
# Sihirbazın "Kaydet ve Arşivle" düğmesi: kullanıcı onaylı dava kartı +
# PROCESS_CACHE'teki belgeler + review'da onaylanan poliçeler tek istekte gelir.


class CommitDocumentIn(BaseModel):
    process_id: str
    new_filename: str
    # HAM arşiv adı için orijinal dosya adı (merge documents[].filename);
    # verilmezse new_filename kullanılır (confirm'deki fallback deseni).
    original_filename: Optional[str] = None
    belge_turu_kodu: Optional[str] = None
    ai_ozet: Optional[str] = None
    esas_no: Optional[str] = None
    muvekkil_adi: Optional[str] = None


class CommitPolicyIn(ClientPolicyCreate):
    # Yalnız client_id'si dolu, kullanıcı onaylı poliçeler gönderilir
    # (merge çıktısında saved=true olanları frontend hiç göndermez).
    client_id: int


class CommitOptions(BaseModel):
    send_email: bool = False  # karar 2: varsayılan KAPALI
    # Alıcı listesi (Faz 4 devir notu b): boş + send_email=true → e-posta
    # pre-check "Alıcı listesi boş" ile zarifçe düşer, belge durumu etkilenmez.
    email_to: list[str] = Field(default_factory=list, max_length=10)


class CaseIntakeCommitRequest(BaseModel):
    case: CaseCreate
    documents: list[CommitDocumentIn] = Field(default_factory=list, max_length=15)
    policies: list[CommitPolicyIn] = Field(default_factory=list, max_length=30)
    options: CommitOptions = Field(default_factory=CommitOptions)
