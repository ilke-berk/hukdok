"""
Mevcut tüm davaların tracking_no alanını geriye dönük düzeltir.

- Kategori: müvekkilin clients.category alanından okunur (yoksa isimden tahmin edilir)
- Sıra no: her müvekkil için davalar opening_date ASC sıralanır (null → sona)
- Kuru çalıştırma: python retag_tracking_nos.py --dry-run

Kullanım:
  python retag_tracking_nos.py            # Gerçek güncelleme
  python retag_tracking_nos.py --dry-run  # Sadece önizleme, DB'ye yazmaz
"""

import sys
import os
import argparse
import re
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv("../.env")

import models
from database import SessionLocal

# ─── MAPPING TABLOLARI (frontend/caseNumberUtils.ts ile eşleşmeli) ────────────

CATEGORY_MAP = {
    "DOKTOR":       "D1",
    "ÖZEL HASTANE": "H2",
    "SİGORTA":      "S0",
    "HASTA":        "H1",
}

INSURANCE_CODES = {
    "AK": "1", "ANADOLU": "2", "AXA": "3",
    "CORPUS": "4", "QUICK": "4", "EUREKO": "5",
    "NIPPON": "6", "SOMPO": "7",
}

PROCESS_MAP = {
    "Hukuk":        "HUKUK",
    "İdari Yargı":  "IDARI",
    "İdare":        "IDARE",
    "Ceza":         "CEZAA",
    "İcra":         "ICRAA",
    "Arabuluculuk": "ARABU",
    "Savcılık":     "SAVCI",
    "Tahkim":       "TAHKM",
    "Vergi":        "VERGI",
    "Danışmanlık":  "DANIS",
}

# ─── YARDIMCI FONKSİYONLAR ───────────────────────────────────────────────────

def _normalize_ascii(s: str) -> str:
    return (s.replace("ı", "i").replace("ğ", "g").replace("ü", "u")
             .replace("ş", "s").replace("ö", "o").replace("ç", "c")
             .replace("İ", "I").replace("Ğ", "G").replace("Ü", "U")
             .replace("Ş", "S").replace("Ö", "O").replace("Ç", "C"))

def _tr_upper(s: str) -> str:
    return _normalize_ascii(s).upper()

# Kurum isimlerinde anlamsız jenerik kelimeler
_CORP_STOP = {
    "SIGORTA", "HAYAT", "ANONIM", "TURK", "SIRKETI", "KOOPERATIFI",
    "TIC", "TICARETI", "SAN", "SANAYI", "SANAYII",
    "INS", "INSAAT", "TAAHHUT", "TAAHHÜTÜ",
    "LTD", "STI", "AS",
    "HASTANE", "HASTANESI", "SAGLIK", "HIZ", "HIZMETLERI", "HIZM",
    "OZEL", "TIBBI", "MALZ",
    "SITE", "SITESI", "YONETICILIGI", "YONETIM", "KURULU", "MERKEZ",
    "VE", "VEYA", "VEYA",
    "PAZ", "PAZARLAMA", "DAG", "DAGITIM",
    "ORG", "ORGANIZASYON", "YAPIM", "TANITIM",
    "URETIM", "ISLETMECILIGI", "DANISMANLIK",
    "GLOBAL", "SISTEMLERI", "HIZMETLER",
}

def _slugify_name(name: str) -> str:
    """Kişi adları için: ilk isim baş harfi + soyisim  →  I_KUTLUK.."""
    if not name:
        return "XXXXXXXXXX"
    clean = re.sub(r"[^A-Z\s]", "", _normalize_ascii(name).upper())
    parts = clean.split()
    if not parts:
        return "XXXXXXXXXX"
    if len(parts) == 1:
        return parts[0].ljust(10, ".")[:10]
    surname = parts[-1]
    first_initial = parts[0][0]
    return (f"{first_initial}_{surname}").ljust(10, ".")[:10]

