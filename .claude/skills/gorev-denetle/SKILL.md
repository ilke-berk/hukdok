---
name: gorev-denetle
description: Verilen kuyruk görevinin son commit'ini görev dosyasındaki kabul kriterlerine karşı bağımsız denetler; kod değiştirmez; SON satırı "SONUC: GECTI" ya da "SONUC: RET — sebep" olur.
---

# Görev: verilen görevi temiz gözle denetle

Prompt'un sonunda `GOREV: <id>` verilir. Sen kodu yazan oturum değilsin; işin itiraz etmek.
Kod DEĞİŞTİRME, commit atma, dosya yazma. Bulunduğun dizinde çalış (worktree olabilir).

## Adımlar
1. `gorevler/gorev/<id>.md` dosyasını oku: kabul kriterleri, dosya kapsamı, doğrulama komutları,
   işçinin Raporu.
2. `git log -1 --format="%h %s"` → mesajda `<id>` geçmiyorsa denetlenecek yeni commit yok:
   son satır `SONUC: RET — <id> için commit bulunamadı` (işçi commit'lemeden "bitti" demiş olabilir).
3. `git show --stat HEAD` + diff'i incele (büyükse dosya dosya). Ara:
   - **Kabul kriteri eksiği:** her kriter gerçekten karşılanmış mı, yoksa yüzeysel mi?
   - **Kapsam sızması:** dosya kapsamı dışında ya da "Dokunma" listesinde değişiklik var mı?
   - **Test hilesi:** silinen/gevşetilen test, skip, kapatılmış assert; Rapor'daki test sayısı
     tutarlı mı (sayı DÜŞTÜYSE kırmızı bayrak)?
   - **Bant ihlali:** frontend/docs görevi `docker compose` koşmuş mu (yanıltıcı test —
     konteyner ana dizini mount eder)? Backend görevi konteyner dışında pytest koşmuş mu?
   - **Log sözleşmesi:** deneme-düzeyi yola yeni ERROR eklenmiş mi?
   - **Rapor disiplini:** Rapor bölümü dolu mu, kararlar gerekçeli mi, KUYRUK.md'ye dokunulmamış mı?
4. Şüphen varsa doğrulama komutlarını KENDİN koş (bant kurallarına uyarak: frontend worktree'de
   yalnız `npm --prefix frontend test`; backend ana dizinde konteynerde pytest).
5. Bulgularını kısa maddelerle, dosya:satır referanslı yaz — sabah kullanıcı okuyacak.
6. SON SATIRIN kesinlikle şu ikisinden biri olsun, sonrasına hiçbir şey ekleme:
   - `SONUC: GECTI`
   - `SONUC: RET — <tek cümle somut sebep>`

RET yalnız gerçek eksik/yanlış içindir (kriter karşılanmamış, test kırmızı/silinmiş/hileli,
kapsam-bant ihlali, commit yok). Üslup ve zevk meselesi RET sebebi değildir — bulgu olarak
not et, GECTI ver.
