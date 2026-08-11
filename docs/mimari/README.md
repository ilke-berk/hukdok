# docs/mimari — yaşayan mimari dokümanları

Bu klasör **güncel** mimariyi anlatır: bir doküman ile kod çeliştiğinde doküman
düzeltilir, dosya arşive taşınmaz.

Giriş noktası repo kökündeki [`CLAUDE.md`](../../CLAUDE.md)'dir; buradaki dosyalar onun
özetini ayrıntılandırır.

| Dosya | Ne anlatır |
| --- | --- |
| [`genel-bakis.md`](genel-bakis.md) | Bileşen haritası (konteynerler, iki katmanlı nginx, 2 worker + lider kilidi), kimlik/tenant, bir isteğin yaşam döngüsü, `/healthz` |
| [`belge-isleme-hatti.md`](belge-isleme-hatti.md) | `/process` stream olay sözleşmesi, PROCESS_CACHE, `/confirm` zinciri, dönüşüm ve gece retry'ı, zaman bütçeleri, upload outbox, hukukbot bildirimi |
| [`dava-acma-akisi.md`](dava-acma-akisi.md) | Zorunlu alanlar, intake sihirbazı uçları, `/commit` 409 çözümlemesi, ofis numarası, taslak kalıcılığı, taraf eşleştirme |
| [`dis-bagimliliklar.md`](dis-bagimliliklar.md) | Gemini (retry/devre kesici/bütçe), Graph & SharePoint (iki katmanlı retry, chunk resume), e-posta, sistem araçları, bağımlılık sürümleri |
| [`deploy-ve-altyapi.md`](deploy-ve-altyapi.md) | `deploy.sh`/`rollback.sh`, sağlık kapısı, `infra/` envanteri, yedekleme, nöbetçiler, GCP izleme, CI, gece otomasyonu |

Kalıcı mimari kararlar ve gerekçeleri ayrı klasördedir: [`docs/kararlar/`](../kararlar/).

## Kural

- Buraya yazılan her operasyonel iddia **koddan ya da koşarak** doğrulanır;
  [`docs/arsiv/`](../arsiv/README.md) içindeki eski planlardan kopyalanmaz.
- Tarih damgalı "şu gün şunu yaptık" anlatısı buraya değil, `docs/arsiv/` içine gider.
- Bir dosya güncelliğini yitirdiyse ya güncellenir ya arşive taşınır; yanlış hâliyle
  burada bırakılmaz.
