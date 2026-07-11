"""Modüller arası paylaşılan sabitler.

Duruşma tarihi zinciri (analyzer → prompts → document_pipeline → frontend)
aynı belge türü filtresini kullanır; liste tek yerden yönetilir ki yeni bir
tür eklenince üç kopyadan biri unutulmasın.
"""
from typing import Optional

# Sonraki duruşma tarihi taşıyabilen belge türü kod parçaları.
# Kodlar '_' ile pad'li gelebilir (örn. "TEBLIGAT______"); contains kontrolü
# yapıldığı için padding sorun olmaz. "TEBLIG" hem TEBLIGAT hem TEBLIG'i kapsar.
HEARING_DOCTYPE_KEYWORDS = ("DURUSMA", "ZABIT", "TUTANAK", "TENSIP", "TEBLIG")


def is_hearing_doctype(code: Optional[str]) -> bool:
    """Belge türü kodu duruşma tarihi çıkarımı yapılacak türlerden mi?"""
    c = (code or "").upper()
    return any(kw in c for kw in HEARING_DOCTYPE_KEYWORDS)
