"""SQLAlchemy ORM modelleri — `Base.metadata` şemanın tek bildirimsel kaynağıdır.

Not (G028, 2026-08-12): `sync_logs` ve `analysis_cache` modelleri (`SyncLog`,
`AnalysisCache`) tek tüketicileri ölü kod olduğu ve iki tablo da boş kaldığı için
kaldırıldı. **Tablolar DB'de duruyor** — bilinçli olarak DROP edilmedi (veri kaybı
riski + migrate.py fail-fast). Artıkları görürsen: model yok, kullanan kod yok.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    tracking_no = Column(String, unique=True, index=True, nullable=False) # e.g. "2024/1234"
    esas_no = Column(String, index=True)
    status = Column(String, default="DERDEST") # "DERDEST", "DANIŞ", "MAHZEN"
    file_type = Column(String) # DOSYA_TURLERI
    # Uzmanlık Alanı (eski adı "Dava Türü Alt Kırılımı" — FAZ F §1.4 ile yeniden
    # adlandırıldı). Kolon ADI bilinçli DEĞİŞMEDİ: değer `specialties` referans
    # listesinden gelir (frontend NewCase.tsx, reference_lists.DEPENDENCIES) ve
    # rename bir ETİKET kararıdır — bkz. G044 raporu.
    sub_type = Column(String) # SPECIALTIES → Uzmanlık Alanı
    service_type = Column(String) # Algorithm Block 5
    subject = Column(String) # DAVA_KONULARI
    court = Column(String)
    opening_date = Column(Date)
    
    responsible_lawyer_name = Column(String)
    uyap_lawyer_name = Column(String)
    
    maddi_tazminat = Column(Numeric(precision=20, scale=2), default=0)
    manevi_tazminat = Column(Numeric(precision=20, scale=2), default=0)

    acceptance_date = Column(Date, nullable=True)  # İş Kabul Tarihi
    bureau_type = Column(String, nullable=True)  # Büro Özel Türü (DR ÖZEL, LEXİS, VEKALETSİZ TAKİP vs.)
    sub_type_extra = Column(String, nullable=True)  # Ek Alt Kırılım (RİNOPLASTİ;SEPTOPLASTİ vs.)
    judicial_unit = Column(String, nullable=True)  # Yargı Birimi (yargı türünün yanındaki ikinci seçim)
    
    notes = Column(String, nullable=True)
    active = Column(Boolean, default=True)
    tenant_id = Column(String, index=True, nullable=True)  # Azure AD tenant (tid)

    # Soft-delete: deleted_at tek gerçek kaynak; silmede active=False da yazılır
    # (restore'da True). Kayıt DB'de kalır, admin panelinden geri alınır.
    deleted_at    = Column(DateTime(timezone=True), nullable=True)
    deleted_by    = Column(String(200), nullable=True)
    delete_reason = Column(String, nullable=True)

    # Excel import alanları (BIRLESIK_SONUC_v5)
    klasor_no_2    = Column(String(2000), nullable=True)  # Eski sistem no — gizli, aranabilir
    atama_tarihi   = Column(Date,   nullable=True)  # Atama Tarihi
    hasar_dosya_no = Column(String, nullable=True)  # Hasar Dosya Numarası
    hukuk_no       = Column(String, nullable=True)  # Hukuk Numarası

    # Eski sistem kimlikleri (Full_Rapor_TKU aktarımı) — yalnız DB + arama, UI'da gösterilmez.
    # tku_no: olay/vaka grup anahtarı (TKU-784 gibi, unique DEĞİL — aynı olayın föyleri paylaşır)
    # sistem_no: Micro Kolay Ofis kayıt kimliği (SSTMN-9425 gibi, unique)
    tku_no    = Column(String(100), index=True, nullable=True)
    sistem_no = Column(String(100), unique=True, index=True, nullable=True)

    # Takip alanları
    case_stage = Column(String(50), nullable=True)          # DERDEST | KARAR | ISTINAF | TEMYIZ | KARAR_DUZELTME | KESINLESME | INFAZ | KAPALI
    dosya_son_durumu = Column(String(100), nullable=True)   # Dosya son durumu (serbest seçim)

    # Yerel Karar
    karar_tarihi = Column(Date, nullable=True)
    karar_turu = Column(String(50), nullable=True)          # KABUL | RED | KISMI_KABUL | FERAGAT | UZLASMA | DUSME
    karar_lehine = Column(String(20), nullable=True)        # LEHINE | ALEYHINE | KISMI
    # Yerel kararın RESMİ sonucu — kapalı liste (local_decisions, G060). Yukarıdaki
    # kaba 6'lık `karar_turu`ndan AYRI bir alandır; o alanın davranışı değişmez.
    yerel_karar_durumu = Column(String(100), nullable=True)
    karar_no = Column(String(50), nullable=True)
    karar_teblig_tarihi = Column(Date, nullable=True)
    karar_aciklama = Column(String, nullable=True)
    # Hükmedilen tutarlar (2026-08-05 büro mutabakatı) — NULL = girilmedi (0'dan farklı),
    # bu yüzden default YOK. Toplam otomatik hesaplanmaz, bağımsız alan.
    hukmedilen_maddi  = Column(Numeric(precision=20, scale=2), nullable=True)
    hukmedilen_manevi = Column(Numeric(precision=20, scale=2), nullable=True)
    hukmedilen_toplam = Column(Numeric(precision=20, scale=2), nullable=True)

    # İstinaf
    istinaf_basvuru_tarihi = Column(Date, nullable=True)
    istinaf_karar_durumu = Column(String(100), nullable=True)
    istinaf_karar_tarihi = Column(Date, nullable=True)
    istinaf_mahkemesi = Column(String(200), nullable=True)
    istinaf_esas_no = Column(String(50), nullable=True)
    istinaf_karar_no = Column(String(50), nullable=True)
    istinaf_karar_aciklama = Column(String, nullable=True)
    istinaf_teblig_tarihi = Column(Date, nullable=True)

    # Temyiz
    temyiz_basvuru_tarihi = Column(Date, nullable=True)
    temyiz_karar_durumu = Column(String(100), nullable=True)
    temyiz_karar_tarihi = Column(Date, nullable=True)
    temyiz_mahkemesi = Column(String(200), nullable=True)
    temyiz_esas_no = Column(String(50), nullable=True)
    temyiz_karar_no = Column(String(50), nullable=True)
    temyiz_eden_durumu = Column(String(100), nullable=True)
    temyiz_karar_aciklama = Column(String, nullable=True)
    temyiz_teblig_tarihi = Column(Date, nullable=True)

    # Karar Düzeltme
    karar_duzeltme_durumu = Column(String(100), nullable=True)
    karar_duzeltme_esas_no = Column(String(50), nullable=True)
    karar_duzeltme_karar_no = Column(String(50), nullable=True)
    karar_duzeltme_tarihi = Column(Date, nullable=True)
    karar_duzeltme_teblig_tarihi = Column(Date, nullable=True)
    karar_duzeltme_aciklama = Column(String, nullable=True)
    yeni_esas_no = Column(String(100), nullable=True)

    # Kesinleşme / İnfaz
    kesinlesme_tarihi = Column(Date, nullable=True)
    infaz_tarihi = Column(Date, nullable=True)

    # ─── FAZ F aktarım alanları (şartname §1.1, G044) ────────────────────────
    # Adlar BU TURDA kesinleşti: export sütun sabitliği taahhüdü verildikten
    # sonra ad değiştirmek taahhüt ihlali olur (şartname §1.4). Hepsi NULL kabul
    # eder — aktarım partiler hâlinde geleceği için "henüz gelmedi" normal
    # durumdur. Yazma yolu FAZ F'nin işi; burada şema + okuma yolu var.
    islah_tutari = Column(Numeric(precision=20, scale=2), nullable=True)  # ıslahla EKLENEN miktar (güncel talep = dava değeri)
    arsiv_tarihi = Column(Date, nullable=True)                  # dosya kapanış süresi + ön muhasebe analizinin dayanağı
    istinaf_basvuran_taraf = Column(String(50), nullable=True)  # KAPALI liste (appealing_parties): Davacı | Davalı | Her İki Taraf
    # DÜZELTME (G076, teslim paketi ölçüldü): "435 föyde esas no yerine geçiyor"
    # iddiası YANLIŞTI. 435 rakamı `Ana Tür = ARABULUCULUK` föy sayısıdır;
    # "Arabuluculuk Numarası" sütunu 8.409 satırın YALNIZ 1'inde dolu. Alan
    # kaynakta boş — dolduğu yer bugün için kullanıcının elle girişidir.
    arabuluculuk_no = Column(String(100), nullable=True)
    arabuluculuk_karar_tarihi = Column(Date, nullable=True)
    # Tıbbi analiz alanları: üçü branş bazlı BÜYÜYEN sözlük (serbest metin),
    # iddia_edilen_kusur ise KAPALI liste (alleged_faults).
    tibbi_surec = Column(String(300), nullable=True)
    tibbi_olay = Column(String(300), nullable=True)
    iddia_edilen_kusur = Column(String(200), nullable=True)
    hastada_olusan_zarar = Column(String(300), nullable=True)
    uygulanan_yontem = Column(String(200), nullable=True)
    # Belgeleme olayı alanları (G103) — iki KAPALI liste (event_types /
    # judgment_roles). Veri ekibinin 25.08 ölçümü: bağlı föylerin ~%14'ünde
    # tazminatın kaynağı tıbbi olay değil BELGELEME olayı (aydınlatma ihlali /
    # tıbbi kayıt eksikliği) ve aynı olgu yargı kademesine göre rol değiştiriyor
    # ("saptandı" ≠ "kazandırdı"). Ad denormalize taşınır (iddia_edilen_kusur
    # deseni). NULL = "karar okunmadı" — meşru durumdur, backfill YOK.
    olay_turu = Column(String(100), nullable=True)      # KAPALI liste (event_types)
    hukumdeki_rol = Column(String(100), nullable=True)  # KAPALI liste (judgment_roles)

    # ─── EKSİK ZORUNLU ALAN BAYRAĞI (FAZ E 6 + FAZ F D2/D8, G046) ────────────
    # TÜRETİLMİŞ kolon: NULL = eksik yok, aksi hâlde kaydın kovası
    # (required_fields.MISSING_BUCKETS: MANUAL | AKTARIM). Tek yazma yolu
    # `case_manager.refresh_missing_required` — değer required_fields'ın Python
    # kuralından hesaplanır, kolon yalnız filtrenin okuduğu önbellektir. Eskiden
    # bu soru her listelemede satır başına korele EXISTS'lerle soruluyordu.
    #
    # DEFAULT 'MANUAL' BİLİNÇLİ: case_manager'ı atlayan bir yazıcı (bugün
    # scripts/import_excel_cases.py) satırı hesaplamasız bırakırsa kayıt "eksik"
    # görünür. Yön önemlidir — görünmeyen borç hiç kapanmaz (ADR-014), fazladan
    # görünen borç ilk düzenlemede kendini düzeltir.
    missing_required_bucket = Column(
        String(20), nullable=True, server_default="MANUAL"
    )

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

    # Relationships
    parties = relationship("CaseParty", back_populates="case", cascade="all, delete-orphan")
    history = relationship("CaseHistory", back_populates="case", cascade="all, delete-orphan")
    documents = relationship("CaseDocument", back_populates="case", cascade="all, delete-orphan")
    lawyers = relationship("CaseLawyer", back_populates="case", cascade="all, delete-orphan")
    relations_as_source = relationship("CaseRelation", foreign_keys="CaseRelation.source_case_id", cascade="all, delete-orphan")
    relations_as_target = relationship("CaseRelation", foreign_keys="CaseRelation.target_case_id", cascade="all, delete-orphan")
    stage_logs = relationship("CaseStageLog", back_populates="case", cascade="all, delete-orphan")
    esas_numbers = relationship("CaseEsasNumber", back_populates="case", cascade="all, delete-orphan")
    stage_decisions = relationship("CaseStageDecision", back_populates="case", cascade="all, delete-orphan")
    # Föyler BİLİNÇLİ cascade'siz + passive_deletes="all" (G063): kartın hard
    # delete'i föy bağını sessizce koparmamalı — ORM çocuğun FK'sını NULL'lamaz,
    # karar veritabanınındır ve NOT NULL + ondelete'siz FK yazımı reddeder.
    # Kartın normal silmesi zaten SOFT'tur (deleted_at); föy envanteri korunur.
    foys = relationship("CaseFoy", back_populates="case", passive_deletes="all")


class CaseEsasNumber(Base):
    """Bir davanın esas numarası TARİHÇESİ (FAZ F şartnamesi §1.3, G045).

    Esas numarası bir öznitelik değil, aşamalar boyunca değişen kimlik geçmişidir:
    görevsizlik/yetkisizlik/bozma sonrası numara değişir ve **eski numarayla arama
    yapılır** (teslim paketindeki "Eski Dosya No" sütunu 616 satırda tam olarak
    bunu taşıyor: `"2017/325 - 2024/145"`).

    `cases.esas_no` KALIR ama TÜRETİLMİŞ değerdir: `is_current = True` satırının
    kopyası. Tek yazma yolu `case_manager.sync_current_esas`; sıcak yollar (liste,
    kart) tek kolondan okumaya devam eder, arama bu index'li tabloya vurur.

    Kolonlarda `index=True` BİLİNÇLİ YOK (G042 dersi): `id` üzerindeki index PK
    ikizi olurdu, `case_id`yi ise `uq_case_esas` (case_id, esas_no, stage) zaten
    ÖNEK kolonuyla karşılar — FK taramaları için ayrı index mükerrer olurdu
    (G043'te `case_relations.source_case_id` için verilen kararın aynısı).
    Kısıt ve index'ler `database._MIGRATIONS`'ta ayrı bir `("index", ...)` op'unda
    durur; `("table", ...)` op'una gömülselerdi hiç koşmazlardı (G041).
    """
    __tablename__ = "case_esas_numbers"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    esas_no = Column(String(50), nullable=False)
    # YEREL | ISTINAF | TEMYIZ | KARAR_DUZELTME | ONCEKI (case_manager.ESAS_STAGES)
    stage = Column(String(20), nullable=False)
    court = Column(String(200), nullable=True)
    # Dava başına EN FAZLA BİR True — kısmi unique index'le zorlanır
    # (uq_case_esas_current). cases.esas_no bu satırın kopyasıdır.
    is_current = Column(Boolean, nullable=False, default=False)
    source = Column(String(100), nullable=True)   # provenance: "add_case", "HUKDOK_TESLIM_*"…
    created_at = Column(DateTime(timezone=True), default=func.now())

    case = relationship("Case", back_populates="esas_numbers")


class CaseStageDecision(Base):
    """Bir davanın aşama/karar TARİHÇESİ (KARAR_ASAMALARI tasarım paketi 17.08, G062).

    Karar künyesi `cases` üzerinde aşama başına TEK SLOT'tur (yerel karar_no/
    karar_tarihi, istinaf_* 8, temyiz_* 9, karar_duzeltme_* 6 alan); aynı
    aşamanın ikinci kararı eskisini ezer. Kanıt vakası id-2271: Danıştay 2023
    Bozma + 2026 Onama tek slota sığmaz. Master analizinde 915 föyün %10,9'u
    çok aşamalı. Slot alanları prod'da bugün 0 dolu (18.08 ölçümü) → veri göçü
    yok, tablo sıfırdan doğar.

    Desen `case_esas_numbers`ın (G045/G049) karar ikizidir: aşama etiketli
    satırlar + TEK yazma yolu (`managers/stage_decisions.py`) + türetilmiş
    tek-slot fotoğraf. `cases`teki slot kolonları KALIR ama o aşama tarihçeden
    yazıldığı andan itibaren TÜRETİLMİŞTİR: her stage'in EN YÜKSEK sira_no'lu
    satırının kopyası ("son aşama fotoğrafı").

    * `stage` etiket seti `case_esas_numbers` ile AYNI, ONCEKI HARİÇ — ONCEKI
      yalnız esas numarası kavramıdır (`stage_decisions.DECISION_STAGES`).
    * `sira_no` — aynı aşamanın kaçıncı kararı; SIRALAMA BUNUNLA yapılır,
      tarihle DEĞİL (tasarım paketi: 170 föyde karar tarihleri güvenilmez).
    * `karar_durumu` — stage'in G060 resmi listesinin ADI (YEREL →
      local_decisions, ISTINAF → appeal_decisions, TEMYIZ →
      cassation_decisions, KARAR_DUZELTME → revision_decisions); kapalı havuz
      denetimi tek yazma yolundadır.
    * `dogrulama_durumu` — tahmin yasağının taşıyıcısı: UYAP | BELGE |
      TURETILDI | BELIRSIZ. server_default da BELIRSIZ: tek yazma yolunu
      atlayan ham INSERT bile damgasız satır bırakamaz.
    * `kaynak_id` — bu karar hangi karardan doğdu (bozma → yeni yerel karar).
      ondelete=SET NULL: kaynak silinirse türeyen kayıt öksüz kalır, SİLİNMEZ.

    Kolonlarda `index=True` BİLİNÇLİ YOK (G042 dersi): `id` PK ikizi olurdu,
    `case_id`yi `uq_case_stage_decision` (case_id, stage, sira_no) ÖNEK
    kolonuyla karşılar; `kaynak_id`nin FK index'i (G043 kuralı: index'siz FK
    kolonu kalmaz) ve unique kısıt `database._MIGRATIONS`'ta ayrı bir
    `("index", ...)` op'undadır (G041 kuralı) — tablo op'una gömülse hiç
    koşmazlardı; tabloyu create_all yaratır.
    """
    __tablename__ = "case_stage_decisions"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    # YEREL | ISTINAF | TEMYIZ | KARAR_DUZELTME (stage_decisions.DECISION_STAGES)
    stage = Column(String(20), nullable=False)
    sira_no = Column(Integer, nullable=False)
    mahkeme = Column(String(200), nullable=True)          # istinaf_mahkemesi ile aynı sınır
    esas_no = Column(String(50), nullable=True)           # aşamanın esas no'su (kart kimliğine dokunmaz)
    karar_no = Column(String(50), nullable=True)
    karar_tarihi = Column(Date, nullable=True)
    karar_durumu = Column(String(100), nullable=True)     # G060 kapalı listesinin adı
    teblig_tarihi = Column(Date, nullable=True)
    basvuran_taraf = Column(String(50), nullable=True)    # istinaf_basvuran_taraf ile aynı sınır
    aciklama = Column(String, nullable=True)
    dogrulama_durumu = Column(String(20), nullable=False, default="BELIRSIZ", server_default="BELIRSIZ")
    kaynak_id = Column(Integer, ForeignKey("case_stage_decisions.id", ondelete="SET NULL"), nullable=True)
    source = Column(String(100), nullable=True)           # provenance: "takip-paneli", "HUKDOK_TESLIM_*"…
    created_at = Column(DateTime(timezone=True), default=func.now())

    case = relationship("Case", back_populates="stage_decisions")


class CaseFoy(Base):
    """SistemNo → kart + müvekkil FÖY eşlemesi (kullanıcı kararı 18.08, G063).

    Karar şudur: **dava TEK kart kalır, müvekkiller kartın altında; kart föy
    bazında BÖLÜNMEZ.** Ama karşı tarafın tüm teslimleri (ilk yükleme, partili
    ek teslimler, düzeltme listeleri, karar aşamaları sayfası) sonsuza dek
    SistemNo anahtarlıdır ve bir kartta birden çok SistemNo yaşar — ön analiz:
    1.211 mevcut kart 2+ föyü birleşik taşıyor, TKU'da 1.537 çok üyeli grup /
    4.030 satır. `cases.sistem_no` TEK kolonu bunu taşıyamaz; bu tablo kartın
    kimliğini bölmeden föyleri kartın altına asar.

    `cases.sistem_no`/`cases.tku_no` kolonlarına BU TURDA DOKUNULMADI (prod'da
    ikisi de 0 dolu); nihai tekilleştirme FAZ F aktarım turunun işidir.

    * `sistem_no` UNIQUE — aktarımın idempotency anahtarı: teslim partiler
      hâlinde ve düzeltme listeleriyle tekrar tekrar gelecek, aynı föy ikinci
      kez yazılınca satır İKİLENMEZ, güncellenir (`managers/foy_map.upsert_foy`).
      Kısıt `("index", ...)` op'unda (G041); modelde `unique=True` YOK —
      create_all yolu ile migrasyon yolu aynı ADI üretsin diye.
    * `case_id` FK'sında `ondelete` BİLİNÇLİ VERİLMEDİ (NO ACTION/RESTRICT):
      dava soft-delete kullanır (`deleted_at`), hard-delete föy bağını sessizce
      koparmamalı — belge koruma şartının (18.08) kardeş kuralı.
    * `case_party_id` FK'sı `ondelete="RESTRICT"`: `CaseDocument.case_party_id`
      SET NULL tuzağının tekrarı istenmiyor. Bir tarafın silinmesi föyün hangi
      müvekkile ait olduğunu sessizce unutturamaz; silme ENGELLENİR.
    * Per-föy EK alanlar (dava değeri, son durum, hizmet türü…) bu turda
      AÇILMADI — kolon seti FAZ F tam eşleme turunda 68 sütunluk eşleme
      tablosuyla kararlaştırılır (YAGNI). Çekirdek = kimlik + bağ; föyler arası
      FARKLI kalan değerlerin (10.08 ölçümü: Hasar No 144, Dava Değeri 211, Son
      Durum 332, Durum 137 grupta farklı) taşıyıcısı olacak satır BURADA hazır.

    Kolonlarda `index=True` BİLİNÇLİ YOK (G042 dersi): `id` index'i PK ikizi
    olurdu; `sistem_no`/`case_id`/`case_party_id`/`tku_no` index'leri
    `database._MIGRATIONS`'ta ayrı bir `("index", ...)` op'undadır — tablo
    op'una gömülselerdi HİÇ koşmazlardı (G041), tabloyu create_all yaratır.
    """
    __tablename__ = "case_foys"

    id = Column(Integer, primary_key=True)
    # Micro Kolay Ofis kayıt kimliği (SSTMN-9425 gibi) — teslimlerin anahtarı
    sistem_no = Column(String(50), nullable=False)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    case_party_id = Column(
        Integer, ForeignKey("case_parties.id", ondelete="RESTRICT"), nullable=True
    )
    tku_no = Column(String(50), nullable=True)     # olay/vaka grup anahtarı (TKU-784)
    hasar_no = Column(String(100), nullable=True)  # föyler arası 144 grupta FARKLI
    source = Column(String(100), nullable=True)    # hangi teslim paketi yazdı
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

    case = relationship("Case", back_populates="foys")
    case_party = relationship("CaseParty", foreign_keys=[case_party_id])


class CaseStageLog(Base):
    __tablename__ = "case_stage_logs"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(String(50), nullable=False)
    changed_at = Column(DateTime(timezone=True), default=func.now())
    changed_by = Column(String(100), nullable=True)
    source = Column(String(20), default="MANUAL")   # "MANUAL" | "AUTO_DOCUMENT"
    note = Column(String, nullable=True)

    case = relationship("Case", back_populates="stage_logs")


class CaseRelation(Base):
    __tablename__ = "case_relations"

    id = Column(Integer, primary_key=True, index=True)
    source_case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    target_case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    relation_type = Column(String(30), nullable=False, default="ILGILI")
    # ICRA_CEZA | ICRA_HUKUK | ASIL_TEMYIZ | ASIL_YENIDEN | BIRLESEN | AYRISTIRILAN | ILGILI
    note = Column(String, nullable=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())

    source_case = relationship("Case", foreign_keys=[source_case_id], overlaps="relations_as_source")
    target_case = relationship("Case", foreign_keys=[target_case_id], overlaps="relations_as_target")


class CaseHistory(Base):
    __tablename__ = "case_history"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    field_name = Column(String, nullable=False) # e.g. "esas_no", "court", "status"
    old_value = Column(String)
    new_value = Column(String)
    changed_at = Column(DateTime(timezone=True), default=func.now())
    # Faz 7 imzası: kim + hangi kaynaktan ("intake-enrich: tensip.pdf",
    # "auto-enrich"…). Elle düzenlemelerde NULL kalabilir (legacy davranış).
    changed_by = Column(String(200), nullable=True)
    source = Column(String(300), nullable=True)

    case = relationship("Case", back_populates="history")

class CaseParty(Base):
    __tablename__ = "case_parties"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True) # Linked if it's a registered client
    
    name = Column(String, nullable=False)
    role = Column(String, nullable=False) # "Davacı", "Davalı", etc.
    party_type = Column(String, nullable=False) # "CLIENT" (registered), "COUNTER", "THIRD"
    birth_year = Column(Integer, nullable=True)
    gender = Column(String, nullable=True)
    tc_no = Column(String, nullable=True) # T.C. Kimlik No (tanıdık sorgu / çıkar çatışması kontrolü)
    
    case = relationship("Case", back_populates="parties")
    client = relationship("Client", back_populates="case_parties")

class CaseLawyer(Base):
    __tablename__ = "case_lawyers"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    lawyer_id = Column(Integer, ForeignKey("lawyers.id", ondelete="SET NULL"), nullable=True) # Linked if registered
    
    name = Column(String, nullable=False) # Actual name representation
    
    case = relationship("Case", back_populates="lawyers")
    lawyer = relationship("Lawyer")

class Lawyer(Base):
    __tablename__ = "lawyers"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False) # e.g. "AGH"
    name = Column(String, nullable=False) # e.g. "Ayşe..."
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0) # Ordering
    tc_no = Column(String, nullable=True)    # T.C. Kimlik No
    sicil_no = Column(String, nullable=True) # Baro Sicil No
    gorev = Column(String, nullable=True)    # AVUKAT / DIŞ AVUKAT
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(String, nullable=True)
    city = Column(String, nullable=True)     # Şehir listesinden seçilir (Client.il ile aynı sözlük)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class Client(Base):
    __tablename__ = "clients" # Muvekkiller

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False) # Müvekkil adı (unique değil, TC/cari_kod ile ayırt edilir)
    source_ids = Column(String) # JSON or Comma-separated list of SharePoint IDs
    active = Column(Boolean, default=True)
    tenant_id = Column(String, index=True, nullable=True)  # Azure AD tenant (tid). NULL = paylaşılan legacy

    # Soft-delete (active'e DOKUNULMAZ — active kullanıcı-düzenlenebilir "pasif cari" alanı)
    deleted_at    = Column(DateTime(timezone=True), nullable=True)
    deleted_by    = Column(String(200), nullable=True)
    delete_reason = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())
    
    # New Fields for Client Management
    tc_no = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    mobile_phone = Column(String, nullable=True) # New field for Cep Telefonu
    address = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    contact_type = Column(String, default="Client") # "Client" or "Other"
    client_type = Column(String, nullable=True) # "Individual" or "Corporate"
    category = Column(String, nullable=True) # e.g. "Sigorta", "Özel", "Doktor"
    cari_kod = Column(String, nullable=True) # 6 haneli sicil no
    birth_year = Column(Integer, nullable=True)
    gender = Column(String, nullable=True)
    specialty = Column(String, nullable=True)

    # Yeni alanlar — Excel import (cari_mikro_guncellendi.xlsx)
    il                  = Column(String, nullable=True)   # Col 8  - İl / Şehir
    sektor              = Column(String, nullable=True)   # Col 10 - Sektörü
    yevmiye_no          = Column(String, nullable=True)   # Col 13 - Yevmiye No
    noterlik            = Column(String, nullable=True)   # Col 14 - Noterlik adı
    vekaletname_tarihi  = Column(Date,   nullable=True)   # Col 15 - Veriliş tarihi
    vekil_avukatlar     = Column(String, nullable=True)   # Col 16 - AD SOYAD;AD SOYAD formatı
    gecerlilik_tarihi   = Column(Date,   nullable=True)   # Col 17 - Geçerlilik tarihi
    vekalet_no          = Column(String, nullable=True)   # Col 18 - Vekalet No
    buro_vekalet_no     = Column(String, nullable=True)   # Col 19 - Büro Vekalet No

    # When a client is deleted, set client_id to NULL in case_parties (don't delete the party row)
    case_parties = relationship("CaseParty", back_populates="client", passive_deletes=True)
    policies = relationship("ClientPolicy", back_populates="client", cascade="all, delete-orphan", passive_deletes=True)


class ClientPolicy(Base):
    """Hekim (client) başına kalıcı poliçe kaydı — otonom dava açma Faz 3.

    Poliçe bir kez kaydedilir, sonraki davalarda otomatik önerilir; dönem
    çakışması uyarısı kalıcı veriyle çalışır (plan Kararlar #3). Kayıtlar
    intake sihirbazının analiz çıktısından beslenir veya müvekkil kartından
    elle girilir. Tenant'ı client üzerinden taşır (ortak havuz modeli).
    """
    __tablename__ = "client_policies"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)

    police_no = Column(String(100), nullable=True)          # yenileme no dahil ("92804147/4")
    police_turu = Column(String(20), nullable=True)         # ZORUNLU | TAMAMLAYICI | DIGER
    sigorta_sirketi = Column(String(200), nullable=True)
    baslangic_tarihi = Column(Date, nullable=True)          # poliçe dönemi başı
    bitis_tarihi = Column(Date, nullable=True)              # poliçe dönemi sonu
    retroaktif_tarihi = Column(Date, nullable=True)         # geçmişe etkinlik — teminatın asıl başlangıcı
    sigortali_kurum = Column(String(300), nullable=True)    # hekimin bağlı olduğu kurum / sigorta ettiren
    teminat_limiti = Column(Numeric(precision=20, scale=2), nullable=True)  # olay başına (TL)

    source_document = Column(String, nullable=True)         # beslendiği belge adı; elle girişte NULL
    created_by = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

    client = relationship("Client", back_populates="policies")

class DocType(Base):
    __tablename__ = "doctypes" # BelgeTuru

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False) # "DAVA-DLK"
    name = Column(String, nullable=False) # "Dava Dilekçesi"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0) # Ordering
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class Status(Base):
    __tablename__ = "statuses" # Durum

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False) # "B"
    name = Column(String, nullable=False) # "Büro"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0) # Ordering
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class EmailRecipient(Base):
    __tablename__ = "email_recipients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class CaseSubject(Base):
    __tablename__ = "case_subjects" # Dava Konulari

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False) # "BOSANMA"
    name = Column(String, nullable=False) # "Boşanma Davası"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0) # Ordering
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class FileType(Base):
    __tablename__ = "file_types"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)  # e.g. "Ceza"
    name = Column(String, nullable=False)                           # e.g. "Ceza"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class CourtType(Base):
    __tablename__ = "court_types"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, index=True, nullable=False)               # e.g. "AGIR-CEZA"
    name = Column(String, nullable=False)                           # e.g. "AĞIR CEZA MAHKEMESİ"
    parent_code = Column(String, nullable=False)                    # e.g. "Ceza"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class PartyRole(Base):
    __tablename__ = "party_roles"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)  # e.g. "DAVACI"
    name = Column(String, nullable=False)                           # e.g. "Davacı"
    role_type = Column(String, default="MAIN")                      # "MAIN" or "THIRD"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class BureauType(Base):
    __tablename__ = "bureau_types"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)  # e.g. "ALEYHE"
    name = Column(String, nullable=False)                           # e.g. "ALEYHE"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class City(Base):
    __tablename__ = "cities"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)  # e.g. "ISTANBUL"
    name = Column(String, nullable=False)                           # e.g. "İstanbul"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class Specialty(Base):
    __tablename__ = "specialties"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)  # e.g. "ACIL-TIP"
    name = Column(String, nullable=False)                           # e.g. "Acil Tıp"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class ClientCategory(Base):
    __tablename__ = "client_categories"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)  # e.g. "DOKTOR"
    name = Column(String, nullable=False)                           # e.g. "Doktor"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class FileStatus(Base):
    __tablename__ = "file_statuses"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)  # e.g. "BILIRKISIDE"
    name = Column(String, nullable=False)                           # e.g. "Bilirkişide"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class AppSetting(Base):
    """Uygulama düzeyi anahtar-değer ayarları (yönetici panelinden aç/kapa).

    Referans listelerinden farklı: satırlar seed'lenmez, yalnız yönetici bir
    ayarı DEĞİŞTİRDİĞİNDE yazılır; satır yoksa kodun tanımladığı varsayılan
    geçerlidir (services/app_settings.py::SETTINGS_REGISTRY — tek kayıt yolu da
    orasıdır, tablo doğrudan yazılmaz). Değerler string saklanır ("true"/"false");
    tip yorumu registry'dedir.
    """
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)   # e.g. "client_notice_enabled"
    value = Column(String, nullable=False)                          # "true" / "false"
    updated_by = Column(String, nullable=True)                      # değiştiren yöneticinin e-postası
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class AllegedFault(Base):
    """İddia Edilen Kusur — KAPALI referans listesi (FAZ F şartnamesi §1.1).

    `cases.iddia_edilen_kusur` bu listenin ADINI denormalize taşır; diğer 13
    liste ile aynı mekanizma (LIST_REGISTRY + DEPENDENCIES), yeni bir yol yok.
    Karşı tarafın cevabı listeyi "hiçbir branşta değişmeyen 7 değer" olarak
    tanımlıyor ama DEĞERLERİ paket içinde gelmedi → seed BİLİNÇLİ olarak boş;
    7 değer geldiğinde yönetim panelinden/seed'den doldurulur (bkz. seed_data).
    """
    __tablename__ = "alleged_faults"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)   # e.g. "TESHIS-HATASI"
    name = Column(String, nullable=False)                            # e.g. "Teşhis Hatası"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())


class AppealingParty(Base):
    """İstinaf Başvuran Taraf — kapalı liste (Davacı / Davalı / Her İki Taraf).

    Temyizle simetri (şartname §1.1, S5). `cases.istinaf_basvuran_taraf` adı
    denormalize taşır; değerler şartnamede yazılı olduğu için seed'lidir.
    """
    __tablename__ = "appealing_parties"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)   # e.g. "DAVACI"
    name = Column(String, nullable=False)                            # e.g. "Davacı"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())


# Karar sonucu RESMİ listeleri (G060) — kaynak: 10.08 teslim paketinin
# DEGER_HAVUZLARI sayfası (KARAR_ASAMALARI tasarım paketinin "kapalı havuzlar"
# değişmezi). Dördü de appealing_parties deseninin kopyasıdır; ad, `cases`in
# ilgili aşama durum kolonunda denormalize taşınır (DEPENDENCIES). Kod ASCII
# ve DEĞİŞMEZ kimliktir (üretim kuralı: seed_data._karar_kodu).

class LocalDecision(Base):
    """Yerel Karar Durumu — kapalı resmi liste (28 değer, seed'li).

    `cases.yerel_karar_durumu` adı denormalize taşır. `cases.karar_turu`
    (kaba 6'lık küme) AYRI bir alandır ve bu listeye BAĞLI DEĞİLDİR (G060).
    """
    __tablename__ = "local_decisions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)   # e.g. "RED_ESASTAN"
    name = Column(String, nullable=False)                            # e.g. "Red/Esastan"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())


class AppealDecision(Base):
    """İstinaf Karar Durumu — kapalı resmi liste (3 değer, seed'li).

    `cases.istinaf_karar_durumu` adı taşır. İstinaf BAŞVURAN tarafı tutan
    `appealing_parties`ten ayrı bir listedir.
    """
    __tablename__ = "appeal_decisions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)   # e.g. "KALDIRMA"
    name = Column(String, nullable=False)                            # e.g. "Kaldırma"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())


class CassationDecision(Base):
    """Temyiz Onama Durumu — kapalı resmi liste (3 değer, seed'li).

    `cases.temyiz_karar_durumu` adı taşır.
    """
    __tablename__ = "cassation_decisions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)   # e.g. "ONAMA"
    name = Column(String, nullable=False)                            # e.g. "Onama"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())


class RevisionDecision(Base):
    """Karar Düzeltme Durumu — kapalı resmi liste (2 değer, seed'li).

    `cases.karar_duzeltme_durumu` adı taşır.
    """
    __tablename__ = "revision_decisions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)   # e.g. "KARAR_DUZELTME_RET"
    name = Column(String, nullable=False)                            # e.g. "Karar Düzeltme Ret"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())


# Belgeleme olayı KAPALI listeleri (G103) — kaynak: veri ekibinin 25.08 ölçümü
# (HUKDOK_BELGELEME_OLAYI_BULGUSU_2026-08-25) + 02.09 kullanıcı kararı.
# İkisi de appealing_parties deseninin kopyasıdır; ad, `cases`in ilgili
# kolonunda denormalize taşınır (DEPENDENCIES). `alleged_faults`un aksine
# SEED'LİDİR: değerler karşı taraf teyidi beklemiyor, bizde sabitlendi
# (bkz. seed_data.EVENT_TYPES / JUDGMENT_ROLES).

class EventType(Base):
    """Olay Türü — kapalı liste (3 değer, seed'li).

    `cases.olay_turu` adı denormalize taşır. KARMA ("Tıbbi + Belgeleme")
    bilinçli: kart alanı tek slot ve ölçümün "yan gerekçe" sınıfında iki tür
    birlikte görülüyor — karma durum açık değerle taşınır, tahminle
    tekilleştirilmez.
    """
    __tablename__ = "event_types"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)   # e.g. "BELGELEME"
    name = Column(String, nullable=False)                            # e.g. "Belgeleme Olayı"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())


class JudgmentRole(Base):
    """Hükümdeki Rol — kapalı liste (4 değer, seed'li).

    Belgeleme olgusunun GÜNCEL kademedeki hükümde oynadığı rol ("saptandı" ≠
    "kazandırdı"); `cases.hukumdeki_rol` adı taşır. E-9/bayat hüküm kuralıyla
    uyumlu: kademe değişince değer düzeltme partisiyle güncellenir.
    """
    __tablename__ = "judgment_roles"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)   # e.g. "YAN-GEREKCE"
    name = Column(String, nullable=False)                            # e.g. "Yan Gerekçe"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())


class HearingDate(Base):
    """Duruşma zaptından çıkarılan bir sonraki duruşma tarihleri."""
    __tablename__ = "hearing_dates"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    hearing_date = Column(Date, nullable=False)
    hearing_time = Column(String(10), nullable=True)  # "09:43" formatında saat
    lawyer_name = Column(String, nullable=True)       # Sorumlu avukat (ajanda filtresi için)
    extracted_from_doc = Column(String, nullable=True) # Kaynak belge adı
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    note = Column(String, nullable=True)

    case = relationship("Case")


class CalendarEvent(Base):
    """Takvime elle eklenen serbest tarih işaretleri (duruşma dışı hatırlatmalar).

    Bir davaya bağlı değildir; ofis genelinde kullanılır. tenant_id NULL ise ortak
    havuzdadır (her iki büro da görür) — mevcut paylaşımlı kayıt modeliyle uyumlu.
    """
    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, nullable=True, index=True)
    title = Column(String, nullable=False)            # "ne olduğu" — kullanıcının yazdığı açıklama
    event_date = Column(Date, nullable=False)
    event_time = Column(String(10), nullable=True)    # "14:30" formatında saat (opsiyonel)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())


class CaseDocument(Base):
    """
    Faz 1: Belgeler ile Davalar arasındaki bağlantıyı tutar.
    Her yüklenen belge bir davaya bağlanır (veya TEST modunda serbest bırakılır).
    """
    __tablename__ = "case_documents"

    id = Column(Integer, primary_key=True, index=True)

    # Dava bağlantısı (nullable: TEST modunda dava seçilmeyebilir)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True, index=True)

    # Dosya bilgileri
    original_filename = Column(String, nullable=False)        # Orijinal yüklenen dosya adı
    stored_filename = Column(String, nullable=False)          # Sistemin verdiği standart ad
    sharepoint_url = Column(String, nullable=True)            # SharePoint'teki tam URL (ileride)
    belge_turu_kodu = Column(String, nullable=True)           # "DAVA-DLK", "KARAR-BLG" vb.
    belge_turu_adi = Column(String, nullable=True)            # "Dava Dilekçesi" (okunabilir)
    ai_summary = Column(String, nullable=True)                # Gemini'nin kısa özeti
    muvekkil_adi = Column(String, nullable=True)              # İlgili müvekkil (deprecated: case_party_id kullan)
    case_party_id = Column(Integer, ForeignKey("case_parties.id", ondelete="SET NULL"), nullable=True)  # NULL → tüm dava, dolu → o tarafa ait
    avukat_kodu = Column(String, nullable=True)               # Sorumlu avukat kodu
    esas_no = Column(String, nullable=True)                   # Belgede geçen esas no

    # Bağlantı modu
    # "LINKED"  → Gerçek bir davaya bağlandı
    # "TEST"    → Test modunda yüklendi, dava seçilmedi
    # "UNLINKED"→ Analiz tamamlandı ama dava bulunamadı / kullanıcı seçmedi
    link_mode = Column(String, default="UNLINKED", nullable=False)

    # Meta
    uploaded_by = Column(String, nullable=True)              # Azure AD kullanıcı adı
    uploaded_at = Column(DateTime(timezone=True), default=func.now())

    # E-posta durumu
    email_sent = Column(Boolean, nullable=True)              # None=gönderilmedi/atlandı, True=başarılı, False=hata
    email_error = Column(String, nullable=True)              # Hata mesajı (email_sent=False ise)

    # Arşiv durumu (Faz 2-C): işlenmiş kopyanın SharePoint yükleme sonucu.
    # pending → kayıt açıldı, yükleme kuyrukta; uploaded → URL commit edildi;
    # failed → deneme(ler) başarısız. Faz 3-A retry kuyruğunun temelidir.
    upload_status = Column(String, default="pending", nullable=True)
    upload_attempts = Column(Integer, default=0, nullable=True)

    # PDF/A dönüşüm katmanı (Faz 3-F, plan 3.8 Katman 2): /confirm'de dönüşüm
    # TÜM yollara rağmen başarısızsa belge kaybolmaz — orijinal KENDİ uzantısıyla
    # arşive gider, kayıt conversion_status='pending' ile açılır, gece job'ı
    # (services/conversion_retry.py) yeniden dener.
    #   NULL      → normal (dönüşüm gerekmedi ya da tamamlandı)
    #   'pending' → gece yeniden denenecek (spool'daki orijinalden)
    #   'failed'  → denemeler tükendi; tek nihai ERROR loglanır, spool dosyası
    #               elle kurtarma için saklanır (conversion_status='pending',
    #               conversion_attempts=0 yapılırsa gece job'ı yeniden dener)
    # KARAR NOTU: upload_status'a yeni değer DEĞİL, ayrı alan — upload_status
    # işlenmiş kopyanın SharePoint yükleme durumudur ve pending belgede
    # orijinalin yüklemesini izlemeye devam eder (dik boyutlar; belge kartı
    # göstergesi ve idx_case_docs_upload_status partial index'i bozulmaz).
    # Hukukbot export'u conversion_status IS NOT NULL kayıtları ingest'e almaz.
    conversion_status = Column(String, nullable=True)
    conversion_attempts = Column(Integer, default=0, nullable=True)
    conversion_spool_path = Column(String, nullable=True)

    # Kullanıcı kimliği (UPN / preferred_username)
    uploaded_by_email = Column(String, nullable=True, index=True)

    # Soft-delete (dava/müvekkil kalıbı): kayıt DB'de kalır, listelerden gizlenir,
    # admin panelinden geri alınır. SharePoint arşiv kopyasına dokunulmaz.
    deleted_at    = Column(DateTime(timezone=True), nullable=True)
    deleted_by    = Column(String(200), nullable=True)
    delete_reason = Column(String, nullable=True)

    # İlişkiler
    case = relationship("Case", back_populates="documents")
    case_party = relationship("CaseParty", foreign_keys=[case_party_id])


class DailyActivityReport(Base):
    """Kullanıcı başına günlük belge yükleme özeti — gece yarısı oluşturulur."""
    __tablename__ = "daily_activity_reports"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, nullable=True, index=True)
    user_email = Column(String, nullable=False, index=True)   # preferred_username (UPN)
    report_date = Column(Date, nullable=False)                # Raporlanan gün (dün)
    total_documents = Column(Integer, default=0)
    mailed_documents = Column(Integer, default=0)             # email_sent=True
    unmailed_documents = Column(Integer, default=0)           # email_sent=None (kullanıcı atladı)
    error_documents = Column(Integer, default=0)              # email_sent=False (hata)
    unmailed_doc_ids = Column(String, nullable=True)          # JSON liste: mailsiz belge id'leri
    mailed_doc_ids = Column(String, nullable=True)            # JSON liste: e-posta ile gitmiş belge id'leri
    error_doc_ids = Column(String, nullable=True)             # JSON liste: hata almış belge id'leri
    is_acknowledged = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())


class UploadOutbox(Base):
    """
    SharePoint arşiv yüklemelerinin kalıcı kuyruğu (Faz 3-A, plan madde 3.1).

    /confirm yanıtı dönmeden önce her arşiv yüklemesi (ham + islenmis) için
    payload spool dizinine kopyalanır ve buraya pending satır yazılır; yükleme
    işi services/upload_queue.py'deki tek worker thread'inde koşar. Süreç ölse
    bile satır + spool dosyası kalır, açılıştaki reconcile kaldığı yerden dener.

    Not: Faz 2-C backfill'inden gelen eski "failed" belgeler (upload_status
    kolonundaki 50 kayıt) bu kuyruğun KAPSAMI DIŞINDADIR — kaynak dosyaları
    /confirm'den 30 sn sonra silindiği için sunucuda yeniden yüklenecek içerik
    yok; retry yalnız spool dosyası olan outbox satırları için mümkündür.
    """
    __tablename__ = "upload_outbox"

    id = Column(Integer, primary_key=True, index=True)
    # Ham satırlarda da izlenebilirlik için dolu; belge upload_status'unu yalnız
    # "islenmis" satırları günceller. CASCADE: belge hard-delete edilirse
    # (bugün yok, soft-delete var) kuyruk satırı da düşer.
    document_id = Column(
        Integer,
        ForeignKey("case_documents.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    kind = Column(String(20), nullable=False)                 # "ham" | "islenmis"
    spool_path = Column(String, nullable=True)                # payload kopyası; janitor temizlerse NULL
    target_filename = Column(String, nullable=False)
    target_folder = Column(String, nullable=False)
    # "pending"  → yükleme bekliyor / retry'da (worker tarar)
    # "uploaded" → SharePoint'e gitti, spool dosyası silindi
    # "failed"   → MAX_ATTEMPTS tüketildi ya da spool kayıp; nihai (ERROR loglanır)
    status = Column(String(20), default="pending", nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True)  # NULL = hemen dene
    last_error = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    done_at = Column(DateTime(timezone=True), nullable=True)  # uploaded/failed'a geçiş anı

    document = relationship("CaseDocument")


class ConfirmReceipt(Base):
    """
    /confirm idempotency kaydı (Faz 3-D, plan madde 3.5).

    Anahtar process_id'dir: /process her sihirbaz oturumu için tekil UUID
    üretir ve frontend /confirm'e (retry'lar dahil) hep aynısını gönderir.
    504 sonrası kullanıcı retry'ı bugüne dek pipeline'ı ikinci kez koşturup
    mükerrer belge + mükerrer e-posta üretiyordu (nginx.conf'ta "mukerrer
    kayit kaynagi" olarak belgeli).

    Akış (services/confirm_idempotency.py):
      - /confirm başında PK'ya INSERT denenir → geçerse pipeline koşar.
      - PK çakışırsa: satır "completed" ise saklanan yanıt AYNEN döndürülür
        (pipeline koşmaz), "in_progress" ise 409 "işlem sürüyor" dönülür.
      - Başarıda yanıt JSON'u satıra yazılır; belge YARATILMADAN patlayan
        istek satırını siler (retry serbest kalır).

    Kayıt DB'de (süreç içinde değil) — bilinçli (3-E kararı): uvicorn restart
    ve gelecekteki --workers 2 geçişinde worker'lar arası tutarlı kalır;
    süreç içi bir dict ikisinde de idempotensi kaybederdi.
    """
    __tablename__ = "confirm_receipts"

    # /process'in ürettiği UUID (36 hane); PK = eşzamanlı çift gönderim kilidi
    process_id = Column(String(64), primary_key=True)
    # İstek sahibinin UPN'i — yanıt yalnız sahibine replay edilir
    owner = Column(String(320), nullable=True)
    status = Column(String(20), default="in_progress", nullable=False)  # in_progress | completed
    # completed'da /confirm yanıtının JSON'u; replay bunun aynısını döndürür
    response_json = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())


class ExportOutbox(Base):
    """
    Hukukbot aktarımının kaynağı (bkz. docs/hukukbot-aktarim/PLAN.md §1).

    Satır YALNIZCA SharePoint upload'ı başarıyla bitip sharepoint_url DB'ye
    yazıldıktan sonra açılır (hook Faz 3'te, document_pipeline.py) — böylece
    outbox id sırası = aktarılabilirlik sırası olur ve async upload ile
    reconcile cursor'ının yarışı ortadan kalkar (BULGULAR #1).
    """
    __tablename__ = "export_outbox"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(
        Integer,
        ForeignKey("case_documents.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    # "pending"   → aktarım bekliyor (hukukbot reconcile bunları sorar)
    # "delivered" → hukukbot işledi, ACK geldi
    # "failed"    → hukukbot N denemeden sonra NACK'ledi; manuel inceleme (BULGULAR #9)
    status = Column(String(20), default="pending", nullable=False, index=True)
    attempts = Column(Integer, default=0, nullable=False)
    nack_reason = Column(String, nullable=True)               # NACK'teki {reason}
    created_at = Column(DateTime(timezone=True), default=func.now())
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    document = relationship("CaseDocument")


class Notification(Base):
    """
    Uygulama içi bildirim (G081) — `DailyActivityReport` deseninin genelleştirilmişi:
    kullanıcı başına satır + okundu işareti.

    KANAL: yalnız uygulama içi. E-posta gönderimi bu sistemin parçası DEĞİLDİR
    (kullanıcı kararı, 2026-08-20) — burada satır açılır, kullanıcı uygulamada görür.
    `daily_activity_reports` AYRI mekanizmadır ve bu tablo onu devralmaz.

    `dedupe_key` YAZMA YOLUNUN IDEMPOTENCY ANAHTARIDIR: aynı anahtarla ikinci
    çağrı satır İKİLEMEZ, mevcut kaydın id'sini döndürür (tek yazma yolu
    `services/notifications.create_notification`). Gece tarayıcısı aynı işi her
    gece yeniden görecek — anahtar "aynı olayın aynı gün tekrarı" kapsamında
    seçilir. NULL bırakılırsa dedupe uygulanmaz (Postgres UNIQUE index'i çok
    NULL'a izin verir) — bilinçli tekrar üretilebilen bildirimler için.

    `case_id`/`document_id` `ondelete="SET NULL"`: silinen dava/belge bildirimi
    ÖKSÜZ bırakır, SİLMEZ — bildirim kullanıcıya gösterilmiş bir olaydır ve
    bağlamı kaybolsa da kaydı kalmalıdır (CASCADE olsaydı okunmamış uyarı
    sessizce yok olurdu).

    Index'ler modelde DEĞİL migrasyonda: tabloyu `create_all` yarattığı için
    ("table", ...) op'u ölü kod olur; kısıt/index koşulsuz koşan ("index",
    "notifications", ...) op'una yazılır (G041 kuralı, database.py madde 37).
    """
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=True)              # Azure AD tenant (tid); NULL = paylaşımlı havuz
    recipient_email = Column(String(320), nullable=False)  # DAİMA küçük harf (yazma yolu normalize eder)
    type = Column(String(50), nullable=False)              # "durusma_yaklasti", "eksik_alan" vb.
    severity = Column(String(20), nullable=False, default="info", server_default="info")
    title = Column(String(300), nullable=False)
    body = Column(String, nullable=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True)
    document_id = Column(Integer, ForeignKey("case_documents.id", ondelete="SET NULL"), nullable=True)
    due_date = Column(Date, nullable=True)                 # Bildirimin işaret ettiği tarih (duruşma vb.)
    dedupe_key = Column(String(200), nullable=True)        # UNIQUE (migrasyon) — idempotency anahtarı
    read_at = Column(DateTime(timezone=True), nullable=True)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
