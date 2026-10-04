# Dava takip modülü — araştırma talebi

**Tarih:** 02.10.2026 · **Gönderen:** HUKDOK ekibi · **Muhatap:** veri ekibi

**Konu:** Dava takibinin belgelerden otomatik yürütülmesi — hangi belgeden hangi veri çekilebilir?

---

Merhaba,

Dava takip modülü için önerdiğiniz araştırmaya başlamak istiyoruz. Hedefimiz dava takibini
otomatikleştirmek: dosyaya gelen her belgeden ilgili bilgi okunsun, dosyanın aşaması, duruşmaları,
kararları ve süreleri elle girilmeden güncellensin. Bunun için sizden iki şey öğrenmek istiyoruz:
**takipte tuttuğumuz bilgiler yeterli mi** ve **hangi belge türünden hangi veriler çekilebilir.**

## 1. Önce bir ayrım: dava kartı ≠ dava takibi

Bu iki katmanın karışmaması araştırmanın ön şartı.

| | Dava kartı | Dava takibi |
| --- | --- | --- |
| Ne anlatır | Davanın **kimliği**: bu dava nedir, kimler arasında, kim bakıyor, ne isteniyor | Davanın **seyri**: ne oldu, dosya şimdi nerede, sırada ne var, hangi süre işliyor |
| Ne zaman doğar | Dosya açılırken, bir kez | Dosya yaşadıkça, her olayla |
| Yapısı | Alan başına tek değer | Tarihli kayıtlar; aynı türden birden çok olabilir (üç duruşma, iki istinaf turu) |
| Kaynağı | Açılış bilgileri + teslim paketinizin ana sayfası | Dosyaya gelen belgeler |
| Örnek | Ofis no, taraflar, sorumlu avukat, dava konusu, dava değeri, klinik kodlama | Aşama, duruşma günü, karar künyesi, tebliğ tarihi, kanun yolu süresi, kesinleşme |

**Ayırma testi:** bilgi dosya açıldığı gün biliniyor muydu? → kart. Bir olay (duruşma, karar,
tebliğ, başvuru, rapor) gerçekleşince mi doğdu? → takip.

**Sınırdaki alanlar:** esas no ve mahkeme kartta *güncel* değeriyle görünür; görevsizlik ya da
bozma ile değişmesi bir takip olayıdır. Dava değeri karttadır; ıslah bir takip olayıdır. Durum
(Derdest / Danış / Mahzen) karttadır; istinaf, temyiz, kesinleşme durum değil **aşamadır** ve
takibe aittir.

Bu araştırma **yalnız dava takibi** içindir. Kart alanlarında değişiklik istemiyoruz; kart
listesini (EK-1, A sayfası) yalnız neyin takip *olmadığını* göstermek için ekledik. Teslim paketi
sözleşmesi de bu çalışmadan etkilenmez.

## 2. Bugün neredeyiz

- Takipte **43 bilgi** tanımladık: 30'u bugün sistemde tutuluyor, 13'ü henüz tutulmayan aday
  (EK-1, B sayfası).
- Tutulanların çoğu **elle** ya da teslim paketinizin `Karar_Asamalari` sayfasından doluyor.
- Sistemde **128 belge türü** var (EK-2). Her belgeden bugün yalnız belge tarihi, esas no,
  mahkeme, müvekkil, taraf adları ve kısa özet okunuyor.
- Belgeden otomatik gelen takip verisi çok sınırlı: sonraki duruşma günü ve saati (yalnız tensip
  zaptı, duruşma zaptı ve tebligattan); temyiz başvurusu / feragat / ıslah dilekçesiyle aşama
  değişimi; karar belgesi yüklenirken kullanıcının girdiği tebliğ tarihi.
- Süre uyarısı yalnız iki süre için hesaplanıyor: istinaf ve temyiz başvurusu (HMK, tebliğden iki
  hafta). İdari yargı ve ceza yargısı süreleri, cevap, rapora itiraz ve ara kararla verilen kesin
  süreler yok.

Kısacası belgeler arşive giriyor ama içlerindeki takip bilgisi dosyaya işlenmiyor. Araştırmanın
kapatmasını istediğimiz boşluk bu.

## 3. Sorularımız

1. **Takip listesi yeterli mi?** EK-1 B sayfasındaki 43 bilgi bir davayı eksiksiz takip etmeye
   yetiyor mu? Eksik, fazla ya da yanlış tanımlanmış olan var mı? Mavi (aday) satırlar gerekli mi,
   öncelikleri ne?
2. **Hangi belge türünden hangi veriler çekilebilir?** EK-2'deki her tür için: takip için hangi
   bilgiler okunabilir, EK-1'deki hangi satırı besler, belgede nerede ve hangi ifadeyle yazar, ne
   kadar güvenilir? Takip verisi taşımayan türe "YOK" yazmanız yeterli.
3. **Aynı bilgi birden çok belgede geçiyorsa hangisi esas?** Örneğin karar tarihi için duruşma
   zaptı mı gerekçeli karar mı; tebliğ tarihi için mazbata mı UYAP kaydı mı?
4. **Hangi belge hangi süreyi başlatır?** Süre uzunluğu ve dayanağıyla birlikte; hukuk, idare ve
   ceza yargısı için ayrı ayrı.
5. **Hangi belge aşamayı ya da son durumu değiştirir?** Belge geldiğinde dosyanın aşaması / son
   durumu neye dönmeli?
6. **Belge türü listemiz yeterli mi?** Takip için önemli olup listede bulunmayan, birleştirilmesi
   ya da bölünmesi gereken türler var mı?

## 4. Cevap biçimi

İki eki doğrudan doldurmanız yeterli; sarı hücreler sizin içindir, her dosyanın ilk sayfasında
okuma kılavuzu ve her tabloda bir örnek satır var.

- **EK-1_Dava_Karti_ve_Dava_Takibi_Alanlari.xlsx** — A: dava kartı alanları (bilgi amaçlı, 20
  satır). B: dava takibi bilgileri (43 satır + sizin ekleyeceğiniz boş satırlar) → 1. soru.
- **EK-2_Belge_Turleri_ve_Veri_Eslemesi.xlsx** — 128 belge türü; her biri için bugün okunan,
  bugünkü etkisi ve işlenmiş belge adedi → 2., 4., 5. sorular. "Eksik Belge Türleri" sayfası → 6. soru.

3\. soruyu ve genel değerlendirmenizi serbest metin olarak iletebilirsiniz.

İki ilkemizi baştan belirtelim: belgeden okunamayan bilgi boş kalır, tahmin yazılmaz; her takip
kaydı hangi belgeden geldiğiyle birlikte saklanır. Önerilerinizi bu iki ilkeyle uyumlu
kurgulamanızı rica ederiz.

128 türün tamamını tek seferde doldurmak gerekmiyorsa, belge adedi yüksek türlerden (tebligat,
gerekçeli karar, istinaf / Danıştay / Yargıtay kararı, ATK ve bilirkişi raporu, ara karar, tensip,
duruşma zaptı, istinaf ve temyiz başvurusu) başlayıp partiler hâlinde göndermeniz bizim için
yeterli. Ne zaman dönebileceğinizi bildirirseniz planımızı ona göre yaparız.

Teşekkürler,
HUKDOK ekibi
