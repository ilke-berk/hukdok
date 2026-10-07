# Oturum özeti — 06-07.10.2026 · Lexis emsal ajan hattı + ilk canlı yazım testi

> Tarihli anlatı (yeni oturumun giriş noktası). Güncel durum için `docs/plan/emsal-ajan-hatti-plani-2026-10-06.md`
> (başındaki Durum bloğu) ve lexis-rapor `PLAN.md` Aşama 12. Kişi verisi yok; kart yalnız numarayla anılır.

## 1. Ne yapıldı (iki depo, hepsi commit'li, push YOK)

**Emsal ajan hattı (karşılaştırma belgesindeki "ajan hattı"), G258-G266 — DOKUZU DA TAMAM, gece kuyruğu + elle merge.**
- lexis-rapor: tam metin arama (`karar_arama` tsvector + GIN, operatörlü sorgu kurucu) 0200695 · belge yükleme / kart
  belgesi + PDF-DOCX-UDF metin + maske + `emsal_dosyalari` 3a84ccd · kalıcı SharePoint arşivi `03_LEXIS_EMSAL`
  (servisin kendi Graph istemcisi) cd90f33 · ajanlar (sorgu üretici, FTS adaylar, paralel okuyucular, kod denetçi,
  önbellek, NDJSON) 9767445 · inceleme paketi (işaret sütunlu DOCX + karar metinleri + JSON) + Word'de emsal künye
  satırı 58d8a27 · ölçüm aracı `emsal_ajan_olcum.py` 624270a. Testler 503 pytest, ruff temiz.
- HUKDOK: nginx allowlist dört emsal ucu + `proxy_buffering off` + 20M af10c9c · ekran (`EmsalBulDiyalogu`, akış okuyucu,
  taslak `emsal_kararlar`) merge 9508e1a · doküman merge 4f6b31b.
- Koşucuya **lexis bandı** eklendi (dış depo `..\lexis-rapor`, seri, host pytest); `.claude/workflows/gece-kuyrugu.js`.
  Sınıflandırıcı iki satırı reddetti, kullanıcı PowerShell'le ekledi (7477e24).
- Kararlar: K23 belge kalıcı (yeni SharePoint klasörü), K27 inceleme paketi, K28 emsal karar taslakta AYRI alan (yazıma
  gitmez), K29 arama evreni yalnız büro, K30 modeller flash. **G275** (kademeli okuma: tek toplu eleme → 8 tam okuma)
  kuyrukta AÇIK (G267-G274 PDF araçları planına ait, başka oturum).

**Lokal kurulum:** karar PDF klasörü servise salt okunur bağlı (lexis-rapor 61028cc), lexis_api imajı yeniden kuruldu.
**Yazım AÇILDI:** lexis `.env`'e `LEXIS_YAZIM=1`, `GEMINI_API_KEY`, `LEXIS_GEMINI_MODEL=gemini-3.8-flash` (07.10 kullanıcı kararı).

## 2. İlk canlı yazım testi (kart 13019, Anadolu, idari yargı, 13 belge / 13 büro kararı)

- Giriş: `http://127.0.0.1:8080` Azure yönlendirme hatası verir, **`http://localhost:8080`** kullanılır. `/lexis` adresine
  doğrudan gidince ana sayfaya düşüyor (yönetici kontrolü hesap yüklenmeden koşuyor); sayfa içi geçişle çalışır.
- Bulunan ve düzeltilen hata: ön yüz uzun yazımı 30 sn'de kesiyordu (nginx 499); `/lexis-api/yaz` ve `/emsal-ara` 300 sn
  katmanına alındı (HUKDOK 4125ba3, frontend imajı yenilendi).
- Sonuç: 9 benzersiz karar, 3 maskeli emsal rapor, 2 Gemini çağrısı, 128 sn, 113.690 karakter. İddia 1 paragraf, yargı
  süreci 9 paragraf (kararlarıyla), değerlendirme 5 doğrulanmış madde + kalıp, muallak manevi 135.418 TL (emsal basamağı).
  Word masaüstüne indi (`Lexis_9.204_ANA_taslak.docx`). İçindekilerdeki gri zemin = Word alan güncellemesi; sağdaki
  "2" kutusu = şablonun üstbilgisindeki sayfa no metin kutusu; ilk üç başlık satırı şablon kalıntısı.
