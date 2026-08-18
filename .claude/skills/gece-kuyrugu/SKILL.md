---
name: gece-kuyrugu
description: Gece kuyruğunu Workflow tabanlı koşucuyla (v3) başlatır — ön kontroller, .claude/workflows/gece-kuyrugu.js çağrısı, koşu sonrası rapor özeti. kuyruk-kosusu.ps1'in CLI'sız halefidir; push/ssh/deploy YAPMAZ. İlk/riskli koşularda önce kuru koşu önerir.
---

# Görev: gece kuyruğunu Workflow koşucusuyla işlet

Sistem tanımı: [otomasyon/README.md](../../../otomasyon/README.md) "v3 — Workflow koşucusu"
bölümü. Kuyruk formatı ve görev sözleşmeleri değişmedi (`gorevler/README.md`).

## 1. Ön kontroller (koşudan önce, sırayla)

1. **Tek koşucu kuralı:** Ana dizinde başka bir aktif görev/koşucu oturumu çalışıyorsa
   BAŞLATMA — kullanıcıya sor. (Backend bandı ve merge'ler ana dizini kullanır; iki koşucu
   birbirinin commit/index durumunu bozar.)
2. `git status --porcelain` — `.claude/` ve `otomasyon/loglar/` dışında kirli dosya varsa:
   kullanıcıya göster; commit/stash ya da `kirliKabul: true` (backend görevleri ve merge'ler
   ertelenir) kararı kullanıcının.
3. Kuyrukta backend görevi varsa Docker Desktop açık olmalı (`docker info`). Konteyneri
   koşucu kendisi kaldırır (`docker compose up -d`), sen kaldırmak zorunda değilsin.
4. **Uyku engeli:** `Start-Process presentationsettings -ArgumentList "/start" -PassThru`
   ile sunum modunu aç, süreç id'sini not et; koşu bitince `Stop-Process` ile kapat.
   `cmd /c` ile ÇAĞIRMA — süresiz bloklar (2026-08-11 dersi). Kapak kapatılırsa makine
   yine uyur; kullanıcıya hatırlat.
5. OneDrive senkronunu gece için duraklatmayı öner (repo OneDrive altında; dosya kilidi
   riski). Worktree'ler zaten OneDrive dışında (`C:\dev\hukudok-wt`).
6. Tarihi belirle (bugünün tarihi, `YYYY-AA-GG`) — betikte `Date.now()` yasak, `tarih`
   argümanı her koşuda verilir.

## 2. Çalıştırma

Workflow aracını şu şekilde çağır (ad çözümlemesine güvenme, yol ver):

- `scriptPath`: `.claude/workflows/gece-kuyrugu.js`
- `args` örneği: `{ "tarih": "2026-08-18", "kuru": true }`

| Parametre | Varsayılan | Ne yapar |
| --- | --- | --- |
| `tarih` | `"tarihsiz"` | Rapor dosya adı — her koşuda ver |
| `kuru` | `false` | `true`: hiçbir şey yazmadan planı/dalgaları göster |
| `tavan` | `6` | Bu koşuda en fazla kaç görev |
| `gorev` | hepsi | `["G061","G062"]` — yalnız bunlar |
| `kirliKabul` | `false` | Kirli ağaçta worktree bantlarına izin (backend ertelenir) |
| `turTavani` / `teshisHakki` | `8` / `1` | Döngü mühendisliği sınırları |
| `butceTabani` | `60000` | Bu kadar token kalmadan yeni iş başlamaz |
| `worktreeKok` | `C:/dev/hukudok-wt` | Worktree kökü (OneDrive DIŞI kalmalı) |

- **İlk koşu ya da yeni plan sonrası daima önce `kuru: true`** — dalga planını kullanıcıya
  göster, onay al, sonra gerçek koşuyu başlat.
- Ölçek: görev başına ~4-7 ajan çalışır; kuyruk kalabalıksa 15-ajan rehberinin üstüne
  çıkılabilir. Kullanıcı maliyeti kısmak isterse `tavan`/`gorev` ile daralt.

## 3. Koşu bitince

1. Dönen özeti ve `otomasyon/loglar/kuyruk-workflow_<tarih>.md` raporunu oku.
2. Kullanıcıya sırayla özetle: **işaretlenenler** (commit'leriyle) → **BLOKE'ler**
   (sebep + korunan worktree yolu + önerilen adım) → **karar bekleyenler** (görev tanımı
   hatalı / kabul karşılanamayan) → **izin engelleri** (varsa: settings izin listesi
   YALNIZ bu ölçümle genişletilir; koşucu/skill kendi iznini genişletmez).
3. Sunum modunu kapat (`Stop-Process`).

## Koşulsuz yasaklar

`git push`, `ssh`, `scp`, `gcloud`, deploy/rollback başlatmak, `.claude/settings*.json`
düzenlemek (izin genişletme insan işi), koşu sırasında ana dizinde elle iş yapmak.
Sabah inceleme + push + deploy kullanıcıdadır.
