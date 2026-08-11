# Otonom Dava Açma — Faz 5 Durum (sihirbaz frontend)

*Tarih: 2026-07-30 · İlk oturum çıktısı. Eş dosyalar: [geliştirme planı](otonom-dava-acma-gelistirme-plani-2026-07-24.md) (İş Kalemi 2), [Faz 4 kickoff](otonom-dava-acma-faz4-baslangic-2026-07-30.md) (backend sözleşmeleri + devir notları).*

> **DURUM: Duman testi 6/6 TAMAM + cila kalemleri BİTTİ (2026-07-30 oturum 2).**
> Sonuçlar §Duman testi sonuçları'nda, cila dökümü §Cila oturumu'nda.
> Doğrulama: backend pytest tam süit + vitest 85 + eslint + build yeşil.
> Kalan: prod deploy (mesai dışı, `--build` ile) + Faz 6 adayları.

## Ne yazıldı (dosya haritası)

| Dosya | İçerik |
|---|---|
| `frontend/src/lib/caseIntake.ts` | API katmanı + tipler: `analyzeIntakeFile` (NDJSON reader), `mergeIntake`, `keepaliveIntake`, `commitIntake` (+`CommitConflictError` 409), `MergeDraft`/`MergePolicy`/commit tipleri. **`toCommitPolicy`: merge `baslangic/bitis/retroaktif/source` → commit `*_tarihi`/`source_document` eşlemesi TEK yerde** (Faz 4 devir notu a). `policyKey` (backend `_policy_key` semantiği), `normalizeFileType` ("İdari"→"İdari Yargı"). |
| `frontend/src/lib/caseIntakeFields.ts` | `INTAKE_FIELDS` alan sözlüğü (12 alan; çıkarılanlar listeye hiç girmedi), `buildFieldStates` (AI ön-dolgu), `fieldApprovalProgress` (onay kapısı). `teblig_tarihi` merge'te var ama CaseCreate'te alanı yok → listede değil (Faz 6 adayı). |
| `frontend/src/lib/caseIntake.test.ts` | 10 vitest: poliçe eşlemesi, saved/client_id filtreleri, normalizeFileType, onay kapısı semantiği. |
| `frontend/src/hooks/useCaseIntake.ts` | Durum makinesi: sıralı analiz kuyruğu (başarısız belge akışı durdurmaz), otomatik merge, review'da 10 dk keepalive interval'ı, commit, reset. |
| `frontend/src/components/intake/IntakeUploadStep.tsx` | Çoklu dropzone (FlowDropZone yeniden kullanımı, max 15), süre beklentisi (~30 sn/belge), "Analiz Et"e kadar işlem yok. |
| `frontend/src/components/intake/IntakeProgressStep.tsx` | Belge başına canlı durum + sonuç çipleri (esas no/mahkeme/N taraf/tür) + kırmızı başarısız; merge hata kartı + tekrar dene. |
| `frontend/src/components/intake/IntakeFieldRow.tsx` | Onay Checkbox + widget editörü + AiPill (confidence) + kaynak rozeti + adaylar popover'ı (tıkla-seç) + "Kanıtlı"/"Hakem" rozetleri + bilinen mahkeme yazımı önerisi. |
| `frontend/src/components/intake/IntakeReviewStep.tsx` | UX kalbi: alan onayları, taraf satırları (party_type/rol/TC düzenlenebilir, `PartyMatchIndicator`, cari eşleşme gösterimi), Ofis No üretimi (ilk onaylı müvekkilde otomatik; `client-sequence` + `generateTrackingNumber`, kategori önceliği aynen) + yeniden-üret, poliçe seçimi (varsayılan: kayıtsız + eşleşmeli), belge şeridi (ad/tür/özet düzenlenebilir; tür fallback `predictDocTypeFromName`), duplicate + warning bantları, Kaydet kapısı ("N/M alan onaylandı"), commit isteği kurucu, **409'da sequence yenile + 1 kez otomatik retry**. |
| `frontend/src/components/intake/IntakeResultStep.tsx` | Dava linki + belge-başı queued/failed/expired + poliçe saved/skipped + yeni sihirbaz. |
| `frontend/src/pages/CaseIntakeWizard.tsx` | Adım orkestrasyonu + `FlowStageStrip`; "Manuel form ile aç →" kaçışı. |
| `frontend/src/App.tsx` | Route `/new-case/auto`. |
| `frontend/src/pages/CaseList.tsx` | "Yeni Dava Aç" → DropdownMenu: "Belgelerden Otomatik Aç" / "Manuel Aç". |

