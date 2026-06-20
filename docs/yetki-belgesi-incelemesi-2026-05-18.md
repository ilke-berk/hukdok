# Yetki Belgesi İncelemesi — 2026-05-18

Production'da aktif kullanılan yetki belgesi akışında bulunan sorunların raporu.

**İncelenen dosyalar:**
- `frontend/src/components/YetkiBelgesiModal.tsx` (3-adımlı modal)
- `backend/yetki_belgesi_generator.py` (UDF üretici)
- `backend/routes/documents.py` (`POST /api/yetki-belgesi/udf`)

**Tetikleyici:** Kullanıcı "Barış Yücel için yetki belgesi oluştururken sicil no görünüyor ama sistemde yok, rastgele mi üretiliyor?" sorusu. Rastgele üretim yok; ana suçlu **placeholder metinleri**. Detaylı inceleme aşağıdaki ek sorunları ortaya çıkardı.

---

## Düzeltilenler

### ✅ B0 — Placeholder metinleri gerçek veri sanılıyor (DÜZELTİLDİ)

`YetkiBelgesiModal.tsx` içinde 11 input alanında `placeholder` öznitelikleri vardı:

| Alan | Eski placeholder | Sorun |
|---|---|---|
| Büro adresi | `BÜYÜKDERE CADDESİ NO:239/9 SARIYER İSTANBUL` | Gerçek adres gibi görünüyor |
| Veren TC | `00000000000` | Sıfırlı maske TC sanılıyor |
| Veren Sicil | `18670` | **5 haneli gerçek bir sicil no görüntüsü** — kullanıcı bunu Barış Yücel için sistem tarafından doldurulmuş veri sandı |
| Yetkili TC | `00000000000` | aynı |
| Yetkili Sicil | `24174` | aynı (gerçek sicil benzeri) |
| Müvekkil Adres | `MASLAK MAH. MASLAK MEYDAN SOK. NO.3/14` | aynı |
| Müvekkil İl | `SARIYER İSTANBUL` | aynı |
| Vergi/TC No | `3450249570` / `00000000000` | aynı |
| Noterlik | `BEYOĞLU 60. NOTERLİĞİ` | aynı |
| Tarih | `27.01.2020` | aynı |
| Yevmiye | `3639` | aynı |

