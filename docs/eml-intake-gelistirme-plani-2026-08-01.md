# Sihirbaza .eml Desteği — Geliştirme Planı (2026-08-01)

## Amaç

Sigorta atama e-postaları (örn. Quick Sigorta / Maher Holding) büroya mail
olarak geliyor. Kritik veri iki yerde:

- **Gövde + konu satırı**: `T.T: 23/07/2026` (tebliğ tarihi), konu kalıbı
  `[Kayseri 3. Tüketici Mahkemesi-5002940510859-0-2026/371]`
  (mahkeme + hasar dosya no + esas no).
- **Ekler**: üst yazı (asıl atama yazısı), dava/cevap dilekçeleri vb.

Bugünkü akış manuel: kullanıcı maili PDF'e yazdırıyor, ekleri tek tek indirip
sihirbaza yüklüyor. Hedef: **tek `.eml` dosyası sürükle → gövde sanal belge +
ekler otomatik ayrışır**, hepsi mevcut belge-başına analiz hattından geçer.

Outlook tarafı: yeni Outlook / OWA'da mail **⋯ → İndir** ile `.eml` olarak
kaydediliyor. Klasik Outlook sürükle-bırak `.msg` verir — bu Faz 2 (opsiyonel).

## Mimari karar

`.eml` upload beyaz listesine (`ALLOWED_EXTENSIONS`) **girmez** — genel belge
yükleme yolları (davaya belge ekleme, /process) mail kabul etmemeli. Bunun
yerine intake'e özel **genişletme endpoint'i** eklenir; frontend `.eml`'i önce
oraya gönderir, dönen parçaları normal dosya gibi listeye ekler. Böylece:

- Belge-başına analiz, ensemble, merge, commit, HAM arşiv → **sıfır değişiklik**.
- Her parça kendi `process_id`/analizini alır, mevcut akışla birebir aynı.
- Çift yükleme (parçalar inip tekrar çıkıyor) maliyeti ihmal edilebilir
  (tipik mail ~500 KB – birkaç MB).

## Faz A — Backend

### A1. `POST /api/case-intake/expand-eml` (routes/case_intake.py)

Girdi: tek `.eml` (multipart), limit `MAX_UPLOAD_BYTES` (50 MB).

Doğrulama: `.eml`'in magic byte'ı yoktur (düz RFC822 metni). İlk ~2 KB'de
`From:` / `Received:` / `Subject:` / `MIME-Version:` başlıklarından en az
ikisi aranır; yoksa 400. (`validate_file_type` genel fonksiyonuna DOKUNULMAZ —
kontrol endpoint içinde yerel yapılır, `.eml` genel beyaz listeye girmez.)

Parse: stdlib `email` — `message_from_binary_file(fp, policy=email.policy.default)`.

**Gövde çıkarımı:**
1. `msg.get_body(preferencelist=("html", "plain"))`.
2. HTML ise temizlik: `<script>`, dış kaynak referansları ve `cid:` gömülü
   görseller sökülür (imza logoları vb.).
3. Başına başlık tablosu eklenir: **Konu / Kimden / Kime / Tarih** — konu
   satırı hasar no + esas no taşıdığı için modele mutlaka gitmeli. Forward
   zincirindeki `From:/Sent:/Subject:` blokları gövdede zaten korunur.
4. Geçici `.html` → **soffice** ile PDF (bkz. A2). Çıktı adı:
   `E-posta_govdesi.pdf` (sanitize sonrası).

**Ek ayrıştırma:** `msg.iter_attachments()` üzerinde:
- Uzantı `resolve_upload_suffix()` ile çözülür (`.udf.zip` → `.udf` dahil).
- `ALLOWED_EXTENSIONS` dışındakiler atlanır ve `skipped` listesine yazılır
  (neden: "uzantı desteklenmiyor").
- İmza görselleri: `iter_attachments()` inline/cid parçaları zaten dışarıda
  bırakır; yine de gelen `Content-ID`'li görüntüler atlanır.
- Dosya adı olmayan parçalara `ek_<n>.<ext>` verilir; adlar
  `sanitize_filename` mantığıyla temizlenir (whitelist kontrolü önce, ki
  HTTPException fırlatmasın).
- Parça başına ve toplamda `MAX_UPLOAD_BYTES` kontrolü.
- İç içe `.eml` (attached message) açılmaz — `skipped` olarak raporlanır.

**Yanıt (JSON):**
```json
{
  "body": { "filename": "E-posta_govdesi.pdf", "data_b64": "..." },
  "attachments": [ { "filename": "ustyazi_77.pdf", "data_b64": "..." } ],
  "skipped": [ { "filename": "image001.png", "reason": "inline görsel" } ]
}
```
Base64 + JSON yeterli; 50 MB sınırında bile ~67 MB yanıt, nginx/axios için
sorun değil (container nginx timeout 300 s).

### A2. `html_to_pdf()` (pdf/format_converter.py)

`office_to_pdf` ile aynı soffice hattı (aynı `_office_semaphore`, aynı
`LIBREOFFICE_TIMEOUT`): `soffice --headless --convert-to pdf <file>.html`.
Türkçe karakterler mevcut docx dönüşümünde sorunsuz olduğundan font tarafı
hazır. `CONVERTIBLE_EXTENSIONS`'a `.html` **eklenmez** (upload yolu değil,
sadece iç kullanım) — ayrı fonksiyon olarak dışa açılır.

### A3. Prompt güncellemesi (prompts.py)

Belge türü listesine "sigorta atama e-postası (çıktısı)" eklenir + kurallar:
- `T.T` / `T.T.` = **tebliğ tarihi** (`teblig_tarihi`).
- Konu satırı kalıbı `[<Mahkeme>-<HasarDosyaNo>-<n>-<Esas Yıl/No>]` →
  `mahkeme`, `hasar_dosya_no`, `esas_no` buradan çıkarılabilir.
