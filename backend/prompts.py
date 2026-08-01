
from datetime import datetime
from typing import Optional, List, Dict


def get_system_instruction(
    dynamic_lawyers: Optional[List[Dict]] = None,
    dynamic_doctypes: Optional[List[Dict]] = None,
    dynamic_statuses: Optional[List[Dict]] = None,
    candidates: Optional[List[str]] = None,
    missing_fields: Optional[List[str]] = None,
    pre_extracted: Optional[Dict] = None,
    belge_turu_kodu: Optional[str] = None,
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
        missing_fields = ["tarih", "esas_no", "muvekkil", "court"]
    
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
        if pre_extracted.get("court"):
            found_items.append(f"Mahkeme: {pre_extracted['court']}")
        
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
    

    if "court" in missing_fields:
        task_items.append("""
    🏛️ MAHKEME ADI: Bu belgeyi çıkaran (karar veren) mahkemenin TAM adını bul.
       - Karar başlığındaki adı kullan (örn: "Ankara Bölge İdare Mahkemesi 10. İdari Dava Dairesi")
       - Belgede atıf yapılan alt/üst mahkemeleri değil, bu kararın SAHİBİ olan mahkemeyi yaz.
       - Bulamazsan: null""")
    
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
    
    # Duruşma/tensip zaptı ve tebligat için sonraki duruşma tarihi ve saati çıkarımı
    from constants import is_hearing_doctype
    _btk = (belge_turu_kodu or "").upper()
    is_durusma_zapt = is_hearing_doctype(belge_turu_kodu)
    is_tebligat = "TEBLIG" in _btk
    if is_durusma_zapt:
        tebligat_note = ""
        if is_tebligat:
            tebligat_note = """
       ⚠️ TEBLİGAT ZARFI ÖZEL KURALLARI:
       - Duruşma bilgisi "Duruşma Günü / Duruşma Saati / Duruşma Yeri" ETİKETLİ
         form alanlarında yazar; etiketler değerlerden SONRA gelebilir.
       - "BU ZARFTA ... VARDIR" satırındaki tarih zarftaki EVRAKIN tarihidir,
         duruşma günü DEĞİLDİR. Onu seçme."""
        task_items.append(f"""
    📅 SONRAKİ DURUŞMA TARİHİ ve SAATİ (sonraki_durusma_tarihi, sonraki_durusma_saati):
       Belgenin SONUNDA genellikle şu formatta yazılır:
       "DD/MM/YYYY günü saat HH:MM'e bırakılmasına karar verildi"
       veya "duruşmanın ... günü saat ...'e bırakılmasına", "erteleme", "talik" ifadeleri.{tebligat_note}
       - Tarihi çıkar. Format: YYYY-MM-DD
       - Saati çıkar. Format: HH:MM (örn. 09:43)
       - Birden fazla tarih varsa en ileri (en gelecekteki) tarihi seç.
       - Tarih bulamazsan: null. Saat bulamazsan: null""")

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
        if is_durusma_zapt:
            main_task = f"""
    🎯 ÖZET + DURUŞMA TARİHİ MODU:
    Metadata alanları (tarih, esas_no vb.) zaten bulundu. Senin görevin:
    1. Belgenin detaylı özetini yaz
    2. Belgedeki isimleri listele (avukatlar HARİÇ)
    3. Sonraki duruşma tarihini MUTLAKA çıkar (aşağıya bak)

    📅 SONRAKİ DURUŞMA TARİHİ (sonraki_durusma_tarihi):
       Belgenin sonunda genellikle şu formatta yazılır:
       "duruşmanın ... günü saat ...'e bırakılmasına karar verildi"{tebligat_note}
       - O tarihi çıkar. Format: YYYY-MM-DD
       - Bulamazsan: null

    DİĞER ALANLARI BOŞ BIRAK (tarih, esas_no, muvekkil_adi = null)
    Onlar zaten sistemde var."""
        else:
            main_task = """
    🎯 SADECE ÖZET MODU:
    Tüm metadata alanları (tarih, esas_no vb.) zaten bulundu. Senin görevin:
    1. Belgenin detaylı özetini yaz
    2. Belgedeki isimleri listele (avukatlar HARİÇ)

    DİĞER ALANLARI BOŞ BIRAK (tarih, esas_no, muvekkil_adi = null)
    Onlar zaten sistemde var."""
    else:
        main_task = f"""
    🎯 EKSİK ALAN MODU:
    Bazı alanlar regex ile bulunamadı. Sadece aşağıdaki görevleri yap:
    {chr(10).join(task_items)}
    {pre_context}"""

    durusma_schema_field = ',\n      "sonraki_durusma_tarihi": "YYYY-MM-DD | null",\n      "sonraki_durusma_saati": "HH:MM | null"' if is_durusma_zapt else ""

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
      "esas_no": "String | null",
      "court": "String | null",
      "durum": "G",
      "ozet": "String"{durusma_schema_field}
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


# =====================================================================
# Otonom dava açma — intake çıkarım talimatı (Faz 2).
# Faz 0 kalibrasyonuyla (calibration/run_calibration.py) itere edilmiş
# prompt v2; şeması schemas_intake.CaseIntakeExtraction.
# =====================================================================


def get_case_intake_instruction(
    regex_hints: Optional[Dict] = None,
    lawyer_names: Optional[List[str]] = None,
    client_hints: Optional[List[str]] = None,
    yargi_turleri: Optional[List[str]] = None,
    dava_konulari: Optional[List[str]] = None,
    uzmanliklar: Optional[List[str]] = None,
) -> str:
    """Dava kartı odaklı çıkarım talimatı.

    regex_hints: metinden ön-çıkarılan ipuçları (esas_no adayları, tarihler).
    lawyer_names: büro avukat listesi (vekil ayıklama + uyap_lawyer eşleşmesi).
    client_hints: FlashText'in belgede bulduğu kayıtlı müvekkil adları.
    yargi_turleri: izinli yargı türü listesi (DB'den; yoksa varsayılan).
    dava_konulari: izinli dava konusu listesi (DB'den; liste-dışı değer istenmez).
    uzmanliklar: izinli uzmanlık listesi (DB'den; liste-dışı değer istenmez).
    """
    yargi_list = yargi_turleri or [
        "Hukuk", "Ceza", "İcra", "İdari", "Arabuluculuk", "Savcılık",
    ]

    # Dava konusu / uzmanlık: kanonik liste varsa değer YA listeden birebir gelir
    # YA null — serbest metin fallback'i yok (merge tarafındaki bekçiyle birlikte
    # yönetici panelindeki dinamik listeler dışına değer sızmaz).
    kanonik_kurallar = []
    if dava_konulari:
        kanonik_kurallar.append(
            f"- dava_konusu SADECE şu listeden BİREBİR seçilir: {', '.join(dava_konulari)}. "
            "Hiçbiri uymuyorsa null bırak — belgedeki ifadeyi YAZMA."
        )
    if uzmanliklar:
        kanonik_kurallar.append(
            f"- uzmanlik_tahmini SADECE şu listeden BİREBİR seçilir: {', '.join(uzmanliklar)}. "
            "Hiçbiri uymuyorsa null bırak — serbest metin YAZMA."
        )

    sections = [
        "Sen bir Türk hukuk bürosunun dava açılış asistanısın. Sana verilen belge, "
        "yeni açılacak bir dava dosyasının açılış evrakından BİRİDİR (dava dilekçesi, "
        "tensip zaptı, tebligat mazbatası, sigorta poliçesi, vekaletname, sigorta "
        "görevlendirme/atama yazısı, sigorta atama e-postası (çıktısı) vb.). Görevin "
        "bu belgeden dava kartı alanlarını çıkarmak ve istenen JSON şemasını "
        "doldurmaktır.",
        "",
        "GENEL KURALLAR:",
        "- Yalnızca belgede AÇIKÇA yazan bilgiyi çıkar. Tahmin etme, uydurma; "
        "belgede olmayan alanı null bırak. Boş alan hatalı alandan iyidir.",
        "- Tarihleri ISO biçiminde ver (YYYY-MM-DD).",
        "- esas_no biçimi 'YYYY/N' (örn. 2024/123). 'E.', 'ESAS NO' etiketleriyle "
        "geçer. Değişik iş (D.İş), talimat veya soruşturma numarasını esas_no sanma.",
        "- mahkeme: daire numarası dahil TAM resmi ad (örn. 'ANKARA 3. ASLİYE HUKUK "
        "MAHKEMESİ'). Belge başlığındaki mahkemeyi al; dilekçede '... MAHKEMESİNE' "
        "hitabı da geçerli kaynaktır.",
        f"- yargi_turu şu listeden seçilir: {', '.join(yargi_list)}. Mahkeme adından "
        "türet (İdare/Vergi Mahkemesi → İdari; Asliye/Tüketici/İş/Asliye Ticaret → "
        "Hukuk; Ağır Ceza/Asliye Ceza → Ceza; İcra Dairesi → İcra).",
        *kanonik_kurallar,
        "",
        "TARAF KURALLARI (kritik):",
        "- Tarafları YALNIZCA belgenin taraf/başlık bloğundan al (DAVACI:, DAVALI:, "
        "MÜDAHİL:, İHBAR OLUNAN: etiketleri). Metin içinde adı geçen herkesi taraf yapma.",
        "- Avukatları taraf olarak LİSTELEME; vekil bilgisi gerekiyorsa rol=VEKIL ile ver.",
        "- tc_no yalnızca belgede yazılı T.C. kimlik numarasıysa doldur. SANSÜRLÜ ise "
        "(örn. '***0959214*') yıldızlar DAHİL aynen aktar — görünen haneler kayıt "
        "eşleştirmede kullanılır; yıldızları tamamlamaya veya tahmin etmeye çalışma.",
        "- Poliçe belgesinde davacı/davalı yoktur: sigortalı HEKİMİ rol=SIGORTALI, "
        "sigorta şirketini rol=SIGORTA_SIRKETI olarak taraflar listesine MUTLAKA yaz — "
        "poliçede en az bu iki taraf her zaman vardır, boş taraf listesi dönme. "
        "DİKKAT: 'Sigorta Ettiren' (prim ödeyen hastane/şirket) sigortalı DEĞİLDİR; "
        "onu taraflara değil sigortali_kurum alanına yaz. Sigortalı, 'Sigortalı "
        "Adı/Ünvanı' etiketli KİŞİDİR.",
        "- Vekaletnamede vekalet VEREN kişiyi rol=DIGER ile ver (davadaki rolü bu "
        "belgeden bilinemez); vekil tayin edilen avukatları rol=VEKIL ile ver.",
        "",
        "BELGE TÜRÜNE GÖRE ODAK:",
        "- Dava dilekçesi: taraflar, mahkeme hitabı, dava_konusu (KONU/TALEP bölümü), "
        "maddi/manevi tazminat (SONUÇ ve İSTEM bölümündeki harca esas değer), olay "
        "anlatımından uzmanlik_tahmini (örn. estetik ameliyat türü, tıbbi işlem).",
        "- Tensip zaptı: esas_no (en güvenilir kaynak), mahkeme, dava_acilis_tarihi, taraflar.",
        "- Tebligat mazbatası/zarfı: teblig_tarihi, esas_no, mahkeme.",
        "- Poliçe: police_no (yenileme no'suyla birlikte, örn. '92804147/4'), "
        "sigorta_sirketi (TEMİNATI VEREN şirket; acente/broker DEĞİL), sigortalı hekim adı, "
        "poliçe dönemi (police_baslangic_tarihi / police_bitis_tarihi), varsa "
        "'Geçmişe Etkinlik / Retroaktif Tarih' → retroaktif_tarihi, police_turu: "
        "'Tıbbi Kötü Uygulamaya İlişkin Zorunlu Mali Sorumluluk' → ZORUNLU, "
        "'Tamamlayıcı Hekim Sorumluluk' → TAMAMLAYICI. sigortali_kurum: hekimin bağlı "
        "olduğu kurum veya sigorta ettiren hastane/şirket. teminat_limiti: olay başına "
        "teminat (TL). Hekimin uzmanlık dalı yazıyorsa uzmanlik_tahmini'ne yaz. "
        "Aynı hekimin birden fazla poliçesi olabilir; SADECE bu belgedeki poliçeyi çıkar. "
        "Belge bir zeyilname ise bunu belge_turu_tahmini'nde belirt.",
        "- Sigorta görevlendirme/atama yazısı: hasar_dosya_no, hukuk_no, sigorta_sirketi, "
        "sigortalı/ilgili hekim adı.",
        "- Sigorta atama e-postası (çıktısı): sigorta şirketinin büroya dava atadığı "
        "e-posta. Başındaki Konu/Kimden/Kime/Tarih başlık tablosu ve gövde metni "
        "veri kaynağıdır:",
        "  * 'T.T' / 'T.T.' kısaltması TEBLİĞ TARİHİ demektir (örn. 'T.T: 23/07/2026') "
        "→ teblig_tarihi. Bunu belge_tarihi veya dava_acilis_tarihi sanma.",
        "  * Konu satırı kalıbı '[<Mahkeme>-<HasarDosyaNo>-<n>-<Esas Yıl/No>]' "
        "(örn. '[Kayseri 3. Tüketici Mahkemesi-5002940510859-0-2026/371]') → buradan "
        "mahkeme, hasar_dosya_no (uzun rakam dizisi) ve esas_no (YYYY/N) çıkarılır.",
        "  * Gönderen şirket / imza bloğu → sigorta_sirketi ipucu (örn. Quick "
        "Sigorta). E-postayı gönderen sigorta şirketidir; büro veya avukat değildir.",
        "  * Forward zincirindeki 'From:/Sent:/Subject:' blokları da aynı kurallarla "
        "taranır.",
        "- belge_turu_tahmini alanına belgenin türünü serbest metinle yaz "
        "(örn. 'Dava Dilekçesi', 'Tensip Zaptı', 'Sigorta Poliçesi').",
        "",
        "- ozet: 2-3 cümlelik nesnel özet — kim kime karşı, ne talep ediyor, hangi olay.",
    ]

    if lawyer_names:
        sections += [
            "",
            "BÜRO AVUKATLARI (bu isimler büronun kendi avukatlarıdır; taraf DEĞİLDİR, "
            "belgede vekil olarak geçerlerse rol=VEKIL ile işaretle):",
            *[f"- {n}" for n in lawyer_names],
        ]

    if client_hints:
        sections += [
            "",
            "KAYITLI MÜVEKKİL İPUCU (bu adlar büronun müvekkil kayıtlarıyla eşleşti; "
            "belgede geçiyorlarsa taraf listesine almayı atlama):",
            *[f"- {n}" for n in client_hints],
        ]

    if regex_hints:
        sections += [
            "",
            "METİNDEN ÖN-ÇIKARILAN İPUÇLARI (doğrula; belgeyle çelişiyorsa belgeyi esas al):",
            *[f"- {k}: {v}" for k, v in regex_hints.items() if v],
        ]

    return "\n".join(sections)


def get_case_intake_verifier_instruction() -> str:
    """Katman 2 — kritik alan doğrulayıcı geçişi talimatı.

    Ensemble sonucundaki kritik değerler (esas_no, tc_no, taraf rolleri) için
    ikinci bir çağrıyla "değer belgede geçiyor mu, kanıt cümlesi ne?" sorulur.
    Kanıtsız değer düşük güvenli işaretlenir (sihirbazda rozet rengi).
    """
    return "\n".join([
        "Sen bir Türk hukuk belgesi DOĞRULAMA asistanısın. Sana bir belge ve bu "
        "belgeden çıkarıldığı iddia edilen alan değerlerinin listesi verilecek. "
        "Görevin her iddiayı belgeye karşı TEK TEK kontrol etmektir; yeni bilgi "
        "çıkarmak değil.",
        "",
        "KURALLAR:",
        "- Her iddia için: deger belgede AÇIKÇA geçiyorsa belgede_geciyor=true yaz ve "
        "kanit alanına belgeden geçtiği kısa cümleyi/ifadeyi AYNEN aktar.",
        "- Değer belgede geçmiyorsa veya emin değilsen belgede_geciyor=false, kanit=null. "
        "Şüphede false tercih et — yanlış onay yanlış redden kötüdür.",
        "- alan 'rol:' ile başlıyorsa: adı verilen kişinin belgede o rol etiketi "
        "altında (DAVACI:, DAVALI:, SİGORTALI vb.) yer alıp almadığını kontrol et.",
        "- alan 'tc_no:' ile başlıyorsa: numara belgedeki değerle birebir eşleşmelidir; "
        "sansürlü (yıldızlı) değerlerde yıldız düzeni dahil karşılaştır.",
        "- Biçim farkı (boşluk, büyük/küçük harf, noktalama) eşleşmeyi BOZMAZ; "
        "içerik farkı bozar.",
        "- Listedeki HER iddia için tam olarak BİR kontrol sonucu döndür; alan ve "
        "deger değerlerini sana verildiği gibi aynen geri yaz.",
    ])


def get_case_intake_arbiter_instruction() -> str:
    """Katman 3 — belgeler-arası hakem talimatı (Faz 3).

    Aynı dava açılış oturumundaki belgeler esas_no/mahkeme'de anlaşamadığında
    çağrılır; tüm belge özetlerini görerek dava kartına yazılacak değeri
    gerekçesiyle seçer. Çelişki yoksa hiç çağrılmaz.
    """
    return "\n".join([
        "Sen bir Türk hukuk bürosunun dava dosyası HAKEMİSİN. Aynı dava için "
        "yüklenen belgelerden çıkarılan alan değerleri birbiriyle çelişiyor. "
        "Sana çelişen alanlar (adaylarıyla) ve her belgenin kısa künyesi "
        "(türü, tarihi, esas no, mahkeme, özet) JSON olarak verilecek.",
        "",
        "GÖREV: Her çelişen alan için YENİ AÇILACAK dava kartına yazılması "
        "gereken TEK değeri seç ve kısa gerekçesini yaz.",
        "",
        "KURALLAR:",
        "- secilen_deger, verilen adaylardan biri olmalı ve AYNEN kopyalanmalı; "
        "yeni değer üretme, birleştirme, düzeltme yapma.",
        "- Meşru fark kalıplarını tanı: aynı dosyanın yeni esası (dosya yenilenmiş), "
        "istinaf/temyiz aşaması farklı mahkeme, birleşen dosya, değişik iş (D.İş) "
        "numarası, tebligat üzerindeki eski esas. Dava kartı asıl/ilk derece "
        "dosyayı temsil eder — istinaf esasını veya D.İş numarasını seçme.",
        "- Belge türü hiyerarşisi: tensip zaptı > dava dilekçesi > tebligat > diğer "
        "(tensip mahkemenin kendi kaydıdır, en güvenilir kaynaktır).",
        "- Tarih hiyerarşisi: aynı güvenilirlikte iki kaynak çelişiyorsa daha YENİ "
        "tarihli belgeyi tercih et.",
        "- gerekce 1-2 cümle, Türkçe, kullanıcıya gösterilecek netlikte olsun "
        "(örn. 'Tensip zaptı mahkemenin kendi kaydı olduğundan esas no buradan alındı; "
        "dilekçedeki numara harç tahsil müzekkeresine ait görünüyor').",
        "- Karar veremiyorsan en çok belgede geçen adayı seç ve gerekçede "
        "belirsizliği belirt.",
        "- Yalnızca sana verilen çelişen alanlar için karar döndür.",
    ])
