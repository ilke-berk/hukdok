import os
import json
import sys

# Force UTF-8 (Fix for Windows)
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import logging
from dotenv import load_dotenv
import google.generativeai as genai
from typing import List, Dict, Optional, Tuple, Any, AsyncGenerator


# --- LOGGER IMPORT ---
try:
    from log_manager import TechnicalLogger
except ImportError:
    # Fallback if logger missing
    class MockTechnicalLogger:
        @staticmethod
        def log(*args, **kwargs):
            logging.info(f"[MockLog] {args} {kwargs}")

    TechnicalLogger = MockTechnicalLogger

# Configure Logging (Standard logging for console fallback)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Load Environment Variables
from pathlib import Path
import uuid  # For error masking
import vault  # Import Vault
import hashlib
import time  # Benchmark için

if getattr(sys, 'frozen', False):
    # PyInstaller EXE: .env is in the same folder as the executable
    env_path = Path(sys.executable).parent / ".env"
else:
    # Dev Mode: .env is in the project root (parent of backend)
    env_path = Path(__file__).resolve().parent.parent / ".env"

load_dotenv(dotenv_path=env_path, override=True)
GOOGLE_API_KEY = vault.get_secret("GEMINI_API_KEY")  # Use Vault

# Kullanıcının .env dosyasından modeli almaya zorluyoruz.
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME")

if not GEMINI_MODEL_NAME:
    TechnicalLogger.log("ERROR", "GEMINI_MODEL_NAME environment variable is NOT set.")
    raise ValueError(
        "HATA: GEMINI_MODEL_NAME çevresel değişkeni bulunamadı! Lütfen .env dosyasını kontrol edin."
    )

if not GOOGLE_API_KEY:
    TechnicalLogger.log("ERROR", "GEMINI_API_KEY not found in .env file.")

# Configure Gemini
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

# --- SYSTEM INSTRUCTION ---
# --- PROMPT IMPORT ---
try:
    from prompts import get_system_instruction
except ImportError:
    TechnicalLogger.log("ERROR", "prompts.py not found. Using fallback.")

    def get_system_instruction(l=None):
        return "ERROR"


# Import local pdf_utils
try:
    import pdf_utils
except ImportError:
    try:
        from . import pdf_utils
    except ImportError:
        TechnicalLogger.log(
            "WARNING", "pdf_utils not found. Conditional OCR might fail."
        )

        pdf_utils = None

# --- DYNAMIC CONFIG ---
from config_manager import DynamicConfig

# ---HİBRİT MÜVEKKİL MATCHER ---
from muvekkil_matcher_v2 import get_hibrid_matcher
# --- LIST SEARCHER ---
from list_searcher import get_list_searcher


def fix_mojibake(text: str) -> str:
    """
    Common Turkish mojibake replacements.
    """
    config = DynamicConfig.get_instance()
    # If get_mojibake_map isn't ready yet, fallback to empty or basic
    replacements = getattr(config, "get_mojibake_map", lambda: {})()

    if not replacements:
        return text

    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def is_scanned_pdf(pdf_path: str) -> Tuple[bool, Optional[str]]:
    """
    Checks if a PDF requires OCR using advanced Hybrid/Garbage checks via pdf_utils.
    Returns: (needs_ocr: bool, extracted_text: str|None)
    """
    if not pdf_utils:
        TechnicalLogger.log("WARNING", "PDF Utils missing, forcing OCR mode.")
        return True, None

    needs_ocr, text, reason = pdf_utils.load_and_analyze_pdf(pdf_path)

    if needs_ocr:
        if reason == "ENCODING_ERROR" and text:
            # Attempt to fix mojibake
            cleaned_text = fix_mojibake(text)
            TechnicalLogger.log(
                "INFO",
                f"Mojibake Detected ({reason}). Attempting repair...",
                {"file": pdf_path},
            )
            return False, cleaned_text

        TechnicalLogger.log(
            "INFO", f"PDF Analysis: OCR Required", {"file": pdf_path, "reason": reason}
        )
        return True, None
    else:
        TechnicalLogger.log(
            "INFO",
            "PDF Analysis: Digital text detected. Using Text mode.",
            {"file": pdf_path},
        )
        return False, text