- Gönderen şirket/imza bloğu → `sigorta_sirketi` ipucu (örn. Quick Sigorta).

> Bu madde tek başına, bugünkü "maili PDF'e yazdır" akışını da iyileştirir —
> A3 bağımsız ve önce deploy edilebilir.

## Faz B — Frontend

### B1. Kabul listesi (lib/fileValidation.ts)

`VALID_TYPES`/`VALID_EXTENSIONS` **değişmez** (genel yollar .eml almamalı).
İntake'e özel ek sabitler:
```ts
export const INTAKE_EXTRA_EXTENSIONS = [".eml"];
export const INTAKE_ACCEPT_ATTRIBUTE = ACCEPT_ATTRIBUTE + ",.eml";
```
`FlowDropZone`'a accept/validator prop'u geçilerek yalnızca sihirbazda geçerli
olur.

### B2. Genişletme akışı (hooks/useCaseIntake.ts + lib/caseIntake.ts)

`addFiles` async'e döner: gelenler arasında `.eml` varsa her biri için
`expandEmlFile(file)` (yeni API sarmalayıcı) çağrılır:
- Dönen `body` + `attachments` base64 → `File` nesnelerine çevrilir
  (`new File([bytes], filename, {type})`) ve listeye normal belge gibi eklenir.
- `.eml`'in kendisi listeye **girmez**.
- `skipped` doluysa toast: "E-posta açıldı: gövde + 5 ek eklendi, 2 parça
  atlandı (inline görsel)".
- `MAX_INTAKE_FILES` (15) kontrolü genişleme SONRASI toplam üzerinden yapılır;
  taşarsa uyarı + sığan kadarı eklenir.
- Genişletme sırasında dropzone'da küçük "E-posta açılıyor…" durumu
  (spinner); hata olursa dosya reddedilir, toast ile neden gösterilir.

### B3. UI dokunuşu (IntakeUploadStep.tsx)

Açıklama metnine "…poliçe, atama yazısı **veya atama e-postası (.eml)**"
eklenir. Parçalar listede normal satır olarak görünür — ekstra grup UI'ı
Faz 1'de yok (gerekirse sonra `sourceEml` etiketi).

## Kapsam dışı / açık kararlar

| Konu | Karar |
|---|---|
| Orijinal `.eml`'in HAM arşive gitmesi | Faz 1'de **yok** — parçalar (gövde PDF'i + ekler) arşivlenir, mail dosyasının kendisi atılır. İstenirse Faz 2. |
| `.msg` (klasik Outlook) | Faz 2 — `extract-msg` bağımlılığı gerektirir. Kullanıcıya ipucu: yeni Outlook/OWA'dan "İndir" ile `.eml` alın. |
| Gelen kutusu otomasyonu (Graph ile mailbox izleme) | Ayrı geliştirme — otonom dava açma sonraki fazları. Bu plan onun ön koşulunu (mail parse) üretmiş olur. |

## Test planı

Backend (pytest, konteynerde — host py3.13 uyumsuz):
- `tests/test_eml_expand.py`: sentetik multipart .eml fixture'ı
  (HTML gövde Türkçe karakterli + PDF ek + inline PNG logo + .zip ek + iç içe .eml):
  1. Gövde PDF üretilir, içinde konu satırı ve `T.T:` metni geçer (fitz ile doğrula).
  2. PDF ek `attachments`'ta, logo + zip + nested eml `skipped`'da.
  3. `.udf.zip` adlı ek `.udf`'e normalize edilir.
  4. Başlıksız/bozuk dosya → 400; boyut aşımı → 413.
  5. Salt text/plain gövdeli mail de çalışır.
- Prompt regresyonu: mevcut intake testleri yeşil kalmalı.

Frontend (vitest, host'ta):
- `fileValidation.test.ts`: `.eml` yalnız intake accept'inde.
- `caseIntake.test.ts`: base64 → File dönüşümü, skipped toast mantığı,
  MAX_INTAKE_FILES taşma davranışı.

Duman testi (lokal docker): gerçek Quick Sigorta maili `.eml` indirilip
sihirbaza atılır → beklenen: gövde + üst yazı + dilekçeler listede, analiz
sonrası `teblig_tarihi=23.07.2026`, `hasar_dosya_no=5002940510859`,
`esas_no=2026/371`, `mahkeme=Kayseri 3. Tüketici Mahkemesi`,
`sigorta_sirketi=Quick Sigorta`.

## Riskler

- **soffice HTML dönüşümü**: karmaşık HTML mail'lerde düzen bozulabilir —
  sorun değil, hedef görsel sadakat değil metnin modele ulaşması. Dönüşüm
  başarısızsa fallback: gövdeyi düz metne indirip (html→text) yeniden dene.
- **`iter_attachments` sınırları**: bazı istemciler eklere `inline`
  disposition verir — dosya adı + izinli uzantısı olan inline parçalar da ek
  sayılır (filtre yalnız cid'li görselleri eler).
- **15 belge limiti**: gövde + 7 ek = 8 parça; iki mail üst üste sınıra
  dayanır. Faz 1'de limit değişmez, uyarı yeterli.

## İş sırası ve tahmin

1. A3 prompt (bağımsız, ~15 dk) → hemen değer üretir.
2. A2 `html_to_pdf` + A1 endpoint + backend testleri (~yarım gün).
3. B1–B3 frontend + vitest (~2-3 saat).
4. Duman testi (gerçek mail) + deploy (standart: SSH + `docker compose up -d --build`, mesai dışı; migration yok, env yok).