- **Kullanıcı değerlendirmesi: "sonuç iyi değil, sebebi öncesinde bir sürü boşluk."** Teşhis (koddan): poliçe no,
  teminat limiti, hastane kartta HİÇ yok; sigortalı rolü bu kartta yok; müdahale tarihi, talep şekli, sulh durumu,
  tıbbi görüş ve poliçe incelemesi BELGELERDEN okunur — belgelerden çıkarım (Aşama 2-3) henüz yazılmadı. Kart 13019'un
  eski Lexis raporu yok; kütüphanedeki 28 raporun kartlarında büro kararı yok → bugün "model taslağı ↔ gerçek rapor"
  kıyası yapılabilecek dosya YOK.

## 3. Açık sorular / önerilen yol (karar kullanıcıda)

1. **Belgelerden olgu ve künye çıkarımı (Aşama 2-3)** kuyruğa (G276-G277 önerisi): dilekçe → iddia/talep/dava tarihi;
   poliçe → poliçe no/teminat/dönem; hekim beyanı → sigortalı/hastane/müdahale tarihi/tıbbi görüş; bilirkişi/ATK →
   tıbbi görüş; hasar ihbarı → ilk talep tarihi/şekli. Metin çıkarma G259'da hazır; model maskeli, alıntı dayanaklı JSON.
2. **Sınama dosyaları:** 3-5 güncel gerçek dosyanın belgeleri HUKDOK kartına yüklenir (K10); pilot 28 raporun dosyaları
   olursa gerçek raporla bölüm bölüm kıyas mümkün (pilot kartlarının yalnız birinde belge var: 4934, 2 ATK raporu).
3. **Külliyat dışa aktarımı** (3.065 rapor): kapanmış dosyalarda rapor + karar birlikte → kararlardan yazımın gerçek ölçümü.
4. **Emsal iyi buluyor mu:** (a) eski rapor önerisi şirket/tür/yargı yoluna dayanır, tıbbi benzerlik 1. adımla gelir;
   (b) emsal karar hattı ölçülebilir: `karar_arama_kur.py --apply` (kuru koşu 4.058 belge hazır) → 20 kartlık zincir
   sağlaması sahte modelle → 10 dosyada Gemini ile "emsal bul" + inceleme paketinde avukat işareti → Recall@5.
   Onay bekliyor: `--apply` + zincir ölçümü (Gemini'ye gitmez).
5. Diğer insan adımları: ilk SharePoint yüklemesi (`SHAREPOINT_*` Lexis `.env`'ine), G275 gece koşusu, push (HUKDOK ve
   lexis-rapor), İçindekiler'deki üç başlık satırının temizlenmesi (şablon/yazıcı kararı).

## 4. Çalışır durumdaki komutlar / yerler

- Lexis gerçek kipi: `http://localhost:8080/lexis?veri=gercek` (yönetici hesabı; sayfa içi geçiş).
- Servis sağlığı: `curl http://127.0.0.1:8020/health`; yazım durumu `docker exec lexis_api python -c "from servis import yazim; print(yazim.durum())"`.
- FTS kuru koşu (lexis-rapor kökü, parola `.env`'den okunur, basılmaz): `LEXIS_DB_URL=... python araclar/karar_arama_kur.py`.
- Kuyruk: `gorevler/KUYRUK.md` ÖNCELİK 9 (G258-G266 tamam, G275 açık); koşucu `/gece-kuyrugu`, lexis görevleri için
  oturuma `..\lexis-rapor` dizin yetkisi ve temiz depo gerekir; HUKDOK'ta izlenmeyen `linkedin/` klasörü runner merge
  kapısını kapatır (frontend/docs görevleri elle merge edildi).