def upload_to_gemini(path: str, mime_type: str = "application/pdf") -> Any:
    """
    Uploads the given file to Gemini.
    """
    file = genai.upload_file(path, mime_type=mime_type)
    TechnicalLogger.log(
        "INFO",
        f"Uploaded file to Gemini",
        {"display_name": file.display_name, "uri": file.uri},
    )
    return file


import asyncio


async def wait_for_files_active(files: List[Any]) -> None:
    """
    Waits for the uploaded files to be processed and active.
    """
    logging.info("Waiting for file processing...")
    for name in (file.name for file in files):
        file = genai.get_file(name)
        while file.state.name == "PROCESSING":
            await asyncio.sleep(1)
            file = genai.get_file(name)
        if file.state.name != "ACTIVE":
            error_msg = f"File {file.name} failed to process state: {file.state.name}"
            TechnicalLogger.log("ERROR", error_msg)
            raise Exception(error_msg)
    logging.info("...File is ready for processing.")


def calculate_file_hash(file_path: str) -> str:
    """Calculates SHA256 hash of the file."""
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        TechnicalLogger.log("ERROR", f"Hash calculation failed: {e}")
        return "HASH_CALCULATION_FAILED"


def get_default_json() -> Dict[str, Any]:
    """Returns a default JSON structure in case of failure."""
    return {
        "tarih": datetime.now().strftime("%Y-%m-%d"),
        "muvekkiller": [],
        "muvekkil_adi": "",
        "karsi_taraf": "", # Yeni alan
        "belgede_gecen_isimler": [],
        "belge_turu_kodu": "",
        "belge_kaynagi": "XXXX",
        "avukat_kodu": "XXX",
        "esas_no": "",
        "durum": "G",
        "ozet": "Analysis Failed",
    }


# --- CACHE MECHANISM (SQLite) ---
from db_manager import DatabaseManager


