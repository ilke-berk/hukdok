import re
import unicodedata

def turkish_upper(text: str) -> str:
    """
    Türkçe karakter destekli büyük harfe çevirme fonksiyonu.
    Python'un standart .upper() metodu 'i' harfini 'I' yapar, 'İ' yapmaz.
    """
    if not text:
        return ""
    
    # Sıralama önemli: önce i -> İ dönüşümü yapılır
    table = str.maketrans({
        "i": "İ",
        "ı": "I",
        "ğ": "Ğ",
        "ü": "Ü",
        "ş": "Ş",
        "ö": "Ö",
        "ç": "Ç",
        # Düzeltme işaretli harfler (büyük harf karşılıkları)
        "â": "Â", "î": "Î", "û": "Û"
    })
    return text.translate(table).upper()

def slugify(text: str) -> str:
    """
    Metni URL/Dosya adı/Kod dostu hale getirir.
    Türkçe karakterleri güvenli ASCII karşılıklarına çevirir.
    Örnek: "Dava Konusu: İtiraz" -> "DAVA_KONUSU_ITIRAZ"
    """
    if not text:
        return ""

    # 1. Önce Düzgün Büyük Harfe Çevir
    text = turkish_upper(text)
    
    # 2. Türkçe Karakterleri ASCII'ye Çevir (Mapping)
    # Database code generasyonu için I/İ ayrımı önemli olabilir ama
    # genelde slugify işleminde hepsi ASCII'ye indirgenir.
    replacements = {
        "İ": "I", "I": "I",
        "Ğ": "G",
        "Ü": "U",
        "Ş": "S",
        "Ö": "O",
        "Ç": "C",
        "Â": "A", "Î": "I", "Û": "U"
    }
    
    for origin, target in replacements.items():
        text = text.replace(origin, target)

    # 3. İzin verilmeyen karakterleri alt çizgi yap
    # Sadece A-Z, 0-9 kalacak
    text = re.sub(r'[^A-Z0-9]', '_', text)
    
    # 4. Tekrarlayan alt çizgileri temizle
    text = re.sub(r'_+', '_', text)
    
    # 5. Baştaki ve sondaki alt çizgileri at
    return text.strip('_')

def sanitize_filename_text(text: str) -> str:
    """
    Dosya isimleri için güvenli metin temizleme.
    Türkçe karakterleri KORUR, sadece dosya sistemi için güvensiz karakterleri temizler.
    """
    # 1. Path traversal ve null karakterleri temizle
    text = text.replace('\x00', '')
    
    # 2. Güvenli karakterler (Türkçe dahil)
    # Şapkalı harfler de eklendi: âîûÂÎÛ
    safe_pattern = re.compile(r'[^a-zA-ZğüşıöçĞÜŞİÖÇâîûÂÎÛ0-9._\-() ]')
    text = safe_pattern.sub('_', text)
    
    # 3. Fazla boşluk ve alt çizgileri düzelt
    # NOT: '_' ve '.' ayrı tutulmalı — "KARARI_.pdf" gibi dosya adlarında
    # '_.' kombinasyonu [_.]{2,} regex'iyle eşleşir ve nokta silinerek uzantı kaybolur!
    text = re.sub(r'_+', '_', text)   # Ardışık alt çizgiler → tek alt çizgi
    text = re.sub(r'\.+', '.', text)  # Ardışık noktalar → tek nokta
    return text.strip()
