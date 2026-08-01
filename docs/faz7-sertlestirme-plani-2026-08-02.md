# Faz 7 Sertleştirme Planı (2026-08-02)

Kendi kendine yeten kickoff dokümanı. Bağlam: Faz 7 zenginleştirme modu kodu
main'de (`c581812`), deploy bekliyor. Değerlendirmede üç açık çıktı; kullanıcı
kararları (2026-08-02):

1. **Çakışma davranışı:** 409 + yeniden birleştir — apply, dava bu arada
   değiştiyse reddedilir; sihirbaz merge'i tazeleyip fark listesini yeniden
   gösterir.
2. **IntakeReviewStep bölünmesi:** AYRI İŞ, bu paket dışı (bir sonraki UI
   işiyle birlikte; bkz. §İş 3).
3. **Deploy kapsamı:** sertleştirme bitince TEK deploy (İş 1 + İş 2 + c581812
   birlikte; öncesinde kullanıcı UI dumanı).

## İş 1 — Alan listesi senkron testi (~10 dk)

`case_manager.ENRICH_FIELDS` ile `schemas_intake.EnrichFieldsIn` el ile
senkron iki liste; ayrışırlarsa alan sessizce uygulanmaz. Test
`tests/test_case_intake_enrich.py`'ye:

- `set(ENRICH_FIELDS) == set(EnrichFieldsIn.model_fields)`
- `set(services.case_intake.ENRICH_CASE_FIELD_MAP) ⊆ set(ENRICH_FIELDS)`
  (merge'in durum verdiği her alan apply'da da uygulanabilir olmalı)

## İş 2 — Eşzamanlılık koruması: 409 + yeniden birleştir (~yarım gün)

Bayat ekranla yazmayı imkânsız kılan optimistic check.

### Backend
1. `get_case` sözlüğünde `updated_at` yoksa eklenir (ISO); merge'in enrich
   `draft["case"]` özetine `updated_at` konur.
2. `CaseIntakeApplyRequest`'e `expected_updated_at: Optional[str]` —
   **verilmezse kontrol atlanır** (geriye uyum; eski istemci davranışı değişmez).
3. `enrich_case` girişinde karşılaştırma: `case.updated_at` ISO normalize
   edilerek `expected_updated_at` ile eşleşmiyorsa `{"error": "stale_case"}`;
   route bunu **409**'a çevirir ("Dava bu ekran açıldıktan sonra güncellendi —
   öneriler güncel değerlerle yeniden birleştirilecek."). Kontrol ALAN
   GÜNCELLEMESİNDEN ve belge arşivinden ÖNCE koşar → 409'da hiçbir belge
   tüketilmez, hiçbir alan yazılmaz (commit'in 409 garantisiyle aynı desen —
   retry güvenli).
4. Bilinen kabul: `updated_at` takip paneli PATCH'iyle de oynar → nadir
   false-positive mümkün; karar gereği yine de 409 + re-merge (zararsız,
   kullanıcı güncel değerleri görür).
5. Testler (apply_env desenine): bayat imza → 409 + belge tüketilmedi
   (`PROCESS_CACHE.touch` hâlâ true) + enrich_case alan yazmadı; güncel imza →
   200; imza gönderilmedi → 200 (kontrol yok).

### Frontend
1. `MergeCaseSummary`'ye `updated_at`; `buildApplyRequest` bunu
   `expected_updated_at` olarak gönderir.
2. `applyIntake` 409'u `ApplyConflictError` olarak fırlatır (commit'in
   `CommitConflictError` deseni).
3. Wizard/hook: 409'da toast ("Dava bu arada güncellendi — öneriler
   tazeleniyor") + otomatik `retryMerge` (analizler korunur, Gemini'ye
   gidilmez) → review yeni draft'la remount (mevcut `key` mekanizması),
   kullanıcı farkları yeniden tik'leyip Kaydet'e basar. Otomatik yeniden-apply
   YOK — çakışmada karar daima kullanıcının.
4. vitest: `ApplyConflictError` ayrımı + buildEnrichFields'ın yeni draft'la
   tutarlılığı zaten kapsanıyor; akış elle test edilir (aşağıda duman 3).

## İş 3 — (ERTELENDİ) IntakeReviewStep bölünmesi

Ayrı iş: yeni-dava / enrich review'u iki bileşene ayır, ortak parçaları
(IntakeFieldRow, taraf satırı, poliçe/belge blokları) paylaşımlı bırak.
Bir sonraki sihirbaz UI işiyle birlikte ele alınacak; bu pakete girmez.

## Sıra, test ve deploy

1. İş 1 → İş 2 → tam koşu: pytest KONTEYNERDE, vitest host'ta, tsc/ruff/mypy.
2. Kullanıcı UI dumanı (lokal Docker, http://localhost:8080):
   - gerçek tensip + mevcut dava → "Belgeden Doldur / Teyit Et" akışı,
   - duplicate köprüsü ("Bu davayı zenginleştir →"),
   - çakışma: iki sekme — birinde review açıkken diğerinden davayı güncelle,
     Kaydet → 409 + otomatik tazeleme görülmeli.
3. TEK deploy (mesai dışı, standart): commit → bundle → `ssh hukukoid` →
   pg_dump yedek → `docker compose up -d --build`; doğrulama: migration
   logları (case_history kolonları), `/api/case-intake/apply` authsuz 401,
   bundle'da enrich işareti, loglar temiz, site 200.

Çalışma kuralları her zamanki gibi: dosya değişikliği daima Edit tool ile
(PS5.1 tuzağı), backend testleri konteynerde.