def _slugify_corp(name: str) -> str:
    """Kurum adları için: jenerik kelimeler atılır, ilk anlamlı kelime alınır  →  ANADOLU.."""
    if not name:
        return "XXXXXXXXXX"
    clean = re.sub(r"[^A-Z\s]", "", _normalize_ascii(name).upper())
    parts = [p for p in clean.split() if p not in _CORP_STOP and len(p) > 1]
    if not parts:
        # tüm kelimeler jenerikse ham ilk kelimeyi kullan
        raw = re.sub(r"[^A-Z\s]", "", _normalize_ascii(name).upper()).split()
        parts = raw[:1] if raw else ["KURUM"]
    return parts[0][:10].ljust(10, ".")

def _client_key(name: str) -> str:
    """Müvekkil isimlerini normalleştirerek gruplama anahtarı üretir."""
    clean = _tr_upper(name.strip())
    # "DR." / "DR" suffix'ini kaldır
    for suffix in [" DR.", " DR"]:
        if clean.endswith(suffix):
            clean = clean[:-len(suffix)].strip()
    return clean

def _get_category_code(category: str, client_name: str) -> str:
    norm_cat  = _tr_upper(category or "")
    norm_name = _tr_upper(client_name or "")

    block1 = "X1"
    for key, val in CATEGORY_MAP.items():
        if _tr_upper(key) in norm_cat:  # normalize key too (Ö→O, İ→I etc.)
            block1 = val
            break

    is_sigorta = "SIGORTA" in norm_cat or "SIGORTA" in norm_name
    if is_sigorta:
        if block1 == "X1":
            block1 = "S0"
        for key, code in INSURANCE_CODES.items():
            if key in norm_name:
                block1 = f"S{code}"
                break

    return block1

_PERSON_CATS = {"DOKTOR", "HASTA", "BIREYSEL"}

def generate_tracking_number(client_name: str, category_code: str,
                              sequence: int, process_type: str,
                              service_type: str = "00000",
                              client_category: str = "") -> str:
    norm_cat = _tr_upper(client_category or "")
    if norm_cat in _PERSON_CATS or not norm_cat:
        block2 = _slugify_name(client_name or "")
    else:
        block2 = _slugify_corp(client_name or "")
    block3 = str(sequence).zfill(4)
    block4 = PROCESS_MAP.get(process_type or "", "HUKUK")
    return f"{category_code}.{block2}.{block3}.{block4}.{service_type}"

# ─── ANA MANTIK ───────────────────────────────────────────────────────────────

def _name_priority(cat_norm: str) -> int:
    """Kişi < kurum < sigorta önceliği. Düşük = önce seçilir."""
    if cat_norm == "DOKTOR":   return 0
    if cat_norm == "HASTA":    return 1
    if cat_norm == "BIREYSEL": return 2
    if cat_norm == "":         return 3  # bilinmiyor, muhtemelen kişi
    if "SIGORTA" in cat_norm:  return 10
    return 5  # kurum, hastane, klinik vs.


