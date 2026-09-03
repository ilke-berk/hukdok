# docs/mimari — yaşayan mimari dokümanları

Bu klasör **güncel** mimariyi anlatır: bir doküman ile kod çeliştiğinde doküman
düzeltilir, dosya arşive taşınmaz.

Giriş noktası repo kökündeki [`CLAUDE.md`](../../CLAUDE.md)'dir; buradaki dosyalar onun
özetini ayrıntılandırır.

| Dosya | Ne anlatır |
| --- | --- |
| [`genel-bakis.md`](genel-bakis.md) | Bileşen haritası (konteynerler, iki katmanlı nginx, 2 worker + lider kilidi), tenant modeli, bir isteğin yaşam döngüsü, `/healthz` |
| [`kimlik-ve-token.md`](kimlik-ve-token.md) | Kullanıcı oturumu (MSAL, PKCE, sessionStorage, 401 yenileme, çıkış yolları), backend doğrulama zinciri (tid allowlist, JWKS, RS256/aud/iss/exp, DEV_MODE guard'ları, ADMIN_EMAILS), süre tablosu (koddan okunan vs. Entra'da teyit edilmemiş), Graph app-only akışı + secret ömrü, `ALLOWED_DOMAINS`'in kapı olmadığı, açık kalemler |
| [`belge-isleme-hatti.md`](belge-isleme-hatti.md) | `/process` stream olay sözleşmesi, PROCESS_CACHE, `/confirm` zinciri, dönüşüm ve gece retry'ı, zaman bütçeleri, upload outbox, hukukbot bildirimi |
| [`dava-acma-akisi.md`](dava-acma-akisi.md) | Zorunlu alanlar, intake sihirbazı uçları, `/commit` 409 çözümlemesi, ofis numarası, taslak kalıcılığı, taraf eşleştirme |
| [`veri-teslim-hatti.md`](veri-teslim-hatti.md) | Veri ekibinin teslim paketleri: SharePoint `gelen` klasörü → `aktarim_teslimleri` defteri ve durum makinesi → kapı eşikleri → 04:00 gece turu / boot telafisi → cevap paketi; `Düzeltme_Logu`/`DEGER_HAVUZLARI`/kapsam sayfaları, log sözleşmesi, açık kalemler. Veri ekibine verilen dış sözleşme [`docs/veri-teslim/SOZLESME.md`](../veri-teslim/SOZLESME.md) |
| [`dis-bagimliliklar.md`](dis-bagimliliklar.md) | Gemini (retry/devre kesici/bütçe), Graph & SharePoint (iki katmanlı retry, chunk resume), e-posta, sistem araçları, bağımlılık sürümleri |
| [`deploy-ve-altyapi.md`](deploy-ve-altyapi.md) | `deploy.sh`/`rollback.sh`, sağlık kapısı, `infra/` envanteri, yedekleme, nöbetçiler, GCP izleme, CI, gece otomasyonu |

Kalıcı mimari kararlar ve gerekçeleri ayrı klasördedir: [`docs/kararlar/`](../kararlar/).

## Kural

- Buraya yazılan her operasyonel iddia **koddan ya da koşarak** doğrulanır;
  [`docs/arsiv/`](../arsiv/README.md) içindeki eski planlardan kopyalanmaz.
- Tarih damgalı "şu gün şunu yaptık" anlatısı buraya değil, `docs/arsiv/` içine gider.
- Bir dosya güncelliğini yitirdiyse ya güncellenir ya arşive taşınır; yanlış hâliyle
  burada bırakılmaz.
