
from datetime import datetime
from typing import Optional, List, Dict


def get_system_instruction(
    dynamic_lawyers: Optional[List[Dict]] = None,
    dynamic_doctypes: Optional[List[Dict]] = None,
    dynamic_statuses: Optional[List[Dict]] = None, 
    candidates: Optional[List[str]] = None,
    missing_fields: Optional[List[str]] = None,
    pre_extracted: Optional[Dict] = None
) -> str:
    """
    Generates a DYNAMIC system instruction based on which fields need extraction.
    
    Args:
        missing_fields: List of fields that regex couldn't find. 
                       Options: ["tarih", "esas_no", "avukat_kodu", "muvekkil"]
                       If None or empty, LLM will only generate summary.
        pre_extracted: Dict of values already found by regex (for context)
    """
    
    # Default: if missing_fields is None, assume all fields need extraction (legacy mode)
    if missing_fields is None:
        missing_fields = ["tarih", "esas_no", "avukat_kodu", "muvekkil"]
    
    # 1. Common Parts
    today_str = datetime.now().strftime("%d.%m.%Y")
    
    lawyer_list_str = ""
    lawyer_names_for_exclusion = []
    if dynamic_lawyers:
        for lawyer in dynamic_lawyers:
            code = lawyer.get("code", "UNK")
            name = lawyer.get("name", "")
            lawyer_list_str += f'- "{code}" : {name}\n'
            if name:
                lawyer_names_for_exclusion.append(name.upper())
            
    # CHECK MODE
    mode = "VERIFICATION" if (candidates and len(candidates) > 0) else "DISCOVERY"
    
    candidates_str = ""
    if mode == "VERIFICATION":
        candidates_str = "ADAY LİSTESİ (Sadece buradan seç):\n" + "\n".join([f"- {c}" for c in candidates])
    else:
        candidates_str = "ADAY LİSTESİ BOŞ. (KEŞİF MODU AKTİF)"

    # --- BUILD DYNAMIC TASK SECTION ---
    task_items = []
    
    # Pre-extracted context (show what was already found)
    pre_context = ""
    if pre_extracted:
        found_items = []
        if pre_extracted.get("tarih"):
            found_items.append(f"Tarih: {pre_extracted['tarih']}")
        if pre_extracted.get("esas_no"):
            found_items.append(f"Esas No: {pre_extracted['esas_no']}")
        if pre_extracted.get("avukat_kodu"):
            found_items.append(f"Avukat: {pre_extracted['avukat_kodu']}")
        if pre_extracted.get("muvekkil_candidates"):
            found_items.append(f"Müvekkil Adayları: {', '.join(pre_extracted['muvekkil_candidates'])}")
        
        if found_items:
            pre_context = f"""
    ÖN ÇIKARIM BİLGİSİ (Zaten bulundu, DEĞİŞTİRME):
    {chr(10).join(['    - ' + item for item in found_items])}
    """

    # Build task list based on missing fields
    if "tarih" in missing_fields:
        task_items.append("""
    📅 TARİH: Belgedeki tarihi bul (YYYY-MM-DD formatında).
       - En yeni/en güncel tarihi tercih et.
       - Eğer tarih yoksa veya belirsizse: null""")
    
    if "esas_no" in missing_fields:
        task_items.append("""
    🔢 ESAS NO: Dava esas numarasını bul (Örn: "2024/123").
       - Formatlar: "2024/123 Esas", "E. 2024/123", "Esas No: 2024/123"
       - Karar numarasını YAZMA, sadece Esas numarası.
       - Eğer yoksa: null""")
    
    if "avukat_kodu" in missing_fields:
        task_items.append(f"""
    ⚖️ AVUKAT KODU: Aşağıdaki listeden belgede geçen avukatı bul:
{lawyer_list_str}
       - Sadece listede olan avukatların KODU'nu yaz (örn: "AGH")
       - Listede yoksa: null""")
    
    if "muvekkil" in missing_fields:
        if mode == "VERIFICATION":
            task_items.append(f"""
    👤 MÜVEKKİL TESPİTİ (DOĞRULAMA MODU):
       {candidates_str}
       - SADECE yukarıdaki listeden seç!
       - Listede olan ismi aynen yaz.
       - Listede yoksa: null""")
        else:
            task_items.append("""
    👤 MÜVEKKİL TESPİTİ (KEŞİF MODU):
       - Aday listesi boş, yeni müvekkil bul.
       - H&A Avukatının temsil ettiği kişiyi bul.
       - Avukatın "Vekili" olarak göründüğü tarafı seç.""")
    
    # Summary is ALWAYS requested
    task_items.append("""
    📝 ÖZET: Belgenin detaylı özeti (2-3 cümle).""")
    
    # Name list is ALWAYS requested, with lawyer exclusion
    lawyer_exclusion_note = ""
    if lawyer_names_for_exclusion:
        lawyer_exclusion_note = f"""
       ⚠️ AVUKATLARI DAHİL ETME! Şu isimleri listeye YAZMA:
       {', '.join(lawyer_names_for_exclusion[:5])}{'...' if len(lawyer_names_for_exclusion) > 5 else ''}"""
    
    task_items.append(f"""
    📋 İSİM LİSTESİ (belgede_gecen_isimler):
       Belgede geçen TÜM taraf isimlerini çıkar:
       - Davacı, Davalı, Sanık, Müşteki, Tanık, İhbar Olunan, Şirketler, Kurumlar
       - Müvekkil olarak seçtiğin ismi de ekle{lawyer_exclusion_note}""")
    
    # Determine if this is a "summary only" mode
    is_summary_only = len(missing_fields) == 0
    
    if is_summary_only:
        main_task = """
    🎯 SADECE ÖZET MODU:
    Tüm metadata alanları (tarih, esas_no vb.) zaten bulundu. Senin görevin:
    1. Belgenin detaylı özetini yaz
    2. Belgedeki isimleri listele (avukatlar HARİÇ)
    
    DİĞER ALANLARI BOŞ BIRAK (tarih, esas_no, avukat_kodu, muvekkil_adi = null)
    Onlar zaten sistemde var."""
    else:
        main_task = f"""
    🎯 EKSİK ALAN MODU:
    Bazı alanlar regex ile bulunamadı. Sadece aşağıdaki görevleri yap:
    {chr(10).join(task_items)}
    {pre_context}"""

    system_instruction = f"""
<system_instruction>
  <role>H&A Veri Mühendisi (Dinamik Mod)</role>
  <objective>Verilen metni analiz et ve JSON çıktısı üret.</objective>
  <today>{today_str}</today>
  
  <critical_ops>
    {main_task}
  </critical_ops>

  <output_schema>
    {{
      "tarih": "YYYY-MM-DD | null",
      "muvekkil_adi": "String | null",
      "muvekkiller": [],
      "belgede_gecen_isimler": [],
      "avukat_kodu": "String | null",
      "esas_no": "String | null",
      "durum": "G",
      "ozet": "String"
    }}
  </output_schema>
  
  <rules>
    - SADECE istenen alanları doldur
    - Liste alanları (muvekkiller, belgede_gecen_isimler) için bulamazsan BOŞ LİSTE [] döndür, ASLA null YAZMA
    - Tekil alanlar (tarih, esas_no vb.) için bulamazsan null yaz
    - AVUKATLARI belgede_gecen_isimler listesine YAZMA
    - JSON formatında yanıt ver
  </rules>
</system_instruction>
"""
    return system_instruction