def run(dry_run: bool = True):
    db = SessionLocal()
    try:
        # 1. Tüm davalar
        all_cases = db.query(models.Case).all()

        # isim → category
        name_to_category: dict[str, str] = {}
        for c in db.query(models.Client).all():
            norm = _tr_upper((c.name or "").strip())
            name_to_category[norm] = c.category or ""

        # case_id → tüm CLIENT tarafları (kategoriyle)
        all_parties: dict[int, list[tuple[models.CaseParty, str]]] = defaultdict(list)
        for p in db.query(models.CaseParty).filter_by(party_type="CLIENT").all():
            cat = name_to_category.get(_tr_upper(p.name.strip()), "")
            all_parties[p.case_id].append((p, cat))

        def pick_name_party(case_id: int):
            """İsim bloğu için: kişiyi (doktor/bireysel) sigorta/kuruma tercih et."""
            parties = all_parties.get(case_id, [])
            if not parties:
                return None, ""
            best = min(parties, key=lambda pc: _name_priority(_tr_upper(pc[1])))
            return best[0], best[1]

        def best_cat_code(case_id: int) -> str:
            """Kategori kodu için: TÜM müvekkillere bak, en özgül kodu seç (sigorta > doktor > X1)."""
            parties = all_parties.get(case_id, [])
            codes = [_get_category_code(cat, p.name) for p, cat in parties]
            # Öncelik: özgül sigorta (S1-S7) > S0 > D1 > H2 > H1 > X1
            for code in codes:
                if code.startswith("S") and code != "S0":
                    return code
            for code in codes:
                if code == "S0": return code
            for code in codes:
                if code != "X1": return code
            return codes[0] if codes else "X1"

        # 2. Davalar müvekkil (isim tarafı) bazında grupla
        groups: dict[str, list[models.Case]] = defaultdict(list)
        case_name_party: dict[int, models.CaseParty] = {}
        case_name_cat:   dict[int, str] = {}

        for case in all_cases:
            party, cat = pick_name_party(case.id)
            if party:
                key = _client_key(party.name)
                groups[key].append(case)
                case_name_party[case.id] = party
                case_name_cat[case.id]   = cat
            else:
                groups[f"__NO_CLIENT_{case.id}__"].append(case)

        # 3. Mevcut tracking_no seti
        existing_tracking_nos: set[str] = {c.tracking_no for c in all_cases}

        # 4. Her grubu işle
        updates: list[tuple[int, str, str]] = []

        for key, cases in groups.items():
            if key.startswith("__NO_CLIENT_"):
                continue

            cases_sorted = sorted(
                cases,
                key=lambda c: (c.opening_date is None, c.opening_date or "", c.id)
            )

            for seq, case in enumerate(cases_sorted, start=1):
                party    = case_name_party[case.id]
                category = case_name_cat[case.id]
                cat_code = best_cat_code(case.id)

                new_no = generate_tracking_number(
                    client_name     = party.name,
                    category_code   = cat_code,
                    sequence        = seq,
                    process_type    = case.file_type or "",
                    service_type    = case.service_type or "00000",
                    client_category = category,
                )

                # Çakışma varsa suffix ekle
                base_no = new_no
                suffix  = 2
                while new_no in existing_tracking_nos and new_no != case.tracking_no:
                    new_no = f"{base_no}-{suffix}"
                    suffix += 1

                if new_no != case.tracking_no:
                    updates.append((case.id, case.tracking_no, new_no))
                    existing_tracking_nos.discard(case.tracking_no)
                    existing_tracking_nos.add(new_no)

        # 5. Rapor
        print(f"\n{'='*70}")
        mode_label = "DRY RUN (DB'YE YAZILMADI)" if dry_run else "GERCEK GUNCELLEME"
        print(f"  RETAG TRACKING NOs  ---  {mode_label}")
        print(f"{'='*70}")
        print(f"  Toplam dava      : {len(all_cases)}")
        print(f"  Değişecek dava   : {len(updates)}")
        print(f"  Değişmeyecek     : {len(all_cases) - len(updates)}")
        print(f"{'='*70}\n")

        # 6. DB'ye yaz (batch commit)
        if not dry_run and updates:
            BATCH = 500
            done = 0
            for i in range(0, len(updates), BATCH):
                batch = updates[i:i+BATCH]
                for case_id, old_no, new_no in batch:
                    db.query(models.Case).filter_by(id=case_id).update({"tracking_no": new_no})
                db.commit()
                done += len(batch)
                print(f"  ... {done}/{len(updates)} kaydedildi", flush=True)
            print(f"\n✓ {len(updates)} dava tracking_no güncellendi.")
        elif not dry_run:
            print("\n✓ Değiştirilecek dava yok.")
        else:
            # dry-run: ilk 30 örneği göster
            print(f"{'ID':>6}  {'ESKİ':<38}  {'YENİ'}")
            print("-"*90)
            for case_id, old_no, new_no in sorted(updates, key=lambda x: x[0])[:30]:
                print(f"{case_id:>6}  {old_no:<38}  {new_no}")
            if len(updates) > 30:
                print(f"  ... ve {len(updates)-30} dava daha")
            print(f"\n(dry-run: hiçbir şey yazılmadı)")

    except Exception as e:
        db.rollback()
        print(f"\n[HATA] {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tracking no'ları geriye dönük düzelt")
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="DB'ye yazmadan sadece önizle")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
