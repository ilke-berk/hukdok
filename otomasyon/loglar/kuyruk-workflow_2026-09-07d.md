# Gece Kuyrugu (workflow) · 2026-09-07d

## Ozet

2 gorev alindi · 2 isaretlendi · 0 bloke · 0 atlandi

## Isaretlenenler

| gorev | bant | commit | kapi | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G141 — Katalog: veriden kapalı liste (eşik + sıklık), secenek_etiketleri, `in` içinde null, sanal arama kolonu + secilebilir, HizliFiltre.sunum/etiket, müvekkil hızlı filtreleri, asistan "(boş)" | backend | `e1beb64` | GECTI (test temiz, kırmızı-yeşil kanıtlandı, ihlal yok) | GECTI (4 bulgu) | 3 tur; son parmak izi: 2712 passed / 3 skipped, ruff + mypy temiz. Ana repoda çalıştı (worktree yok), merge gerekmedi. SÖZLEŞME DEĞİŞTİ (plan §5.2 güncellendi): zaten liste tipli `karar_turu`/`case_stage`/`dosya_son_durumu`/`muvekkil_tipi`/`client_type` "işaretlenecek" değil "sabit kalır"; eşik karşılaştırması ≤; eşik altında `oneriler=null`; `secilebilir=false` kolon sıralamada da 422. Lokal veride `court` >100 DISTINCT → `metin_icerir` kalıyor (eşik 150 ile açılabilir — kullanıcı kararı). |
| G142 — Rapor şeridi: arama kutusu + kategori çipleri + veriden çoklu seçim (Sık/Tümü/(boş)) + var-yok ve "X yok" anahtarları + "boş olanlar" kaldırıldı + secilebilir=false gizli | frontend | `52c04b3` | GECTI (test temiz, kırmızı-yeşil kanıtlandı, ihlal yok) | GECTI (5 bulgu) | 3 tur; son parmak izi: vitest 66 dosya / 836 test yeşil, eslint 0, `tsc -b --force` 0. Worktree `C:/dev/hukudok-wt/G142` → merge yapıldı, entegrasyon yeşil, worktree temizlendi. Denetim tek gerçek kusur: `ChipSelect.tsx`'e sızan literal NUL byte'ı (çalışmayı etkilemiyor — temizlenmeli). Kilitli test dosyalarına ve hub dosyalara dokunulmadı; `ColumnSheet.tsx` değişmedi. |

### Testi değiştirmeden geçilemeyen noktalar (hattın doğru çalıştığının kanıtı)

- **G141:** Kod değişikliği sonrası 9 mevcut rapor testi beklenen şekilde kırmızıya düştü (g130 katalog anahtar kümesi; g137 grup/kontrol/hızlı filtre/öneri → seçenek). İzin kapsamındaki testler güncellendi; def sayısı sabit (32/25), assert sayısı arttı (82→84, 124→129). Değiştirilen test → gerekçe tablosu görev dosyasında.
- **G142:** Test katalogları yeni zorunlu alanları (`secenek_kaynagi`/`secenek_etiketleri`/`secilebilir`, `HizliFiltre.sunum`/`etiket`) taşımıyordu → izinli test dosyalarındaki `kolon()`/`hf()` yardımcılarına varsayılanlar eklendi. `expect(` sayıları azalmadı. Yeni `FilterControl.test.tsx` eski kodda kırmızı (kırmızı-yeşil kanıtı).

## Bloke

yok

## Karar bekleyenler

- `gorevTanimiHatali=true` olan görev yok; `kabulKarsilanmayan` boş.
- SORU (G141, kullanıcı kararı): Lokal veride `court` kolonu >100 DISTINCT olduğu için veriden kapalı liste açılmıyor, `metin_icerir` kalıyor (8 ms). Eşik 150'ye çekilsin mi?
- SORU (G142 → G143 docs turu): Görev tanımı arama placeholder'ını katalog `aciklama` alanından istiyor, ancak plan §5.2 / backend `KatalogKolon`'da bu alan YOK. Frontend tipte isteğe bağlı eklendi, yoksa "Ara..." gösteriliyor. Backend'e `aciklama` eklensin mi, yoksa sözleşmeden düşülsün mü?
- SORU (deploy sırası): G142 backend `in` içinde null'ı G141 ile paralel alıyor → iki görev BİRLİKTE deploy edilmeli; aksi halde "(boş)" seçimi 422 döner. Ayrı deploy planlanıyorsa sıralama teyit edilmeli.
- NOT (G141, kapsam dışı → G143): `prompts.py` "türetilmiş kolonlar filtrelenemez" cümlesi G137'den beri eksik. `docs/mimari/raporlama.md` de plan gereği G143'e bırakıldı.

## Izin engelleri

yok

## Atlananlar

yok (tavan nedeniyle atlanan: yok; zincirHatasi/teslimHatasi: yok)

## Plan uyarıları (koşucudan)

- G141/G142 görev dosyalarında ayrı "Dosya kapsamı" başlığı yok; dosya[] üst bilgi satırındaki `**Dosya kapsami:**` maddesinden alındı (G142'de SearchBox/ChipSelect/ToggleFilter YENİ dosyalar).
- G141 ve G142 dosya kesişimi yok, aynı anda koşabilir (KUYRUK notu: G141 ∥ G142). Backend bandında G141 `backend/routes/reports.py`'ye yalnız gerekirse dokunur.
- HEAD 423e17b (plan commit'i); `.claude/` dışında kirli dosya yok. `.claude/settings.local.json` (M) ve `.claude/launch.json` (??) oturum başında zaten kirliydi, dokunulmadı/commit'e alınmadı.