## Cila oturumu (2026-07-30 oturum 2) — yapılanlar

1. ✅ **E-posta toggle + alıcı seçimi** — review'da yeni kart: toggle (varsayılan
   KAPALI, karar 2), alıcı çipleri, config `email_recipients` önerileri +
   serbest e-posta girişi (regex doğrulamalı). Kaydet kapısı: toggle açık +
   alıcı boşsa engeller. Backend: `CommitOptions.email_to` → route
   `custom_to` geçişi + pytest (`test_commit_email_recipients_passed_through`).
2. ✅ **`sub_type` select** — seçenekler `courtTypesByParent[file_type]`
   (NewCase ALT_TURLER ile aynı kaynak); AI değeri listede yoksa da seçili
   kalabilir (IntakeFieldRow select fallback'i).
3. ✅ **Court parser ortak yardımcıya çıktı** — `lib/courtParse.ts` + 7 vitest;
   QuickCaseModal'daki kopya silindi. İyileştirme: Türkçe İ/ı JS regex /i
   katlamasına girmediğinden desenler `[iİ]`/`[ıI]` sınıflarıyla yazıldı —
   intake'in TAM BÜYÜK HARF mahkeme adları da artık ayrışıyor.
4. ✅ **Priors rozetleri** — ilk cari-eşleşmeli müvekkilin `priors` önerisi
   alan satırında "Geçmiş: X (n/m)" tık-uygula rozeti (otomatik uygulanmaz).
5. ✅ **`beforeunload` koruması** — analiz/review adımlarında sekme
   kapatma/yenileme tarayıcı onayına takılır (SPA içi rota değişimi kapsam dışı).
6. ✅ **Poliçe → kaynak belge linki** — `GET /clients/{id}/policies` yanıtına
   `document_url` eklendi (case_documents'tan ada göre, en yeni kayıt);
   müvekkil kartında poliçe no artık SharePoint linki. (Poliçe düzenleme/silme
   UI'ı Faz 6 — backend POST/DELETE zaten mevcut.)

Yapılmayan (bilinçli, Faz 6 adayları): yeni dosya adı önerisi (backend
`generated_filename` konvansiyonu intake'te yok); taraf `rol` serbest metin
(`ROL_DISPLAY` varsayılanları yeterli); oturum düşmesinde sihirbaz durumu
kurtarma (sessionStorage taslağı / MSAL sessiz yenileme — bulgu 4).

## Duman testi sonuçları (2026-07-30 oturum 2 — gerçek belgeler: 2025/553 demeti)

Girdi: `2026_02_19_DAVA_DILEKCESI_2025_553.pdf` + `..._TENSIP_TUTANAGI_...pdf`
+ `POLICE_2024_2025.pdf` (gerçek dava, Mersin 3. Tüketici Mah.).

| # | Senaryo | Sonuç |
|---|---|---|
| 1 | Yükleme → analiz ilerlemesi | ✅ 3/3 analiz, çipler doğru (`runs_valid: 3` hepsi) |
| 2 | Review | ✅ Kanıtlı/Hakem/AiPill rozetleri, adaylar, "Bilinen yazım" önerisi, cari eşleşmeleri (#4272/#4390), tanıdık sorgu noktaları, 3 uyarı bandı (duplicate + POLICY_PERIOD_MISMATCH + PARTY_CONFLICT), onay sayacı — hepsi çalıştı. "İlgili dönem" rozeti çıkmadı çünkü poliçe dönemi gerçekten dönem dışıydı (doğru davranış). |
| 3 | Kaydet → DB | ✅ Dava 14365 (`X1.A_YILDIRIM.0005.HUKUK.00000`), 3 belge SharePoint'e yüklendi + URL'ler işlendi, poliçe doğru müvekkile kaydedildi, müvekkil hızlı bakışında görünüyor. Taraflar/roller/party_type doğru (poliçeli hekim → CLIENT). |
| 4 | 409 otomatik retry | ✅ Deterministik test: 0006'yı işgal eden sahte kayıt sokuldu → commit 409 → sihirbaz sessizce sequence yeniledi → 0007 ile 200. Kullanıcı hata görmedi. |
| 5 | 30 dk keepalive | ◐ Keepalive kanıtlandı: 32 dk boyunca 10 dk arayla 3 ping, hepsi 200. AMA kullanıcının Azure oturumu düştü → login yönlendirmesi sihirbaz durumunu sıfırladı, commit hiç denenemedi. Bulgu: uzun bekleme senaryosunda gerçek risk belge TTL'i değil, MSAL oturumu (aşağıda not 4). |
| 6 | Kasıtlı expired (restart) | ✅ Review'dayken backend restart → commit 200, dava açıldı (karar 4), yanıt `{queued: 0, failed: 0, expired: 3}`, `case_documents` boş. Aynı koşuda dedup düzeltmesi canlıda doğrulandı: merge `parties: 4` (önceki aynı demetle 5'ti), hastane tek satır. |

Bulunan hatalar / notlar:

1. **Mükerrer kurumsal taraf** — hastane "… ANONİM ŞİRKETİ" ve "… A. Ş."
   yazımlarıyla iki taraf satırı oldu. Kök neden: merge dedup anahtarı
   `normalize_person_name` şirket eklerini eşitlemiyor. **Düzeltildi:**
   `party_check.normalize_party_key` (A.Ş.↔ANONİM ŞİRKETİ, LTD ŞTİ↔LİMİTED
   ŞİRKETİ, TİC/SAN açılımları, kelime sırası bağımsız); merge_parties +
   poliçe sigortalı eşlemesi + belge-içi koşu birleşimi buna geçti; pytest
   eklendi, konteyner süiti yeşil. (Senaryo 6 restart'ıyla canlıya alındı.)
2. Poliçe satırına müvekkil kartından belge erişimi yok (`source_document`
   sadece dosya adı; SharePoint URL'si `case_documents`'ta) — cila adayı.
3. Sequence max+1 ile ilerliyor; aradaki boşluk (silinen 0006) yeniden
   kullanılmıyor — güvenli, bilinçli davranış.
4. **Uzun beklemede oturum kaybı** — 30+ dk açık kalan review'da Azure token
   süresi dolarsa login yönlendirmesi TÜM sihirbaz durumunu kaybettiriyor
   (keepalive belgeleri canlı tutmuştu ama işe yaramadı). `beforeunload`
   cilası uyarır ama kurtarmaz; kalıcı çözüm adayı (Faz 6): taslağı
   sessionStorage'a yazmak ya da MSAL sessiz yenilemeyi review'da tetiklemek.

## Duman testi senaryosu (plan §Faz 5 + Faz 4 deseni)

Lokal stack (`docker compose up`; AVG nedeniyle backend'e
`SSL_CERT_FILE=/app/calibration/ca_bundle.pem`) + `npm run dev` host'ta:

1. CaseList → "Belgelerden Otomatik Aç"; 3–5 gerçek belge (dilekçe + tensip +
   poliçe TIF) yükle → ilerleme satırları + çipler doğru mu?
2. Review: alan onayları/adaylar popover'ı; ilk müvekkil onayında Ofis No
   üretimi; poliçe bloğunda `İlgili dönem` rozeti; Kaydet kapısı sayacı.
3. Kaydet → dava listesinde görünmeli; `case_documents` + upload kuyruğu dolu;
   poliçe müvekkil kartında (`GET /api/clients/{id}/policies`).
4. 409: aynı müvekkille ikinci dava → otomatik sequence retry sessiz geçmeli.
5. 30+ dk bekletme → keepalive sayesinde commit'te belge `expired` OLMAMALI.
6. Kasıtlı expired (backend restart) → sonuç ekranında amber `expired` satırı.

Frontend test/lint: `npm run test` + `npx eslint src/...` + `npm run build`
(host'ta). Backend'e dokunulmadı — konteyner pytest gerekmez.
