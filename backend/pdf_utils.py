import fitz
import re
import logging

# Configure Logging for standalone testing
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


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
