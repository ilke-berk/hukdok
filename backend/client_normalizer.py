import json
import re
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ClientNormalizer")

# --- PRE-COMPILED REGEX PATTERNS (PERFORMANCE OPTIMIZATION) ---
# Titles to remove (DR, AV, UZM, DOÇ, PROF - with or without dot)
# \b boundary ensures we don't match inside words, IGNORECASE handle capitalization
PRE_COMPILED_TITLE_PATTERNS = [
    re.compile(r'\bDR\.?', re.IGNORECASE),
    re.compile(r'\bAV\.?', re.IGNORECASE),
    re.compile(r'\bUZM\.?', re.IGNORECASE),
    re.compile(r'\bDOÇ\.?', re.IGNORECASE),
    re.compile(r'\bPROF\.?', re.IGNORECASE)
]

# Split delimiters: ; | - | / | ve
# Compiled once for speed in massive loops
PRE_COMPILED_SPLIT_PATTERN = re.compile(r';| - | / | ve ')

def turkish_upper(text):
    """Turkish specific uppercase conversion"""
    if not text:
        return ""
    table = str.maketrans({
        "i": "İ",
        "ı": "I",
        "ğ": "Ğ",
        "ü": "Ü",
        "ş": "Ş",
        "ö": "Ö",
        "ç": "Ç"
    })
    return text.translate(table).upper()

def clean_name(name):
    """
    Cleans the client name:
    1. Upper case
    2. Remove DR., AV. etc. (Using pre-compiled regex)
    3. Remove extra spaces
    """
    if not name:
        return ""
    
    # Turkish Upper
    cleaned = turkish_upper(name)
    
    # Remove Titles (Using pre-compiled patterns)
    for pat in PRE_COMPILED_TITLE_PATTERNS:
        cleaned = pat.sub('', cleaned)
        
    # Remove specific header "AD SOYAD / UNVAN" if it exists as a value
    if "AD SOYAD" in cleaned and "UNVAN" in cleaned:
        return None

    # Strip and cleanup spaces and trailing punctuation
    cleaned = cleaned.replace(";", "").replace(":", "") # Remove residual punctuation
    cleaned = " ".join(cleaned.split())
    cleaned = cleaned.strip(" .") # Remove trailing dots
    
    return cleaned if len(cleaned) > 2 else None # Filter out very short artifacts

def process_client_list():
    from pathlib import Path
    import sys
    import shutil

    # Determine paths
    app_data_dir = Path.home() / "AppData" / "Local" / "HukuDok" / "data"
    app_data_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Input Path (muvekkil_listesi.json) - Check AppData first, then Bundled
    input_path = app_data_dir / "muvekkil_listesi.json"
    
    if not input_path.exists():
        # Fallback to bundled
        if getattr(sys, 'frozen', False):
            bundled_path = Path(sys.executable).parent / "data" / "muvekkil_listesi.json"
        else:
            bundled_path = Path(__file__).resolve().parent / "data" / "muvekkil_listesi.json"
            
        if bundled_path.exists():
            logger.info(f"Input not in AppData, using bundled: {bundled_path}")
            input_path = bundled_path
    
    # 2. Output Path (normalized_client_list.json) - ALWAYS AppData
    output_path = app_data_dir / "normalized_client_list.json"
    
    logger.info(f"Reading from: {input_path}")
    
    if not input_path.exists():
        logger.error("Error: Input file not found!")
        return
        
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    raw_list = data.get("muvekiller", [])
    logger.info(f"Total raw entries: {len(raw_list)}")
    
    # Enhanced structure: normalized_name -> {raw_variants, count, source_ids}
    normalized_map = {}
    
    for raw_entry in raw_list:
        # Handle both old format (string) and new format (dict)
        if isinstance(raw_entry, dict):
            source_id = raw_entry.get("id", "unknown")
            raw_text = raw_entry.get("name", "")
        else:
            # Backward compatibility: old format was just a string
            source_id = "legacy"
            raw_text = raw_entry
        
        if not raw_text:
            continue
            
        # Split logic (Using Pre-Compiled Pattern)
        parts = PRE_COMPILED_SPLIT_PATTERN.split(raw_text)
        
        for part in parts:
            cleaned = clean_name(part)
            if cleaned:
                # Initialize structure if needed
                if cleaned not in normalized_map:
                    normalized_map[cleaned] = {
                        "raw_variants": [],
                        "source_ids": [],
                        "count": 0
                    }
                
                # Add raw variant (avoid duplicates)
                if raw_text not in normalized_map[cleaned]["raw_variants"]:
                    normalized_map[cleaned]["raw_variants"].append(raw_text)
                
                # Add source ID (avoid duplicates)
                if source_id not in normalized_map[cleaned]["source_ids"]:
                    normalized_map[cleaned]["source_ids"].append(source_id)
                
                # Update count
                normalized_map[cleaned]["count"] = len(normalized_map[cleaned]["raw_variants"])
    
    # Output structure
    output_data = {
        "metadata": {
            "source": "client_normalizer.py",
            "original_count": len(raw_list),
            "normalized_count": len(normalized_map),
            "description": "Enhanced structure with metadata for collision detection"
        },
        "clients": normalized_map
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
        
    logger.info("✅ Processing complete.")
    logger.info(f"Normalized entries: {len(normalized_map)}")
    logger.info(f"Saved to: {output_path}")

    # Check verification example
    test_names = ["VAHAP DÖŞ", "NİHAN HİLAL HOŞAĞASI"]
    logger.info("--- Verification ---")
    for name in test_names:
        name_clean = clean_name(name)
        if name_clean in normalized_map:
            entry = normalized_map[name_clean]
            logger.info(f"FOUND: '{name}' -> Variants: {entry['raw_variants'][:3]}, Count: {entry['count']}, IDs: {entry['source_ids'][:3]}")
        else:
            logger.info(f"NOT FOUND: '{name}' (Cleaned: '{name_clean}')")

if __name__ == "__main__":
    process_client_list()
