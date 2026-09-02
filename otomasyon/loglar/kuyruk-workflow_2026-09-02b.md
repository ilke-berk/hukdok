# Gece Kuyrugu (workflow) · 2026-09-02b

## Ozet
1 gorev alindi · 0 isaretlendi · 1 bloke · 0 atlandi

## Isaretlenenler
| gorev | bant | commit | kapi | denetim | not |
| --- | --- | --- | --- | --- | --- |
| — | — | — | — | — | Bu koşuda işaretlenen görev yok |

## Bloke

### G106 — Takip paneline Olay Türü + Hükümdeki Rol yazma arayüzü (frontend)

**Durma sebebi:** Testi değiştirmeden geçilemedi — görev tanımı gözden geçirilmeli. Bu bir başarısızlık değil, hattın DOĞRU çalıştığının kanıtıdır: sözleşmeye birebir uyan uygulama, kapsam dışı bir kilit testiyle yapısal olarak çakışıyor.

**Son parmak izi:** `caseCardFields.test.ts:121` — G073 kesişim kilidi: kesişim `toEqual []` beklentisine `olay_turu` + `hukumdeki_rol` düştü (1 failed / 579 passed).

**Denenen yaklaşımlar:**
1. TUR 1: Sözleşmeye birebir uygulama — EVENT_FIELDS + PanelListKey tip genişlemesi + TRACKING_DRAFT_KEYS'e iki anahtar + panelde genel bölüme Belgeleme Olayı bloğu (renderField select deseni birebir) + 13 yeni test; sonuç 1 failed / 579 passed — tek kırmızı kapsam dışı G073 kesişim kilidi.
2. Alternatif değerlendirildi-RED: alanları TRACKING_DRAFT_KEYS dışında panel-yerel state ile taşımak — kilit yeşil kalırdı ama görev "taslak kalıcılığı aynı davranır / özel kural icat etme" diyor; kilidin denetlediği şey fiilen varken testi yeşil tutmak sahte yeşil olurdu.
3. Alternatif değerlendirildi-RED: alanları karttan çıkarmak — `caseCardFields.ts`/`CaseDetails.tsx` kapsam dışı + G105 sözleşmesi dondurulmuş.
4. Alternatif değerlendirildi-RED: `caseCardFields.test.ts:115` kilidini güncellemek — mevcut test + kapsam dışı dosya, işçiye çift yasak; DUR kararı verildi.

**Teşhisin kök nedeni:** G105 iki alanı MEDICAL_CARD_FIELDS'e koydu (salt-okunur gösterim; TransferFieldsCard düzenleme kontrolü taşımıyor, `CaseDetails.tsx:132-172` doğrulandı), G106 sözleşmesi aynı alanları takip taslağına koyuyor; `caseCardFields.test.ts:115-122` kart-grubu-kesişim-taslak=boş kilidi bu ikiliyle yapısal çakışıyor.

**Worktree:** `C:/dev/hukudok-wt/G106` — KOMİTSİZ tam uygulamayla korunuyor (5 dosya: 4 kapsam + görev dosyası raporu), kapatma turu için hazır. Yeni test dosyası yok; 13 yeni test kapsamdaki iki mevcut test dosyasına eklendi (`trackingDraft.test.ts` +6, `CaseTrackingPanel.test.tsx` +7; configMock'a eventTypes/judgmentRoles fixture alanları eklendi — beklenti değişikliği değil). Lint/tsc bilerek koşulmadı (paket kırmızıyken anlamsız). Not: `useCases.ts::CaseTrackingUpdate` arayüzünde iki alan bildirimi yok (kapsam dışı; `patch as CaseTrackingUpdate` cast'i sayesinde derleme/çalışma etkilenmiyor).

**Önerilen sonraki adım (gündüz/planlayıcı kararı):** G106 kapsamına `frontend/src/lib/caseCardFields.test.ts` eklenip kilit düzenlenebilirlik gerçeğine yeniden bağlanmalı (ör. kesişim beklentisi tam `['hukumdeki_rol','olay_turu']` + G061/G065 emsal yorumu).

**Kabul kriterlerinin durumu:**
- "Mevcut testlerde gerileme yok" — `caseCardFields.test.ts:121` (kapsam dışı G073 kesişim kilidi) yapısal olarak kırmızı; sözleşmeye uyan her uygulama kırar.
- Diğer üç kriter (dropdownlar genel bölümde + payload adları/yalnız-değişen + boş seçim temizler) uygulandı ve 13 yeni testle yeşil, AMA paket kırmızı olduğundan commit'lenmedi — resmen karşılanmış sayılmaz.

## Karar bekleyenler
- G106 — karşılanmayan kabul maddesi, SORU olarak: "Mevcut testlerde gerileme yok" kriteri, kapsam dışı G073 kesişim kilidi (`caseCardFields.test.ts:121`) sözleşmeye uyan her uygulamada kırıldığı için karşılanamıyor. Kilit testi G106 kapsamına alınıp güncellensin mi (önerilen: kesişim beklentisi `['hukumdeki_rol','olay_turu']`)?
- G106 — SORU: Diğer üç kriter uygulanmış ve 13 yeni testle yeşil olduğu halde paket kırmızı olduğundan commit'lenmedi; kilit kararı verildikten sonra worktree'deki hazır uygulama kapatma turuyla commit'lensin mi?

(teshis.gorevTanimiHatali=true işaretli görev bu koşuda yok; sorular kabulKarsilanmayan maddelerden türetildi.)

## Izin engelleri
yok

## Atlananlar
yok (tavan nedeniyle atlanan da yok)
