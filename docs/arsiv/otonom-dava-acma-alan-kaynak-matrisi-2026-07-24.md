# Otonom Dava Açma — Alan-Kaynak Matrisi (Faz 0)

*Tarih: 2026-07-24 · Eş dosyalar: [geliştirme planı](otonom-dava-acma-gelistirme-plani-2026-07-24.md), [hazırlık raporu](otonom-dava-acma-hazirlik-raporu-2026-07-24.md)*

Dava açılışı anında elde olabilecek belgeler: **dava dilekçesi, poliçe** (kullanıcının
vereceği çekirdek), tensip zaptı, tebligat mazbatası/üst yazısı, vekaletname, sigorta
görevlendirme/atama yazısı, UYAP tevzi formu/dosya kapağı. DB = mevcut veritabanı
(müvekkil, avukat, geçmiş dava kayıtları, izinli listeler).

## Alan → kaynak tablosu

| Dava kartı alanı | Birincil kaynak | Destek / çapraz kontrol | Dilekçe+poliçe ile durum |
|---|---|---|---|
| `esas_no` | **Tensip zaptı** veya tebligat üst yazısı (kesin) | Tebliğ edilen dilekçe nüshasındaki mahkeme kaşesi; regex | ⚠ Riskli — dilekçe esas no almadan yazılır; kaşesiz nüshada bulunamaz |
| `court` (mahkeme) | Tensip/tebligat başlığı (**daireli** tam ad) | Dilekçe hitabı ("… MAHKEMESİNE" — çoğu kez dairesiz); DB'deki mevcut dava adlarıyla fuzzy normalize | ⚠ Kısmi — dilekçeden daire numarası çıkmayabilir |
| `opening_date` | Tensip zaptı / UYAP tevzi formu | Dilekçe tarihi (yaklaşık) | ⚠ Yaklaşık değer kalır |
| `file_type` (yargı türü) | Mahkeme adından türetme (dilekçe yeterli) | DB izinli liste (Hukuk/Ceza/İdari…) | ✓ |
| `sub_type` (mahkeme türü) | Mahkeme adından (Asliye Hukuk, Tüketici, İdare…) | DB izinli liste | ✓ |
| `sub_type_extra` (uzmanlık; RİNOPLASTİ vb.) | Dilekçe olay anlatımı | DB `specialties` listesi + müvekkil geçmişi prior'ı | ✓ |
| `subject` (dava konusu) | Dilekçe KONU/TALEP bölümü | DB `caseSubjects` listesine eşleme | ✓ |
| Taraflar (ad + rol) | Dilekçe başlık bloğu (DAVACI:/DAVALI:) | Tensip taraf listesi; poliçe sigortalısı; vekaletname; DB FlashText müvekkil taraması + tanıdık sorgu | ✓ |
| Taraf `tc_no` | Vekaletname (kesin); dilekçe başlığı (davacı tarafta genelde var) | DB client kaydı | ⚠ Davalı/müvekkil TC'si dilekçede olmayabilir |
| Taraf `party_type` (CLIENT/COUNTER) | Belgeden çıkmaz — **DB müvekkil eşleşmesi** | Poliçe sigortalısı = müvekkil teyidi; atama yazısı muhatabı | ✓ (DB + poliçe birlikte yeterli) |
| `maddi_tazminat` / `manevi_tazminat` | Dilekçe SONUÇ ve İSTEM (harca esas değer) | — (poliçedeki **teminat limitiyle karıştırılmamalı**) | ✓ |
| `responsible_lawyer_name` | Hiçbir belgede yok | Atama yazısı muhatabı; DB müvekkil geçmişi prior'ı; **kullanıcı seçer** | ✗ Kullanıcı girişi |
| `uyap_lawyer_name` + `lawyers` | Vekaletname vekil listesi ∩ büro avukatları | DB `client.vekil_avukatlar` alanı | ⚠ Vekaletname yoksa DB'den öneri |
| `tracking_no` (Ofis No) | — (belge değil) | **DB**: client-sequence + kategori önceliği (mevcut mantık) | ✓ DB üretir |
| `status` | — | Sabit DERDEST önerisi (açık soru #1) | ✓ |
| `acceptance_date` (iş kabul) | Sigorta atama yazısı / e-posta tarihi | Kullanıcı girişi | ✗ Belge gerekli |
| `atama_tarihi` | Sigorta atama/görevlendirme yazısı | — | ✗ Belge gerekli |
| `hasar_dosya_no` | Sigorta atama yazısı / hasar yazışması | Poliçede genelde **yoktur** (hasar açılınca verilir) | ✗ Belge gerekli |
| `hukuk_no` | Sigorta atama yazısı (hukuk birimi no) | — | ✗ Belge gerekli |
| Poliçe no + sigorta şirketi + dönem | **Poliçe** (hekim başına **birden fazla** olabilir — liste olarak toplanır, çoğunluk oyuna girmez) | Atama yazısı; dava tarihi → ilgili poliçe seçimi; **aynı tip poliçelerde dönem çakışması varsa uyarı** | ✓ (dava kartında ayrı alan yok → notes'a; sigorta şirketini COUNTER taraf teyidi için kullanırız) |
| Tebliğ tarihi (cevap süresi!) | Tebligat mazbatası | UYAP | ✗ — dava kartında alanı yok ama **cevap süresi hesabı için kritik**; notes'a yazılması önerilir |
| `bureau_type` (DR ÖZEL/LEXİS…) | Belgede yok | Sigorta şirketi / müvekkil kategorisi prior'ı; kullanıcı seçer | ✗ Kullanıcı girişi |
| `notes` | AI özeti (tüm belgeler) | — | ✓ |
| `klasor_no_2`, `service_type` | Eski sistem alanları — intake kapsamı dışı | — | — |
| Mükerrer dava kontrolü | — | **DB** `case_matcher.find_matching_case` | ✓ DB |

## Sonuç: önerilen belge seti

Dilekçe + poliçe çekirdeği iyi ama üç kalem eksik kalıyor. Demetlere şunları da
eklemek çıkarım kalitesini belirgin artırır (öncelik sırasıyla):

1. **Tensip zaptı VEYA tebligat üst yazısı** → kesin `esas_no`, daireli mahkeme adı,
   `opening_date`. Bu olmadan üç alan da tahminde kalır.
2. **Sigorta görevlendirme/atama yazısı** → `hasar_dosya_no`, `hukuk_no`,
   `atama_tarihi`, `acceptance_date`; ayrıca sorumlu avukat ipucu.
3. **Vekaletname** → müvekkil TC (kesin), `uyap_lawyer` / vekil listesi.
4. (Varsa) Tebligat mazbatası → tebliğ tarihi (cevap dilekçesi süresi).

## Alan seti taslağı (caseIntakeFields.ts ön hali — Faz 5 öncesi donacak)

| Alan | Widget | Sihirbazda | Zorunlu | Kaynak |
|---|---|---|---|---|
| esas_no | text | ✓ | — | AI + regex |
| court | court (base+daire) | ✓ | ✓ | AI + DB normalize |
| file_type | select | ✓ | ✓ | AI (izinli liste) |
| sub_type | select | ✓ | — | AI (izinli liste) |
| sub_type_extra | text/select | ✓ | — | AI + specialties |
| opening_date | date | ✓ | — | AI |
| subject | select | ✓ | — | AI (caseSubjects) |
| maddi/manevi_tazminat | number | **değerlendirilecek** — dilekçeden güvenilir çıkıyor | — | AI |
| notes | textarea | ✓ (özet ön-dolu) | — | AI |
| lawyers / uyap_lawyer | select | ✓ | — | AI ∩ büro listesi + DB prior |
| responsible_lawyer | select | ✓ | — | DB prior + kullanıcı |
| status | — | sabit DERDEST | — | — |
| tracking_no | readonly | ✓ | ✓ | client-sequence |
| acceptance_date / atama_tarihi / hasar_dosya_no / hukuk_no | — | atama yazısı demete girerse **değerlendirilecek**, aksi halde v1 dışı | — | AI |
| bureau_type / service_type / klasor_no_2 | — | v1 dışı | — | — |

Plandan fark: plan tazminat + hasar/hukuk no alanlarını "hiç girmez" listesine koymuştu;
dilekçe ve atama yazısı bu alanları güvenilir taşıdığı için kalibrasyon sonucuna göre
yeniden değerlendirilecek (şemada mevcutlar, ölçeceğiz).