async def analyze_file_generator(
    file_path: str,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Generator that yields status updates and finally the result.
    Yields: {"status": "info"/"error"/"complete", "message": "...", "data": dict}
    """


    # ⏱️ BENCHMARK: Zamanlama başlat
    benchmark = {}
    total_start = time.perf_counter()
    
    # 0. Initial Hash Calculation (Async)
    t0 = time.perf_counter()
    loop = asyncio.get_running_loop()
    file_hash = await loop.run_in_executor(None, calculate_file_hash, file_path)
    benchmark["hash_calculation"] = round((time.perf_counter() - t0) * 1000, 2)

    # Note: Cache logic removed for clarity as it was disabled.

    if not GOOGLE_API_KEY:
        TechnicalLogger.log(
            "WARNING", "Skipping analysis because GEMINI_API_KEY is missing."
        )
        default_data = get_default_json()
        default_data["hash"] = file_hash
        yield {"status": "complete", "data": default_data}
        return

    if not os.path.exists(file_path):
        TechnicalLogger.log("WARNING", f"File vanished before processing: {file_path}")
        default_data = get_default_json()
        default_data["hash"] = file_hash
        yield {"status": "complete", "data": default_data}
        return

    # 1. Check if file is UDF format - convert to PDF first
    file_ext = Path(file_path).suffix.lower()
    temp_pdf_from_udf = None
    
    if file_ext == '.udf':
        yield {
            "status": "info",
            "message": "📄 UYAP UDF formatı tespit edildi, PDF'e dönüştürülüyor..."
        }
        try:
            from udf_converter import convert_udf_to_pdf
            
            # Convert UDF to temporary PDF
            temp_pdf_from_udf = await loop.run_in_executor(
                None, convert_udf_to_pdf, file_path, None
            )
            
            TechnicalLogger.log("INFO", f"UDF converted to PDF: {temp_pdf_from_udf}")
            
            # Now analyze the converted PDF instead
            file_path = temp_pdf_from_udf
            
            yield {
                "status": "info",
                "message": "✅ UDF dönüştürme tamamlandı, analiz başlıyor..."
            }
            
        except Exception as e:
            TechnicalLogger.log("ERROR", f"UDF conversion failed: {e}")
            default_data = get_default_json()
            default_data["hash"] = file_hash
            default_data["ozet"] = f"UDF dönüşüm hatası: {str(e)}"
            yield {"status": "complete", "data": default_data}
            return

    # 2. Decide Mode (Async wrapper for heavy pdf logic)
    t1 = time.perf_counter()
    needs_ocr, extracted_text = await loop.run_in_executor(
        None, is_scanned_pdf, file_path
    )
    benchmark["pdf_analysis"] = round((time.perf_counter() - t1) * 1000, 2)

    if needs_ocr:
        TechnicalLogger.log(
            "INFO",
            "Taranmış veya hibrit belge algılandı, OCR moduna geçiliyor...",
            {"file": file_path},
        )
        yield {
            "status": "info",
            "message": "Belge analizi derinleştiriliyor. Okuma moduna geçiliyor, işlem biraz sürebilir...",
        }
    else:
        TechnicalLogger.log(
            "INFO", "Hızlı Mod: Metin temiz ve yeterli seviyede.", {"file": file_path}
        )
        yield {
            "status": "info",
            "message": "✅ Metin algılandı. Hızlı analiz yapılıyor...",
        }

    uploaded_file = None
    try:
        # === PRE-EXTRACTION PHASE (Regex/List çıkarıcılar LLM'den önce) ===
        pre_extracted = {
            "tarih": None,
            "esas_no": None,
            "avukat_kodu": None,
            "muvekkil_candidates": []
        }
        
        t2 = time.perf_counter()  # Pre-extraction timer start
        if extracted_text and len(extracted_text) > 50:
            yield {"status": "info", "message": "Analiz yapılıyor..."}
            
            # 1. Tarih (Regex)
            try:
                from date_extractor import find_best_date
                pre_extracted["tarih"] = find_best_date(extracted_text)
                if pre_extracted["tarih"]:
                    TechnicalLogger.log("INFO", f"📅 [PRE] Tarih bulundu: {pre_extracted['tarih']}")
            except Exception as e:
                TechnicalLogger.log("WARNING", f"[PRE] Tarih çıkarımı hatası: {e}")
            
            # 2. Esas No (Regex)
            try:
                from esas_no_extractor import find_best_esas_no
                pre_extracted["esas_no"] = find_best_esas_no(extracted_text)
                if pre_extracted["esas_no"]:
                    TechnicalLogger.log("INFO", f"🔢 [PRE] Esas No bulundu: {pre_extracted['esas_no']}")
            except Exception as e:
                TechnicalLogger.log("WARNING", f"[PRE] Esas No çıkarımı hatası: {e}")
            
            # 3. Avukat (List/Regex)
            try:
                from lawyer_extractor import find_best_lawyer
                pre_extracted["avukat_kodu"] = find_best_lawyer(extracted_text)
                if pre_extracted["avukat_kodu"]:
                    TechnicalLogger.log("INFO", f"⚖️ [PRE] Avukat bulundu: {pre_extracted['avukat_kodu']}")
            except Exception as e:
                TechnicalLogger.log("WARNING", f"[PRE] Avukat çıkarımı hatası: {e}")
            
            # 4. Müvekkil Adayları (FlashText)
            try:
                searcher = get_list_searcher()
                pre_extracted["muvekkil_candidates"] = searcher.search(extracted_text)
                if pre_extracted["muvekkil_candidates"]:
                    TechnicalLogger.log("INFO", f"👤 [PRE] Müvekkil adayları: {pre_extracted['muvekkil_candidates']}", {"count": len(pre_extracted["muvekkil_candidates"])})
            except Exception as e:
                TechnicalLogger.log("WARNING", f"[PRE] Müvekkil arama hatası: {e}")
        
        # === MISSING FIELDS DETECTION ===
        missing_fields = []
        if not pre_extracted["tarih"]:
            missing_fields.append("tarih")
        if not pre_extracted["esas_no"]:
            missing_fields.append("esas_no")
        if not pre_extracted["avukat_kodu"]:
            missing_fields.append("avukat_kodu")
        if not pre_extracted["muvekkil_candidates"]:
            missing_fields.append("muvekkil")
        
        benchmark["pre_extraction"] = round((time.perf_counter() - t2) * 1000, 2)
        
        # Log what we found/missing
        TechnicalLogger.log("INFO", f"🎯 [PRE] Eksik alanlar: {missing_fields if missing_fields else 'YOK (Sadece özet istenecek)'}")
        
        # Promptu dinamik oluştur (Singleton Konfigürasyon Kullan)
        config = DynamicConfig.get_instance()
        lawyers = config.get_lawyers()
        statuses = config.get_statuses()
        doctypes = config.get_doctypes()

        # 🆕 YENİ: Dinamik prompt oluştur (eksik alanlar ve ön çıkarım bilgisi ile)
        sys_inst = get_system_instruction(
            dynamic_lawyers=lawyers,
            dynamic_doctypes=doctypes, 
            dynamic_statuses=statuses,
            candidates=pre_extracted["muvekkil_candidates"],
            missing_fields=missing_fields,
            pre_extracted=pre_extracted
        )

        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL_NAME, system_instruction=sys_inst
        )


        t3 = time.perf_counter()  # AI call timer start
        
        if needs_ocr:
            # --- OCR MODE ---
            TechnicalLogger.log("INFO", "MODE: OCR Activated")
            uploaded_file = upload_to_gemini(file_path)
            yield {"status": "info", "message": "⏳ Dosya işleniyor..."}
            await wait_for_files_active([uploaded_file])
            response = await model.generate_content_async([uploaded_file])
        else:
            # --- TEXT MODE ---
            TechnicalLogger.log("INFO", "MODE: TEXT Activated")

            # Validate text length again
            if extracted_text and len(extracted_text) < 50:
                # Fallback to OCR if text is suspiciously short (redundant check)
                TechnicalLogger.log(
                    "WARNING",
                    "Text too short, falling back to OCR",
                    {"len": len(extracted_text)},
                )
                uploaded_file = upload_to_gemini(file_path)
                response = await model.generate_content_async([uploaded_file])
            else:
                response = await model.generate_content_async(extracted_text)
        
        benchmark["ai_call"] = round((time.perf_counter() - t3) * 1000, 2)
        logging.info(f"GEMINI HAM CEVAP: {response.text}")

        # 3. Robust JSON Parsing (Brace Counting)
        def extract_first_json(text):
            text = text.strip()
            # Find first '{'
            start_idx = text.find("{")
            if start_idx == -1:
                return None

            balance = 0
            for i in range(start_idx, len(text)):
                char = text[i]
                if char == "{":
                    balance += 1
                elif char == "}":
                    balance -= 1

                if balance == 0:
                    return text[start_idx : i + 1]
            return None

        result_text = response.text
        # Optional Cleanup
        cleaned_text = result_text.replace("```json", "").replace("```", "")

        json_str = extract_first_json(cleaned_text)

        if json_str:
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                # Fallback: Try raw text if extraction failed logically but structure exists
                data = json.loads(cleaned_text)
        else:
            # No JSON found by key, try raw (risky but fallback)
            data = json.loads(cleaned_text)

        # 4. Hash'i sonuca ekle
        data["hash"] = file_hash
        
        debug_info = []

        # 🛡️ HARD OVERRIDE: Belge Türü Seçimini Kullanıcıya Bırak
        data["belge_turu_kodu"] = ""
        debug_info.append("- Belge Türü: Kullanıcıya Bırakıldı")
        
        # 🛡️ HARD OVERRIDE: Karşı Taraf Seçimini Kullanıcıya Bırak
        data["karsi_taraf"] = ""
        debug_info.append("- Karşı Taraf: Kullanıcıya Bırakıldı")

        # === POST-PROCESSING: Pre-Extracted Değerleri Uygula ===
        # Artık regex'leri tekrar çalıştırmıyoruz, pre-extraction'daki sonuçları kullan
        
        # 📅 TARİH
        if pre_extracted.get("tarih"):
            data["tarih"] = pre_extracted["tarih"]
            debug_info.append(f"- Tarih: REGEX ({pre_extracted['tarih']})")
        else:
            # LLM'nin bulduğu değer kalır
            debug_info.append(f"- Tarih: LLM ({data.get('tarih', 'BOŞ')})")
        
        # 🔢 ESAS NO
        if pre_extracted.get("esas_no"):
            data["esas_no"] = pre_extracted["esas_no"]
            debug_info.append(f"- Esas No: REGEX ({pre_extracted['esas_no']})")
        else:
            # LLM'nin bulduğu değer kalır
            debug_info.append(f"- Esas No: LLM ({data.get('esas_no', 'BOŞ')})")
        
        # ⚖️ AVUKAT
        if pre_extracted.get("avukat_kodu"):
            data["avukat_kodu"] = pre_extracted["avukat_kodu"]
            debug_info.append(f"- Avukat: REGEX/LİSTE ({pre_extracted['avukat_kodu']})")
        else:
            # LLM'nin bulduğu değer kalır
            debug_info.append(f"- Avukat: LLM ({data.get('avukat_kodu', 'BOŞ')})")

        # 👤 MÜVEKKİL (Hibrit Matcher hala gerekli)
        try:
            hook_muvekkil = data.get("muvekkil_adi")
            diger_isimler = data.get("belgede_gecen_isimler", [])
            avukat_var = data.get("avukat_kodu") is not None
            
            # 🛡️ AVUKAT FİLTRESİ: Müvekkil adaylarından avukatları çıkar
            lawyer_names_upper = set()
            for lawyer in lawyers:
                name = lawyer.get("name", "")
                if name:
                    # Hem tam ismi hem de parçalarını ekle
                    lawyer_names_upper.add(name.upper())
                    # Örn: "AYŞE GÜL HANYALOĞLU" için "AYŞE", "GÜL", "HANYALOĞLU" da ekle
                    for part in name.upper().split():
                        if len(part) > 3:  # Sadece anlamlı parçalar
                            lawyer_names_upper.add(part)
            
            # Hook müvekkil avukat mı?
            if hook_muvekkil and hook_muvekkil.upper() in lawyer_names_upper:
                TechnicalLogger.log("WARNING", f"⚠️ AVUKAT FİLTRE: '{hook_muvekkil}' avukat olarak tespit edildi, müvekkil olarak kullanılmayacak!")
                hook_muvekkil = None
            
            # Diğer isimlerden avukatları çıkar
            filtered_isimler = []
            for isim in diger_isimler:
                isim_upper = isim.upper() if isim else ""
                is_lawyer = False
                for lawyer_name in lawyer_names_upper:
                    if lawyer_name in isim_upper or isim_upper in lawyer_name:
                        is_lawyer = True
                        break
                if not is_lawyer:
                    filtered_isimler.append(isim)
            
            # Güncellenmiş listeyi kaydet (GEÇİCİ - Aşağıda tekrar filtrelenecek)
            data["belgede_gecen_isimler"] = filtered_isimler
            
            matcher = get_hibrid_matcher()
            sonuc, kaynak, skor = matcher.filtrele(
                hook_tespit=hook_muvekkil,
                diger_isimler=filtered_isimler,
                avukat_var=avukat_var
            )
            
            # Sonucu güncelle
            data["muvekkil_adi"] = sonuc
            data["muvekkil_kaynak"] = kaynak  # Debug için
            data["muvekkil_benzerlik"] = round(skor, 1) if skor > 0 else 0
            
            # 🆕 MÜVEKKİLLER LİSTESİ FİLTRELEMESİ (SIKI MOD)
            # SADECE pre_extracted["muvekkil_candidates"] içindeki isimler kabul edilir
            raw_muvekkiller = data.get("muvekkiller", [])
            validated_muvekkiller = []
            
            # Pre-extraction candidates'ı set olarak al (hızlı lookup için)
            pre_cand_upper = set()
            pre_cand_map = {}  # upper -> original
            if pre_extracted.get("muvekkil_candidates"):
                for cand in pre_extracted["muvekkil_candidates"]:
                    cand_upper = cand.upper().replace("İ", "I")
                    pre_cand_upper.add(cand_upper)
                    pre_cand_map[cand_upper] = cand
            
            for muv in raw_muvekkiller:
                if not muv:
                    continue
                muv_upper = muv.upper().replace("İ", "I")
                
                # Avukat mı?
                is_lawyer = False
                for lawyer_name in lawyer_names_upper:
                    if lawyer_name in muv_upper or muv_upper in lawyer_name:
                        is_lawyer = True
                        break
                
                if is_lawyer:
                    TechnicalLogger.log("INFO", f"⚠️ Müvekkil listesinden avukat çıkarıldı: {muv}")
                    continue
                
                # 🛡️ SIKI FİLTRE: Sadece SharePoint listesindekiler kabul edilir
                if muv_upper in pre_cand_upper:
                    # Standart ismi kullan (SharePoint'teki haliyle)
                    validated_muvekkiller.append(pre_cand_map[muv_upper])
                else:
                    # Listede yok - "Diğer İsimler"e bırak, müvekkillere ekleme
                    TechnicalLogger.log("INFO", f"ℹ️ Müvekkil listesinde yok, atlandı: {muv}")
            
            # Pre-extraction'da bulunan ama LLM'nin muvekkiller'inde olmayan adayları da ekle
            for cand in pre_extracted.get("muvekkil_candidates", []):
                cand_upper = cand.upper().replace("İ", "I")
                if cand_upper not in {m.upper().replace("İ", "I") for m in validated_muvekkiller}:
                    validated_muvekkiller.append(cand)
            

            
            # Duplicate temizle (sıra koruyarak)
            seen = set()
            unique_muvekkiller = []
            for m in validated_muvekkiller:
                m_key = m.upper().replace("İ", "I")
                if m_key not in seen:
                    seen.add(m_key)
                    unique_muvekkiller.append(m)
            
            data["muvekkiller"] = unique_muvekkiller
            
            # 🆕 İLK ELEMANI ANA MÜVEKKİL YAP
            if unique_muvekkiller and not data.get("muvekkil_adi"):
                data["muvekkil_adi"] = unique_muvekkiller[0]
                TechnicalLogger.log("INFO", f"📌 Ana müvekkil listeden atandı: {unique_muvekkiller[0]}")
            
            # Pre-extraction'da aday bulunduysa belirt
            if pre_extracted.get("muvekkil_candidates"):
                debug_info.append(f"- Müvekkil: HİBRİT [Pre-Adaylar: {len(pre_extracted['muvekkil_candidates'])}] → {data.get('muvekkil_adi')} ({kaynak})")
            else:
                debug_info.append(f"- Müvekkil: HİBRİT (Aday Yok) → {data.get('muvekkil_adi')} ({kaynak})")
            
            debug_info.append(f"- Müvekkil Listesi: {len(unique_muvekkiller)} kişi (Avukatlar ve duplikasyonlar çıkarıldı)")
            
            # 🆕 SON TEMİZLİK: Müvekkiller listesinde olanları "belgede_gecen_isimler"den çıkar
            # Böylece dropdown'da duplicate görünmez.
            final_muvekkil_uppers = {m.upper().replace("İ", "I") for m in unique_muvekkiller}
            cleaned_diger_isimler = []
            for isim in data.get("belgede_gecen_isimler", []):
                isim_upper = isim.upper().replace("İ", "I")
                # Eğer müvekkiller listesinde yoksa ekle
                if isim_upper not in final_muvekkil_uppers:
                    cleaned_diger_isimler.append(isim)
            
            data["belgede_gecen_isimler"] = cleaned_diger_isimler
            
            # Önemli durumları logla
            if kaynak == "fallback":
                TechnicalLogger.log("WARNING", f"⚠️ HOOK YANLIŞTI! '{hook_muvekkil}' yerine '{sonuc}' kullanıldı")
            elif kaynak == "bulunamadi":
                TechnicalLogger.log("WARNING", f"ℹ️ Listede bulunamadı: '{hook_muvekkil}' (Yeni müvekkil olabilir)")
                
        except Exception as e:
            TechnicalLogger.log("ERROR", f"Hibrit filtreleme hatası: {e}")
            debug_info.append(f"- Müvekkil: HATA ({data.get('muvekkil_adi')})")

            
        # 🆕 DOSYA ADI FORMATLAMA
        try:
            client_list = data.get("muvekkiller", [])
            # Fallback for legacy prompt response or single client
            if not client_list and data.get("muvekkil_adi"):
                client_list = [data.get("muvekkil_adi")]
            
            # Ensure list is list
            if not isinstance(client_list, list):
                 if isinstance(client_list, str):
                     client_list = [client_list]
                 else:
                     client_list = []

            final_filename_string = ""
            if client_list:
                first_client = str(client_list[0]).strip()
                parts = first_client.split()
                if len(parts) >= 2:
                    initial = parts[0][0].upper().replace('İ', 'I')
                    surname = parts[-1].upper().replace('İ', 'I')
                    formatted_base = f"{initial}. {surname}"
                else:
                    formatted_base = first_client.upper().replace('İ', 'I')
                
                if len(formatted_base) > 14:
                    formatted_base = formatted_base[:14]
                else:
                    formatted_base = formatted_base.ljust(14, "_")
                
                count = len(client_list)
                if count > 1:
                    suffix = f"_+{count-1}"
                    final_filename_string = formatted_base + suffix
                else:
                    final_filename_string = formatted_base
                
                data["dosya_icin_ozel_isim"] = final_filename_string
                debug_info.append(f"- Dosya Formatı: {final_filename_string} (Kaynak: {len(client_list)} kişi)")
            else:
                 debug_info.append("- Dosya Formatı: OLUŞTURULAMADI (Liste boş)")

        except Exception as e:
            TechnicalLogger.log("ERROR", f"Dosya formatlama hatası: {e}")
            debug_info.append(f"- Dosya Formatı: HATA ({str(e)})")

        # Debug info artık özete eklenmez, sadece terminale loglanır
        TechnicalLogger.log("DEBUG", f"Post-processing: {debug_info}")

        # ⏱️ BENCHMARK: Toplam süreyi hesapla ve logla
        benchmark["total"] = round((time.perf_counter() - total_start) * 1000, 2)
        
        # Görünür çıktı için print kullan (TechnicalLogger bazen filtreliyor)
        print(f"\n{'='*60}")
        print(f"⏱️ BENCHMARK SONUÇLARI (ms):")
        for key, value in benchmark.items():
            print(f"   {key}: {value} ms")
        print(f"{'='*60}\n")
        
        logging.info(f"⏱️ BENCHMARK: {benchmark}")
        
        # Ayrıca data içine de ekle ki frontend'de görülebilsin
        data["_benchmark"] = benchmark

        TechnicalLogger.log(
            "INFO",
            "Gemini Analysis Successful",
            {"file": file_path, "doc_type": data.get("belge_turu_kodu")},
        )
        yield {"status": "complete", "data": data}

    except FileNotFoundError:
        # Error handlers unchanged
        error_id = str(uuid.uuid4())[:8]
        TechnicalLogger.log("ERROR", f"File not found: {file_path}")
        default_data = get_default_json()
        default_data["hash"] = file_hash
        default_data["ozet"] = (
            f"Dosya bulunamadı. Lütfen dosya yolunu kontrol edin. (Kod: {error_id})"
        )
        yield {"status": "complete", "data": default_data}

    except ValueError as e:
        error_id = str(uuid.uuid4())[:8]
        TechnicalLogger.log("ERROR", f"Gemini Value Error (Likely Safety Block): {e}")
        default_data = get_default_json()
        default_data["hash"] = file_hash
        default_data["ozet"] = (
            f"Yapay zeka yanıtı engellendi (Güvenlik/Gizlilik Filtresi). (Kod: {error_id})"
        )
        yield {"status": "complete", "data": default_data}

    except Exception as e:
        error_id = str(uuid.uuid4())[:8]
        TechnicalLogger.log(
            "ERROR",
            f"Gemini Analysis Failed for {file_path} [ErrorID: {error_id}]: {e}",
            {"trace": str(e)},
        )

        default_data = get_default_json()
        default_data["hash"] = file_hash

        if "403" in str(e) or "quota" in str(e).lower():
            default_data["ozet"] = (
                f"API Erişim Hatası (Kota Aşımı veya Yetki Sorunu). (Kod: {error_id})"
            )
        else:
            default_data["ozet"] = (
                f"Analiz teknik bir sorun nedeniyle tamamlanamadı. (Kod: {error_id})"
            )

        yield {"status": "complete", "data": default_data}
    finally:
        if uploaded_file:
            try:
                uploaded_file.delete()
            except Exception as e:
                TechnicalLogger.log("WARNING", f"Error deleting Gemini file: {e}")
        
        if temp_pdf_from_udf and os.path.exists(temp_pdf_from_udf):
            try:
                os.remove(temp_pdf_from_udf)
                TechnicalLogger.log("INFO", f"Cleaned up temp UDF PDF: {temp_pdf_from_udf}")
            except Exception as e:
                TechnicalLogger.log("WARNING", f"Error deleting temp UDF PDF: {e}")


# Backward compatibility wrapper (Now Async)
async def analyze_file_local(file_path: str) -> Optional[Dict[str, Any]]:
    gen = analyze_file_generator(file_path)
    result = None
    async for item in gen:
        if item["status"] == "complete":
            result = item["data"]
    return result


if __name__ == "__main__":
    print("Analyzer Module Loaded.")