**Çözüm:** Hepsi kaldırıldı. (`CommandInput` arama kutusundaki `Avukat ara...` placeholder'ları gerçek veri olmadığı için bırakıldı.)

---

## Kritik bug'lar (veri doğruluğuna doğrudan etki eden)

### 🔴 B1 — Belgede "Vergi Daire ve No" alanı veren avukatın TC'si ile dolduruluyor

`backend/yetki_belgesi_generator.py:80-85`:
```python
if tc_v:
    veren_parts.append(f"T.C. Kimlik No: {tc_v}")
if sicil_v:
    veren_parts.append(f"{sicil_v} sicil no'lu")
if tc_v:
    veren_parts.append(f"Vergi Daire ve No: {tc_v}")  # ← TC ikinci kez kullanılıyor
```

**Sorun:**
- "Vergi Daire ve No" iki ayrı bilgidir (Vergi Dairesi adı + Vergi Numarası). Form bunları hiç sormuyor.
- Veren avukatın TC'si önce "T.C. Kimlik No: 12345678901" sonra "Vergi Daire ve No: 12345678901" olarak **iki kez** yazdırılıyor.
- Aynı bug HTML önizlemede de var: `YetkiBelgesiModal.tsx:506-508`.

**Etki:** Hukuken yanlış. UYAP'a giden belgede tek satır iki kez tekrarlanıyor; gerçek vergi dairesi (örn. "Beşiktaş VD") hiç bulunmuyor.

**Öneri:**
- Lawyers tablosuna `vergi_dairesi` kolonu ekle.
- Eğer vergi dairesi DB'de boşsa, satırı tamamen atla.
- TC'nin "Vergi Daire ve No" olarak tekrar yazılması kesinlikle kaldırılmalı.

---

### 🔴 B2 — DB'de avukat varsa ama alanı boşsa, localStorage cache'i hiç kullanılmıyor

`frontend/src/components/YetkiBelgesiModal.tsx:92-99`:
```ts
function lookupAvukat(ad: string): { tc: string; sicil: string; address: string } {
    const cache = loadCache();
    const normalAd = normalizeName(ad);
    const match = lawyers.find(l => normalizeName(l.name) === normalAd);
    if (match) {
        return { tc: match.tc_no || "", sicil: match.sicil_no || "", address: match.address || "" };
    }
    return { ...(cache[normalAd] || { tc: "", sicil: "" }), address: "" };
}
```

**Senaryo:** Barış Yücel DB'de var (`sicil_no=NULL`). Kullanıcı geçen sefer yetki belgesi yaparken sicil_no elle yazdı, `goToStep3` cache'e kaydetti. Bir sonraki açılışta:
- `match` bulunuyor (DB'de var) → DB değerleri dönüyor (sicil = `""`)
- Cache hiç okunmuyor → kullanıcı **her seferinde elden tekrar yazıyor**

**Öneri:** Fallback hiyerarşisi `DB > cache > boş` olmalı:
```ts
if (match) {
    const c = cache[normalAd] || {};
    return {
      tc: match.tc_no || c.tc || "",
      sicil: match.sicil_no || c.sicil || "",
      address: match.address || "",
    };
}
```

---

### 🔴 B3 — `useEffect [step]` bağımlılığı: Geri butonu manuel girişleri siliyor

`frontend/src/components/YetkiBelgesiModal.tsx:102-111`:
```ts
useEffect(() => {
    if (step !== 2) return;
    const v = lookupAvukat(verenAd);
    setVerenDetay({ ad: verenAd, tc: v.tc, sicil: v.sicil });   // ← overwrite!
    if (v.address) setBuroAdres(v.address);
    setYetkiliDetaylar(yetkiliAdlar.map(ad => {
        const l = lookupAvukat(ad);
        return { ad, tc: l.tc, sicil: l.sicil };
    }));
}, [step]);
```

**Senaryo:**
1. Adım 1: Barış Yücel'i veren seçer
2. Adım 2: Form açılır (DB'den sicil = "" geliyor). Kullanıcı elden `24174` yazar.
3. Adım 3: Önizler. `goToStep3` cache'e yazar — OK.
4. **Geri** butonu → Adım 2'ye döner. useEffect tekrar tetiklenir. `lookupAvukat` çağrılır. DB'de match bulunduğu için (B2 nedeniyle) sicil = `""` dönüyor.
5. `setVerenDetay({...sicil: ""})` → **kullanıcının az önce yazdığı `24174` silinir**.

**Etki:** Kullanıcı geri tuşunu kullandığında manuel veri kaybı.

**Öneri:** B2 düzelirse bu büyük ölçüde çözülür. Ek olarak, dependency'ye `[step, verenAd, yetkiliAdlar.join(",")]` eklenip "form daha önce doldurulmuşsa atla" kontrolü konabilir.

---

### 🔴 B4 — Yetkili kılınan dış avukatlar için "Aynı adreste mukim" yazıyor

`backend/yetki_belgesi_generator.py:97`:
```python
for idx, av in enumerate(yetkililar, 1):
    ...
    parts = ["Aynı adreste mukim"]   # ← her zaman aynı adres varsayımı
    if tc_y: parts.append(...)
    if sicil_y: parts.append(...)
```

**Sorun:**
- Hanyaloğlu-Acar büroda 4 iç avukat (gorev=`AVUKAT`) var, 74'ü `DIŞ AVUKAT` (export'tan bakınca).
- Dış avukatlara yetki verildiğinde belge "aynı adreste mukim" diyor — **olgusal olarak yanlış**.
- `lawyers.address` kolonu zaten DB'de var ama yetkili kılınanlar için hiç kullanılmıyor.

**Öneri:**
- Yetkili kılınanın `gorev='DIŞ AVUKAT'` olduğu durumda: form aşamasında ayrı adres alanı göstermek veya `lawyers.address`'i kullanmak.
- Generator'da: `parts = [f"{uc(adres)} adresinde mukim"]` if adres geldiyse, yoksa "Aynı adreste mukim".

---

## Orta öncelik sorunlar (UX / tutarlılık)

### 🟠 B5 — UDF indirme hatasında kullanıcıya bildirim yok

`frontend/src/components/YetkiBelgesiModal.tsx:187-189`:
```ts
} catch (e) {
    console.error("UDF indirme hatası:", e);
}
```

**Sorun:** Sadece DevTools console'a yazıyor. Kullanıcı için: spinner durur, dosya gelmez, neden başarısız olduğu hakkında hiçbir ipucu yok.

**Öneri:** Toast/Alert göster (proje muhtemelen `sonner` veya `react-hot-toast` kullanıyor — yetki_belgesi_plani.md'ye göre toaster mevcut).

---

### 🟠 B6 — Tarih ve TC alanlarında validasyon yok

- **Tarih:** Label "Tarih (GG.AA.YYYY)" diyor ama input regex yok. Kullanıcı `27/01/2020`, `27-01-20`, `Ocak 27` yazabilir → UDF'e aynen geçer.
- **TC:** Sadece `maxLength={11}`. Harf, boşluk girilebilir. TC checksum doğrulaması yok.
- **Yevmiye:** Tipik olarak numerik ama herhangi bir kontrol yok.

**Öneri:**
- TC için `onChange`'de `value.replace(/\D/g, "").slice(0, 11)`.
- Tarih için maskeli input veya date picker.

---

### 🟠 B7 — Önizleme ile UDF'in DAYANAK satırı farklı

- **Önizleme** (`YetkiBelgesiModal.tsx:543`): `{toUpper(dayanakSatiri)}` — tüm satır büyük harf
- **UDF** (`yetki_belgesi_generator.py:120-126`): Sadece `day_not` `uc()` ile büyük; `day_tar`, `day_yev` olduğu gibi

**Etki:** Kullanıcının önizlemede gördüğü ile dışa aktardığı belge görsel olarak farklı. Tutarsızlık güveni sarsıyor.

**Öneri:** Her ikisinde de aynı kuralı uygula (önerim: noterlik büyük, tarih/yevmiye olduğu gibi — onlar zaten sayısal).

---

### 🟠 B8 — `step2Valid` sadece veren TC'sini kontrol ediyor

`YetkiBelgesiModal.tsx:220`:
```ts
const step2Valid = verenDetay.tc.trim() !== "";
```

**Sorun:**
- Veren'in sicil_no'su (hukuken daha kritik) kontrol edilmiyor.
- Yetkili kılınanların hiçbir alanı kontrol edilmiyor — boş ad ile devam edebilir.
- Müvekkilin TC/Vergi No boş olabilir.
- Dayanak vekaletname tamamen boş olabilir.

**Öneri:** En azından veren için sicil_no şart, yetkililer için en azından ad gerekli olmalı.

---

## Düşük öncelik / not edilenler

### 🟡 B9 — Print penceresi popup blocker tarafından engellenirse sessiz başarısızlık

`YetkiBelgesiModal.tsx:134-135`:
```ts
const win = window.open("", "_blank", "width=820,height=960");
if (!win) return;
```
Hiçbir uyarı yok. Kullanıcı "Yazdır" butonuna basar, hiçbir şey olmaz, sebep popup blocker.
uyarı ekle popup izin verin gibi bir şey
---

### 🟡 B10 — Frontend'in oluşturduğu indirme dosya adı Türkçe karakter içeriyor

`YetkiBelgesiModal.tsx:182`:
```ts
a.download = `yetki_belgesi_${(client.name || "belge").replace(/\s+/g, "_").substring(0, 30)}.udf`;
```
Backend `Content-Disposition` header'ında ASCII'leştirilmiş ad veriyor ama `a.download` attribute'u onu override ediyor. Bazı dosya sistemlerinde "İ", "Ş" gibi karakterler sorun çıkarabilir.

**Öneri:** Frontend'de de backend'deki gibi NFKD normalize edip `[^A-Za-z0-9_]` temizliği yap.

---

### 🟡 B12 — Backend'de tenant/yetki kontrolü yok

`/api/yetki-belgesi/udf` sadece `get_current_user` istiyor; veriler tamamen body'den okunuyor, DB'den hiçbir şey çekilmiyor. Yani teorik olarak bir kullanıcı başka müvekkilin adına yetki belgesi oluşturabilir. Pratikte zararsız (yine kendi üretip kendi indiriyor), ama IDOR incelemesinin tutarlılığı için not edildi.

---

## Önerilen Yol Haritası

### Hızlı (1-2 saat)
1. ~~Placeholder'ları kaldır~~ ✅
2. **B1:** Generator'da TC'nin "Vergi Daire ve No" olarak tekrar yazılmasını kaldır
3. **B5:** UDF hata mesajını toast ile göster
4. **B7:** Önizleme/UDF DAYANAK satırı tutarlılığı

### Orta (yarım gün)
5. **B2 + B3:** `lookupAvukat` fallback hiyerarşisini düzelt + useEffect manuel girişleri korusun
6. **B6:** TC ve tarih validasyonu (frontend)
7. **B8:** Step 2 validasyonunu sıkılaştır

### Uzun vade
8. **B4:** Yetkili dış avukat için ayrı adres alanı (DB'den `lawyers.address` çekilebilir, veya form'da gösterilebilir)
9. Lawyers tablosuna `vergi_dairesi` kolonu ekleyip B1'i tam çöz
10. **B11:** Cache key'ine tenant_id ekle

---

## Yan Bulgu: Barış Yücel'in DB Kaydı

Soru veren senaryoda Barış Yücel için sicil_no NULL:
```
id=6  code=BBA  name=BARIŞ YÜCEL  sicil_no=  tc_no=  gorev=AVUKAT
```

`gorev='AVUKAT'` olduğu için iç büro avukatı. Sicil/TC bilgisi DB'ye girilirse her seferinde elle yazmaya gerek kalmaz. Gerçek bilgiler verilirse aşağıdaki SQL ile güncellenebilir:
```sql
UPDATE lawyers SET sicil_no = ?, tc_no = ? WHERE code = 'BBA';
```
