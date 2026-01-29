import re
import os
import json
from datetime import datetime
import logging
import google.generativeai as genai
import vault
from dotenv import load_dotenv

# Load Environment
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=env_path)

# Configure Gemini
api_key = vault.get_secret("GEMINI_API_KEY") 
if api_key:
    genai.configure(api_key=api_key)

def get_model():
    model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-1.5-flash")
    return genai.GenerativeModel(model_name)

class DateCandidate:
    def __init__(self, date_str, original_text, match_index, total_len, context_score=0):
        self.date_str = date_str
        self.original_text = original_text
        self.index = match_index
        self.normalized_pos = match_index / total_len if total_len > 0 else 0
        self.context_score = context_score
        self.recency_score = 0 # Recency Bonus/Penalty
        self.final_score = 0
        self.breakdown = {}
        
        # Extract snippet (50 chars before and after)
        start = max(0, match_index - 60)
        end = min(len(original_text), match_index + len(date_str) + 60)
        self.snippet = original_text[start:end].replace("\n", " ").strip()

    def calculate_score(self):
        # Base Score
        score = 10
        
        # 1. Position Scoring
        pos_score = 0
        if self.normalized_pos < 0.2:
            pos_score = 20
        elif self.normalized_pos > 0.8:
            pos_score = 40
        else:
            pos_score = -20 # Body Penalty (Middle of document is less likely)
        score += pos_score
        
        # 2. Context Keywords
        context_window = self.original_text[max(0, self.index - 50):min(len(self.original_text), self.index + 50)].lower()
        keyword_score = 0
        
        if "tarih" in context_window:
            keyword_score += 30
        if "imza" in context_window:
            keyword_score += 30
        if "düzenleme" in context_window or "tanzim" in context_window:
            keyword_score += 35
        if "karar verildi" in context_window or "oy birliğiyle" in context_window:
             keyword_score += 50 # Very high score for decision dates
        if "vade" in context_window or "suç" in context_window or "olay" in context_window:
            keyword_score -= 50
            
        score += keyword_score
        
        self.final_score = score + self.context_score + self.recency_score
        
        self.breakdown = {
            "Base": 10,
            "Pos": pos_score,
            "Key": keyword_score,
            "Context": self.context_score,
            "Recency": self.recency_score
        }
        return self.final_score

    def __repr__(self):
        # Format: Total [Base|Pos|Key|Rec]
        breakdown_str = f"B:{10} P:{self.breakdown['Pos']} K:{self.breakdown['Key']} R:{self.breakdown['Recency']}"
        return f"Date({self.date_str}, Total={self.final_score} [{breakdown_str}], Snippet='...{self.snippet[-20:] if len(self.snippet)>20 else self.snippet}...')"


def advanced_regex_scan(text):
    candidates = []
    text_len = len(text)
    today = datetime.now()
    
# --- PRE-COMPILED PATTERNS ---
# Pattern 1: Numeric (dd.mm.yyyy, dd/mm/yyyy, dd-mm-yyyy)
PRE_COMPILED_NUMERIC_DATE = re.compile(r'\b(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{4})\b')

# Pattern 2: Text Month (generalized)
PRE_COMPILED_TEXT_DATE = re.compile(r'\b(\d{1,2})\s+([a-zA-ZçÇğĞıIİiöÖşŞüÜ]+)\s+(\d{4})\b')

# Fallback LLM date check (YYYY-MM-DD)
PRE_COMPILED_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def advanced_regex_scan(text):
    candidates = []
    text_len = len(text)
    today = datetime.now()
    
    # Pattern 1: Numeric (Using Pre-Compiled)
    for match in PRE_COMPILED_NUMERIC_DATE.finditer(text):
        try:
            d, m, y = map(int, match.groups())
            if 1990 <= y: 
                # Basic validity check
                dt = datetime(y, m, d)
                if dt > today: continue # Strict Future Filter
                
                # Format to standard
                date_str = f"{d:02d}.{m:02d}.{y}"
                candidates.append(DateCandidate(date_str, text, match.start(), text_len))
        except ValueError:
            continue

    # Pattern 2: Text Month (15 Ocak 2023)
    months_map = {
        'OCAK': 1, 'ŞUBAT': 2, 'MART': 3, 'NİSAN': 4, 'MAYIS': 5, 'HAZİRAN': 6,
        'TEMMUZ': 7, 'AĞUSTOS': 8, 'EYLÜL': 9, 'EKİM': 10, 'KASIM': 11, 'ARALIK': 12
    }
    
    # Using Pre-Compiled Pattern
    for match in PRE_COMPILED_TEXT_DATE.finditer(text):
        d_str, m_str, y_str = match.groups()
        m_upper = m_str.upper().replace('İ', 'I').replace('I', 'I') 
        
        found_month = None
        for month_name, month_val in months_map.items():
            norm_key = month_name.replace('İ', 'I')
            if norm_key in m_upper or m_upper in norm_key:
                found_month = month_val
                break
        
        if found_month:
            try:
                y = int(y_str)
                d = int(d_str)
                if 1990 <= y:
                    dt_check = datetime(y, found_month, d)
                    if dt_check <= today: # Strict Future Filter
                         date_str = f"{d:02d}.{found_month:02d}.{y}"
                         candidates.append(DateCandidate(date_str, text, match.start(), text_len, context_score=5)) 
            except ValueError:
                continue

    # --- RECENCY BOOST & AGE PENALTY ---
    unique_dates = set()
    for cand in candidates:
        try:
            dt = datetime.strptime(cand.date_str, "%d.%m.%Y")
            if dt <= today:
                unique_dates.add(dt)
        except ValueError:
            pass
            
    # Sort descending (Newest first)
    sorted_dates = sorted(list(unique_dates), reverse=True)
    
    # Pick top 2 newest dates for Bonus
    top_2_dates = sorted_dates[:2] if sorted_dates else []
    top_2_strs = {d.strftime("%d.%m.%Y") for d in top_2_dates}
    
    # Max date for Age Penalty (Reference Point)
    max_date = sorted_dates[0] if sorted_dates else datetime(1900, 1, 1)

    # Calculate scores with boost and penalty
    for cand in candidates:
        cand_year = 1900
        try:
             cand_year = datetime.strptime(cand.date_str, "%d.%m.%Y").year
        except:
             pass

        # A. Recency Boost (+25)
        if cand.date_str in top_2_strs:
            cand.recency_score += 25 
        
        # B. Age Penalty (-5 per year difference)
        if cand_year < max_date.year:
            year_diff = max_date.year - cand_year
            penalty = min(50, year_diff * 5) # Cap penalty at -50
            cand.recency_score -= penalty
            
        cand.calculate_score()
        
    return candidates

