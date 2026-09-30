# Gece Kuyrugu (workflow) · 2026-09-30c

## Özet

6 görev alındı · 0 işaretlendi · 1 bloke · 5 atlandı

Bu koşuda hiçbir görev tamamlanmadı, commit üretilmedi, merge yapılmadı. HEAD değişmedi (9ae92e1).
Zincirin başındaki G236 durunca ona bağlı beş görev (G237, G238, G239, G240, G241) hiç başlamadı.
Tavan nedeniyle atlanan: yok.

## İşaretlenenler

| görev | bant | commit | kapı | denetim | not |
| --- | --- | --- | --- | --- | --- |
| — | — | — | — | — | Bu koşuda işaretlenen görev yok |

## Bloke

### G236 · testi değiştirmeden geçilemedi — görev tanımı gözden geçirilmeli

**Başlık:** Yeni kartta numarayı sunucu verir (istemci değeri yok sayılır, müvekkilsiz 422, paralel kayıtta
409 yok) + `GET /api/cases/ofis-no-onizleme`; düzenlemede numara değişmez. Bant: backend.

Bu bir uygulama başarısızlığı DEĞİLDİR: işçi, mevcut testleri değiştirmeden görevin kabul kriterlerini
sağlamanın mümkün olmadığını kod yazmadan önce tespit edip durdu. Hat doğru çalıştı (test kilidi
korundu); çözülmesi gereken görev tanımıdır.

- **Durma sebebi:** `test-degistirmek-gerekti`
- **Durum:** uygulanmadı (`uygulandi=false`), doğrulama çalıştırılmadı (`verify=calistirilmadi`), tur sayısı 0,
  commit yok, kapı/denetim koşmadı, merge yapılmadı, entegrasyon: uygulanamaz.
- **Son parmak izi:** yok (hiçbir test/kapı koşusu yapılmadı).
- **Worktree:** yok (korunan worktree bulunmuyor).

**Denenen yaklaşımlar**

1. Kod yazmadan önce mevcut testler tarandı. `add_case`'i doğrudan çağıran testler veri sözlüğü bayrağıyla
   korunabilir; ancak `test_g196_status_kapisi.py` içindeki üç HTTP testi müvekkilsiz `POST /api/cases` için
   200 ve istemcinin gönderdiği `tracking_no` ile satır bekliyor. Hiçbir tasarım ikisini birlikte sağlamaz.

**Kök neden (işçi notundan; ayrı teşhis adımı koşmadı — `teshis` boş)**

Görevin iki kabul maddesi ("müvekkilsiz kayıt 422" ve "istemci `tracking_no` yok sayılır") mevcut, lokalde
geçen (dosya 31 passed) testlerle doğrudan çelişiyor:

- `test_pg_post_eski_deger_derdest_asama_ve_varsayilan`: tarafsız `POST /api/cases` → 200 bekler ve satırı
  `WHERE tracking_no='G196/TEMYIZ'` ile arar.
- `_pg_dava_ac` yardımcısını kullanan `test_pg_put_uclu_disi_400_hicbir_alan_degismez`.
- `_pg_dava_ac` yardımcısını kullanan `test_pg_takip_yolu_uclu_disi_kapida_durur_check_yok_error_yok`.

**Sonraki koşu için doğrulanan noktalar** (ayrıntı görev dosyasının Rapor bölümünde)

1. `add_case`'i doğrudan çağıran diğer testler (g045/g046/g055/g158/g190/g196 birim/tenant) ve
   `scripts/kartsiz_foy_kart_ac.py`, sunucu tahsisi route'un veri sözlüğüne koyduğu bayrakla açılırsa korunur.
   İmza değişmemeli — `test_faz5_settings_budget` ve tenant testi tek argümanlı sahte kullanıyor.
2. Avukat doğrulaması ve üçlü-dışı status 400'ü müvekkil kontrolünden ÖNCE kalmalı
   (`test_avukat_yazim_korumasi`, `test_pg_post_uclu_disi_400`).
3. `update_case` `tracking_no`'yu zaten yazmıyor.
4. Idempotency: `find_idempotent_commit_match` yalnız `duplicate_tracking_no` sonrası ve `tracking_no` birebir
   anahtarıyla çalışıyor; numara sunucudan gelince hiç tetiklenmez, intake tekrar isteği ikinci kart açar.
   `CaseIntakeCommitRequest`'te taslak kimliği YOK — numarasız eşleşme anahtarı tasarım kararı gerektirir.

