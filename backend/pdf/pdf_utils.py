import os
import tempfile
import fitz
import re
import logging

# Configure Logging for standalone testing
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


MAX_PDF_PAGES = 500


def load_and_analyze_pdf(pdf_path):
    """
    Opens PDF, extracts text, and simultaneously checks for scanned/hybrid content.
    Optimized to do a single pass over the file.

    Returns:
        (needs_ocr: bool, extracted_text: str|None, reason: str)
    """
    try:
        doc = fitz.open(pdf_path)
        full_text = []
        is_hybrid_detected = False
        garbage_detected = False
        total_text_len = 0

        total_pages = len(doc)
        if total_pages == 0:
            return True, None, "EMPTY_FILE"

        if total_pages > MAX_PDF_PAGES:
            doc.close()
            logging.warning(f"PDF rejected: {total_pages} pages exceeds limit of {MAX_PDF_PAGES}")
            raise ValueError(f"PDF çok fazla sayfa içeriyor: {total_pages}. Maksimum {MAX_PDF_PAGES} sayfa.")

        logging.info(f"Processing PDF: {pdf_path} ({total_pages} pages)")

        for page_num, page in enumerate(doc):
            # Extract text
            text = page.get_text()
            full_text.append(text)

            # Update metrics
            text_len = len(text.strip())
            total_text_len += text_len

            # --- 1. Hybrid Check (Image rich, text poor) ---
            # Optimization: Only check images if text is suspiciously low
            if text_len < 100:
                images = page.get_images()
                num_images = len(images)

                if num_images > 0:
                    logging.info(
                        f"Page {page_num+1}: Potential Hybrid/Image detected (Text: {text_len} chars, Images: {num_images})."
                    )
                    is_hybrid_detected = True

            # --- 2. Encoding / Mojibake Check ---
            # Check for common encoding artifacts
            # Optimization: Check only if we haven't found garbage yet
            if not garbage_detected:
                # Escape special chars like ? to avoid regex errors (e.g., Å? matching empty string)
                mojibake_patterns = [r"Ã¼", r"ÅŸ", r"Ä°", r"Ã§", r"Å\?", r"Ã¶", r"ÄŸ"]
                for pattern in mojibake_patterns:
                    if re.search(pattern, text):
                        logging.warning(
                            f"Page {page_num+1}: Encoding artifact detected ('{pattern}')."
                        )
                        garbage_detected = True
                        break

            # Early Exit: If we found both issues, we can technically stop analyzing for 'reasons'
            # but we continue to collect 'full_text' in case we can use it as fallback.

        doc.close()

        # Combine text
        combined_text = "\n".join(full_text)

        # Decision Logic
        if is_hybrid_detected:
            # Even if hybrid, we return the text we found.
            # The caller (analyzer) can decide to use it if it looks coherent, or use OCR.
            return True, combined_text, "HYBRID_CONTENT"

        if garbage_detected:
            return True, combined_text, "ENCODING_ERROR"

        # Final empty check
        if total_text_len < 50:
            return True, None, "INSUFFICIENT_TEXT"

        # Success path
        return False, combined_text, "CLEAN_TEXT"

    except Exception as e:
        logging.error(f"PDF Analysis Error: {e}")
        return True, None, f"ERROR: {e}"


BLANK_PAGE_CHAR_THRESHOLD = 200  # Bu karakterden azsa metin yetersiz sayılır


def _is_blank_page(doc, page_idx: int) -> bool:
    """
    Sayfanın anlamlı içerik taşıyıp taşımadığını kontrol eder.
    İki adımlı: önce metin, yetmezse görsel içerik.

    - Metin >= eşik → boş değil (normal PDF)
    - Metin < eşik ama sayfa resim içeriyor → boş değil (taranmış PDF)
    - Metin < eşik ve resim yok → boş sayfa
    """
    page = doc[page_idx]
    text = page.get_text().strip()
    if len(text) >= BLANK_PAGE_CHAR_THRESHOLD:
        return False
    # Metin yetersiz — taranmış PDF olabilir, görsel varlığını kontrol et
    return len(page.get_images()) == 0


def _find_non_blank(doc, start_idx: int, direction: int, min_idx: int, max_idx: int) -> int:
    """
    start_idx'ten başlayarak direction (+1 ileri, -1 geri) yönünde
    boş olmayan ilk sayfanın indeksini döner.
    Hepsi boşsa start_idx'i döner (en kötü durum fallback).
    """
    idx = start_idx
    while min_idx <= idx <= max_idx:
        if not _is_blank_page(doc, idx):
            return idx
        idx += direction
    return start_idx  # fallback: hepsi boştu


def extract_key_pages(pdf_path: str) -> str:
    """
    Uzun PDF'lerden ilk 2 ve son anlamlı sayfayı çıkarır, yeni bir temp PDF döner.
    Sayfa sayısı <= 3 ise orijinal yolu döner (kopyalamaz, disk yazmaz).

    Seçilen sayfalardan biri aşırı boşsa komşu sayfaya kayar:
      - İlk sayfa (0) boşsa → sonraki sayfaya ilerler
      - İkinci sayfa (1) boşsa → sonraki sayfaya ilerler
      - Son sayfa boşsa → bir önceki sayfaya geri gider

    Returns:
        Kullanılacak PDF'nin yolu — orijinal veya yeni temp dosya.
    """
    doc = fitz.open(pdf_path)
    total = len(doc)

    if total <= 3:
        doc.close()
        return pdf_path

    last = total - 1

    # Her pozisyon için boşluk kontrolü ve kayma
    p0 = _find_non_blank(doc, 0,    +1, 0, last)      # 1. sayfa: ileri kay
    p1 = _find_non_blank(doc, 1,    +1, 0, last)      # 2. sayfa: ileri kay
    p_last = _find_non_blank(doc, last, -1, 0, last)  # Son sayfa: geri kay

    pages_to_keep = sorted({p0, p1, p_last})

    logging.info(
        f"extract_key_pages: {total} sayfa, secilen indeksler: {pages_to_keep} "
        f"(p0={p0}, p1={p1}, son={p_last})"
    )

    new_doc = fitz.open()
    for p in pages_to_keep:
        new_doc.insert_pdf(doc, from_page=p, to_page=p)
    doc.close()

    fd, output_path = tempfile.mkstemp(suffix="_trimmed.pdf")
    os.close(fd)
    new_doc.save(output_path)
    new_doc.close()

    return output_path