def ask_llm_referee(text, top_candidates):
    """
    LLM decides which date is the correct Document Date among candidates.
    """
    model = get_model()
    
    candidates_str = "\n".join([
        f"- {c.date_str} (Bağlam: \"...{c.snippet}...\")" 
        for c in top_candidates
    ])
    
    prompt = f"""
    Sen uzman bir hukuk asistanısın. Görevin aşağıda verilen aday tarihler arasından belgenin ASIL DÜZENLENME TARİHİNİ tespit etmektir.
    
    Adaylar (Regex ile metinden çıkarıldı):
    {candidates_str}
    
    KURALLAR:
    1. ⚠️ KESİNLİKLE VE SADECE yukarıdaki kandidat listesindeki tarihlerden birini seç. Listede olmayan bir tarih uydurma.
    2. Belgenin "sonuçlandığı", "imzalandığı" veya "karar verildiği" tarihi bul.
    3. Hukuki ipuçları:
       - "Karar verildi", "Oy birliğiyle karar verildi" yazan cümlenin içindeki tarihi seç. (EN GÜÇLÜ İPUCU)
       - "İmza" bloğunun hemen altındaki veya üstündeki tarihi seç.
       - "Tebliğ", "Suç Tarihi", "Vade Tarihi" gibi tarihleri SEÇME.
    
    Lütfen yanıtı şu formatta JSON olarak ver:
    {{
        "selected_date": "YYYY-MM-DD",
        "reasoning": "Neden bu tarihi seçtiğinin kısa açıklaması. Hangi bağlam ipucunu kullandın (örn: 'oy birliğiyle karar verildi' ifadesi)."
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        cleaned = response.text.strip().replace("```json", "").replace("```", "").strip()
        return cleaned # Returns JSON string
    except Exception as e:
        logging.error(f"LLM Error: {e}")
        return None

def find_best_date(text: str) -> str:
    """
    Smart extraction logic replacing the old simple method.
    Returns YYYY-MM-DD or Today's date (if hard fallback needed).
    """
    if not text:
        return datetime.now().strftime("%Y-%m-%d")

    candidates = advanced_regex_scan(text)
    
    # Sort by score descending
    candidates.sort(key=lambda x: x.final_score, reverse=True)
    
    if not candidates:
        logging.warning("No date candidates found. Defaulting to Today.")
        return datetime.now().strftime("%Y-%m-%d")

    top_candidate = candidates[0]
    is_confident = top_candidate.final_score >= 50
    
    if len(candidates) > 1:
        runner_up = candidates[1]
        if (top_candidate.final_score - runner_up.final_score) < 20:
            is_confident = False
    
    if is_confident:
        try:
            dt = datetime.strptime(top_candidate.date_str, "%d.%m.%Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass # Fallback

    # Not confident -> LLM Referee
    try:
        json_response = ask_llm_referee(text, candidates[:3])
        if json_response:
            try:
                data = json.loads(json_response)
                selected = data.get("selected_date")
                if selected:
                    return selected
                    
            except json.JSONDecodeError:
                # Fallback: if LLM returns just the date string
                stripped = json_response.strip().strip('"').strip("'")
                if PRE_COMPILED_ISO_DATE.match(stripped):
                     return stripped
    except Exception as e:
        logging.error(f"LLM Referee failed: {e}")

    # Fallback if LLM fails or is unclear -> Return Top Candidate anyway
    try:
        dt = datetime.strptime(top_candidate.date_str, "%d.%m.%Y")
        return dt.strftime("%Y-%m-%d")
    except:
        return datetime.now().strftime("%Y-%m-%d")