**Çalışma ağacı durumu**

- `gorevler/gorev/G236.md` DEĞİŞTİ ama COMMIT EDİLMEDİ (BLOKE'de kod commit'lenmez; `KUYRUK.md`'ye
  dokunulmadı). Sıradaki backend görevinden önce bu dosya commit'lenmeli, yoksa ana dizinde kirli dosya kalır.
- `.claude/launch.json` koşu öncesinden beri izlenmiyor, dokunulmadı.

**Önerilen sonraki adım**

Aşağıdaki "Karar bekleyenler" bölümündeki iki karar verilmeden G236 yeniden koşulmamalı: (a) test taşıma izni
ya da 422 kuralının gevşetilmesi, (b) intake tekrar isteği için numarasız eşleşme anahtarı. Karar görev
dosyasına yazıldıktan sonra G236 tek başına koşulur; zincirin geri kalanı (G237, G238 → G239, G241 → G240)
ancak ondan sonra açılır.

## Karar bekleyenler

Teşhis adımı koşmadığı için `gorevTanimiHatali=true` işaretli kayıt yok; aşağıdaki sorular G236'nın işçi
notundan ve karşılanmayan kabul maddelerinden gelir.

**G236 — insan kararı gereken sorular**

1. `test_g196_status_kapisi.py` için taşıma izni verilecek mi (isteğe CLIENT taraf eklenir, satır dönen `id`
   ile aranır), yoksa `POST /api/cases`'te müvekkilsiz 422 kuralı mı gevşetilecek?
2. Intake/confirm tekrar isteğinin ikinci kart açmaması için eşleşme anahtarı ne olacak?
   (`CaseIntakeCommitRequest`'te taslak kimliği yok; numara sunucudan gelince mevcut `tracking_no` anahtarlı
   eşleşme hiç tetiklenmez.)

**G236 — karşılanmayan kabul maddeleri (hiçbiri uygulanmadı; her biri açık soru)**

- Yeni kayıtta istemci `tracking_no` yok sayılıp karar 023 formatında numara verilecek mi? — karşılanmadı
- Paralel iki kayıtta ardışık sıra, 409 yok — karşılanmadı
- Müvekkilsiz kayıt 422 — karşılanmadı (yukarıdaki 1. soruya bağlı)
- Önizleme ucu sayacı artırmaz — karşılanmadı
- Düzenleme numarayı değiştirmez (test) — karşılanmadı (test yazılmadı; `update_case`'in `tracking_no`
  yazmadığı yalnız okunarak görüldü)
- Intake/confirm tekrar isteği ikinci kart açmaz — karşılanmadı (yukarıdaki 2. soruya bağlı, yeni vaka)
- `client-sequence` ucu çalışır — dokunulmadı, ayrıca test edilmedi

**Plan uyarıları (görev tanımı netleştirilmeli)**

- G241: dosya kapsamında adı belirsiz kalemler var (yeni hook/api yardımcısı, mevcut müvekkil kategorisi
  yönetim bileşeni, testler) — `dosya[]` yalnız adı geçen yolları taşır. Bu kalemlerin yolları yazılacak mı?
- G236/G237: test dosyaları kapsamda joker/genel ifadeyle geçiyor (`test_g236_*.py`, "ilgili `*.test.ts(x)`").
  Somut dosya adları yazılacak mı?

## İzin engelleri

yok

## Atlananlar

| görev | bant | sebep | worktree (temizlenmedi) |
| --- | --- | --- | --- |
| G238 | backend | bağımlılık bu koşuda tamamlanmadı: G236 | — |
| G237 | frontend | bağımlılık bu koşuda tamamlanmadı: G236 | `C:/dev/hukudok-wt/G237` |
| G239 | backend | bağımlılık bu koşuda tamamlanmadı: G237, G238 | — |
| G241 | frontend | bağımlılık bu koşuda tamamlanmadı: G237 | `C:/dev/hukudok-wt/G241` |
| G240 | docs | bağımlılık bu koşuda tamamlanmadı: G239, G241 | `C:/dev/hukudok-wt/G240` |

Zincir hatası ya da teslim hatası olan görev yok. Atlanan beş görevin hiçbirinde iş yapılmadı
(uygulanmadı, commit yok). G237, G241 ve G240 için veride worktree yolu kayıtlı ve
`worktreeTemizlendi=false`; bu dizinlerin diskte durup durmadığı bu rapor için ayrıca doğrulanmadı.
