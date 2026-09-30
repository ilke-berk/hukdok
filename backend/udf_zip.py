"""Dizin kaydı (central directory) eksik UDF arşivleri için sıralı okuma.

UYAP'tan gelen bazı .udf dosyalarında girişler (content.xml, sign.sgn) eksiksizdir
ama arşivin sonundaki dizin kaydı hiç yazılmamıştır (30.09.2026 prod olayı: dosya
son girişin data descriptor'ında bitiyordu). `zipfile` dizini sondan okuduğu için
böyle dosyayı BadZipFile ile reddeder. Buradaki okuyucu yerel giriş başlıklarını
baştan sırayla yürür; yalnız `zipfile` başarısız olduğunda YEDEK yol olarak çağrılır.

Dosya DEĞİŞTİRİLMEZ/onarılmaz: ham dosya arşive UYAP'tan geldiği haliyle gider.
"""
import struct
import zlib
from typing import Optional

_LOCAL_HEADER_SIG = b"PK\x03\x04"
_DATA_DESCRIPTOR_SIG = b"PK\x07\x08"
_LOCAL_HEADER = struct.Struct("<IHHHHHIIIHH")

_FLAG_ENCRYPTED = 0x1
_FLAG_DATA_DESCRIPTOR = 0x8
_METHOD_STORED = 0
_METHOD_DEFLATED = 8

# Tek girişin açılmış boyut tavanı (zip bombasına karşı).
MAX_ENTRY_BYTES = 100 * 1024 * 1024


def read_entry_sequential(file_path: str, entry_name: str = "content.xml") -> Optional[bytes]:
    """`entry_name` girişini yerel başlıkları sırayla okuyarak döndürür.

    Giriş bulunamazsa, arşiv o girişe kadar tutarlı yürünemezse ya da CRC
    tutmazsa None döner (istisna fırlatmaz) — çağıran dosyayı bozuk sayar.
    """
    try:
        with open(file_path, "rb") as f:
            data = f.read()
    except OSError:
        return None

    pos = 0
    while data[pos:pos + 4] == _LOCAL_HEADER_SIG and pos + _LOCAL_HEADER.size <= len(data):
        (_sig, _ver, flags, method, _time, _date, crc, csize, _usize,
         name_len, extra_len) = _LOCAL_HEADER.unpack_from(data, pos)
        name_start = pos + _LOCAL_HEADER.size
        name = data[name_start:name_start + name_len].decode("utf-8", errors="replace")
        body_start = name_start + name_len + extra_len
        has_descriptor = bool(flags & _FLAG_DATA_DESCRIPTOR)

        if flags & _FLAG_ENCRYPTED:
            return None

        if method == _METHOD_DEFLATED:
            # Deflate akışı kendi sonunu bildirir; descriptor'lı girişte başlıktaki
            # csize 0 olduğundan tüketilen bayt sayısı buradan öğrenilir.
            decomp = zlib.decompressobj(-15)
            try:
                content = decomp.decompress(data[body_start:], MAX_ENTRY_BYTES)
            except zlib.error:
                return None
            if not decomp.eof:
                return None  # yarıda kesilmiş akış ya da tavan aşımı
            body_end = len(data) - len(decomp.unused_data)
        elif method == _METHOD_STORED and not has_descriptor:
            body_end = body_start + csize
            if body_end > len(data) or csize > MAX_ENTRY_BYTES:
                return None
            content = data[body_start:body_end]
        else:
            return None

        pos = body_end
        if has_descriptor:
            if data[pos:pos + 4] == _DATA_DESCRIPTOR_SIG:
                pos += 4
            if pos + 12 > len(data):
                return None
            (crc,) = struct.unpack_from("<I", data, pos)
            pos += 12

        if zlib.crc32(content) != crc:
            return None
        if name == entry_name:
            return content

    return None
