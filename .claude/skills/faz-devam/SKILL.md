---
name: faz-devam
description: Sertleştirme takibindeki sıradaki tamamlanmamış paketi uçtan uca bitirir (kod+test+doküman+tek commit); deploy/push yapmaz, tek paketle durur.
---

# Görev: sıradaki sertleştirme paketini bitir

Tek çağrı = TEK paket. Paket bitince (commit dahil) dur; sonraki pakete geçme.

## 1. Durumu oku
- `docs/plan/guvenilirlik-sertlestirme-uygulama-takibi.md` dosyasını oku: çalışma protokolü, paket listesi, son durum notları.
- Durum notlarında çözülmemiş `BLOCKED` varsa: hiçbir şey değiştirme, son mesajında `BLOCKED — kullanici mudahalesi gerekli` yaz, dur.
- İlk işaretsiz `- [ ]` paketi bul:
  - Hiç kalmadıysa: son mesajında aynen `TUM PAKETLER TAMAM` yaz, dur.
  - Paket FAZ 6'daysa (6-A/6-B): son mesajında aynen `FAZ 6 GECE KAPSAMI DISI` yaz, dur. (docs reorganizasyonu bu takip dosyasının kendisini de taşıyacağı için gözetimsiz yapılmaz.)
- Ana planın (`docs/plan/guvenilirlik-sertlestirme-plani-2026-08-04.md`) YALNIZ ilgili faz bölümünü oku — paket satırındaki `[x.y]` numaraları o bölümün maddeleridir. Eski denetim raporlarını ve arşiv planlarını açma.

## 2. Çalışma ağacını değerlendir
- `git status --porcelain` çıktısına bak (`.claude/` altını yok say).
- Kirli dosyalar paketin kapsamına giriyorsa: bunlar yarım kalmış önceki oturumun işidir — önce mevcut değişiklikleri OKU, üzerine devam et. Sıfırdan yazma, ezme. İş zaten tamamsa yalnız test + doküman + commit adımları kalmış demektir.
- Paket kapsamına GİRMEYEN kirli dosya varsa: o dosyalara dokunma; takip dosyasının durum notlarına `BLOCKED (<paket>): kapsam disi kirli dosyalar: <liste>` satırı ekle, kod commit'leme, dur.

## 3. Paketi uygula
- SADECE paketin dosya kümesine dokun; kapsam dışı refactor yok. Kapsam dışı ciddi bulgu görürsen düzeltme — durum notuna `NOT:` olarak yaz.
- Dosya değişikliği daima Edit/Write tool ile (PS5.1 Get/Set-Content Türkçe içeriği çift kodlar — asla shell ile dosya yazma).
- Büyük dosyaları (ör. `frontend/src/pages/NewCase.tsx` ~1700 satır) bölüm bölüm oku; geniş keşif gerekiyorsa Explore ajanına devret, ana oturuma özetle dön.
- Log sözleşmesi: deneme-düzeyi hatalar WARNING, nihai başarısızlık TEK ERROR (GCP ERROR-oranı alarmı ≥5/5dk beslenmemeli).
- Gece koşusunda tarayıcı/görsel doğrulama YOK; vitest/pytest kanıtı yeterli. Görsel kontrol gerektiren noktaları durum notuna "izlenecek" olarak yaz.

## 4. Test
- Backend değiştiyse (konteynerde): `docker compose exec -T backend python -m pytest -q` + önceki oturumlarla aynı şekilde konteynerde ruff + mypy.
- Frontend değiştiyse (host'ta): `npm --prefix frontend test` (cd kullanma; komut repo kökünden koşar).
- Kırmızı → düzelt ve yeniden koş. Düzeltemiyorsan: kodu COMMIT'LEME; durum notlarına `BLOCKED (<paket>): <tek satır sebep>` ekle, son mesajında BLOCKED durumunu belirt, dur.

## 5. Kapat
- Takip dosyasında paketin kutusunu `[x]` yap + "Durum notları"na mevcut formatta TEK satır ekle (en yeni üstte): tarih, paket, ne yapıldı, alınan kararlar ve gerekçeleri, test sayıları, izlenecekler.
- Paket satırında "Deploy #N" işareti varsa nota `DEPLOY #N HAZIR — kullanici onayi bekleniyor` ibaresini ekle. Deploy'u SEN YAPMA.
- Kod + doküman AYNI commit'te: mesaj `feat: <özet> (Faz X-Y)` biçiminde (içeriğe göre fix/refactor öneki olabilir) + `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` satırı. `git add` ile YALNIZ dokunduğun dosyaları ekle; `git add -A` / `git add .` yasak.
- Commit sonrası dur. Son mesajında: paket adı, commit hash'i, test sonuçları, izlenecekler.

## Koşulsuz yasaklar
- `git push`, `ssh`, `scp`, `gcloud`, `deploy.sh`, `rollback.sh` — uzak repoya ve prod'a dokunan her şey.
- `git reset --hard`, `git checkout`/`git restore` ile mevcut değişiklik silmek, `docker compose down -v`, volume silme.
- Sonraki pakete geçmek; takip dosyası dışındaki dokümanları yeniden düzenlemek.
