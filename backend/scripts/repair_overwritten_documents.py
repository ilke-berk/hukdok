"""Ezilen arşiv dosyalarını SharePoint sürüm geçmişinden kurtarır (2026-09-01 arızası onarımı).

Arka plan: hedef ad standardı teklik taşımıyordu ve Graph yüklemeleri
conflictBehavior=replace ile gidiyordu — aynı ada düşen ikinci belge birincinin
dosyasını değiştirdi. conflictBehavior=replace SharePoint'te YENİ SÜRÜM açtığı
için ezilen içerik dosyanın sürüm geçmişinde durur ve kurtarılabilir
(2026-09-01 doğrulaması: 102 mükerrer ad grubu / 240 kayıt).

Ne yapar:
  1) case_documents'ta aynı stored_filename'i paylaşan grupları bulur,
  2) 02_YEDEK_ARSIV'deki dosyanın TÜM sürümlerini indirir ve hash'ler
     (ardışık özdeş sürümler retry artığıdır, teke indirilir),
  3) satırları sürümlere eşler (id sırası ↔ sürüm sırası, SONDAN hizalı);
     canlı içerikten FARKLI eski içerikler `<ad>_2.pdf`, `_3`... adıyla YENİ
     dosya olarak yüklenir,
  4) --apply ile ilgili DB satırı yeni ada/URL'e çevrilir; --notify-hukukbot
     verilmişse export edilmiş belgeler hukukbot'a yeniden bildirilir,
  5) HAM arşivde (upload_outbox kind='ham' tarihçesinden) aynı ada birden çok
     belgenin düştüğü çakışmaları da kurtarır — ham adları DB'de tutulmadığı
     için burada yalnız dosya yüklenir, DB güncellemesi yoktur.

Varsayılan DRY-RUN'dur: SharePoint'e yükleme ve DB yazımı YAPMAZ; sürümleri
indirip (salt-okunur) tam planı raporlar. Yarım kalan --apply koşusu güvenle
tekrarlanır: onarılan satırlar gruptan düştüğü için atlanır; yüklenmiş ama DB'ye
yazılamamış kurtarma dosyası hash eşleşmesiyle yeniden KULLANILIR (mükerrer
kopya üretilmez).

Kullanım (konteynerde):
  docker exec hukdok_backend python scripts/repair_overwritten_documents.py             # dry-run
  docker exec hukdok_backend python scripts/repair_overwritten_documents.py --apply
  docker exec hukdok_backend python scripts/repair_overwritten_documents.py --apply --notify-hukukbot
  Seçenekler: --limit N (ilk N grup), --skip-ham, --json /tmp/onarim.json
İmaj script'i henüz içermiyorsa önce:
  docker cp backend/scripts/repair_overwritten_documents.py hukdok_backend:/app/scripts/
"""
import argparse
import hashlib
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/ modulleri icin

import requests  # noqa: E402
from sqlalchemy import text  # noqa: E402

import models  # noqa: E402
from database import SessionLocal  # noqa: E402
from services.archive_names import islenmis_stem_taken  # noqa: E402
from sharepoint import sharepoint_uploader_graph as up  # noqa: E402
from sharepoint.auth_graph import get_graph_token  # noqa: E402

ISLENMIS_FOLDER = os.getenv("SHAREPOINT_FOLDER_ISLENMIS_NAME", "02_YEDEK_ARSIV")
HAM_FOLDER = os.getenv("SHAREPOINT_FOLDER_HAM_NAME", "01_HAM_ARSIV")

_MAX_RECOVERY_SUFFIX = 199


# ─── Graph yardımcıları (salt-okunur uçlar) ──────────────────────────────────

def _graph_get(url: str, **kw) -> requests.Response:
    """401'de bir kez taze token ile yeniden dener (uploader ile aynı desen)."""
    session = up._get_shared_session()
    token = get_graph_token(config_type="default")
    r = session.get(url.format(drive=_drive_id(token)), headers=up._headers(token), **kw)
    if r.status_code == 401:
        token = get_graph_token(config_type="default", force_refresh=True)
        r = session.get(url.format(drive=_drive_id(token)), headers=up._headers(token), **kw)
    return r


def _drive_id(token: str) -> str:
    _site, drive = up._get_site_and_drive_id(token, config_type="default")
    return drive


def list_versions(item_id: str):
    """Öğenin sürümlerini KRONOLOJİK (eski→yeni) döndürür.

    DİKKAT: sürüm uçları path adreslemesiyle (root:/yol:/versions/...) content
    indirmede 400 veriyor (2026-09-01 prod doğrulaması) — bu yüzden önce
    item_info ile ID çözülür, sürümler ID üzerinden okunur."""
    r = _graph_get(
        up.GRAPH + "/drives/{drive}/items/" + item_id + "/versions", timeout=(10, 60)
    )
    r.raise_for_status()
    vers = r.json().get("value", [])
    return sorted(vers, key=lambda v: v.get("lastModifiedDateTime") or "")


def download_version(item_id: str, version_id: str, is_current: bool = False) -> bytes:
    """Sürüm içeriği. GÜNCEL sürümün içeriği /versions/{id}/content ile
    alınamıyor (Graph 400 — 2026-09-01 prod doğrulaması); normal /content
    ucundan iner. Eski sürümler versions ucundan iner."""
    if is_current:
        url = up.GRAPH + "/drives/{drive}/items/" + item_id + "/content"
    else:
        url = up.GRAPH + "/drives/{drive}/items/" + item_id + f"/versions/{version_id}/content"
    r = _graph_get(url, timeout=(10, 120), allow_redirects=True)
    r.raise_for_status()
    return r.content


def item_info(folder: str, name: str):
    """Dosya varsa {id, webUrl, size}, yoksa None."""
    path = quote(f"{folder}/{name}")
    r = _graph_get(up.GRAPH + "/drives/{drive}/root:/" + path, timeout=(10, 60))
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def download_current(folder: str, name: str) -> bytes:
    content, _ctype = up.download_file_from_sharepoint(folder, name)
    return content


# ─── içerik/eşleme yardımcıları ──────────────────────────────────────────────

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dedup_consecutive(versions_with_hash):
    """Ardışık özdeş hash'leri teke indirir (upload retry artıkları)."""
    distinct = []
    for v in versions_with_hash:
        if distinct and distinct[-1]["hash"] == v["hash"]:
            distinct[-1]["version_ids"].append(v["version_id"])
            continue
        distinct.append(
            {
                "hash": v["hash"],
                "ts": v["ts"],
                "size": v["size"],
                "version_ids": [v["version_id"]],
                "content": v["content"],
            }
        )
    return distinct


def _recovery_name(db, base_name: str, target_hash: str, folder: str):
    """Kurtarma dosyası için benzersiz ad seçer.

    Dönüş: (ad, mevcut_webUrl | None) — mevcut_webUrl doluysa aynı içerik daha
    önceki (yarım kalmış) koşuda zaten yüklenmiştir; yeniden yüklenmez.
    Ad uzayı: DB stem'leri (islenmis_stem_taken) + SharePoint'te fiilen duran
    dosyalar (DB kaydı olmayan yetim yüklemeler dahil)."""
    stem, ext = Path(base_name).stem, Path(base_name).suffix
    for n in range(2, _MAX_RECOVERY_SUFFIX + 1):
        cand_stem = f"{stem}_{n}"
        cand = f"{cand_stem}{ext}"
        info = item_info(folder, cand)
        if info is not None:
            # Yarım kalan önceki koşunun dosyası mı? Hash tutuyorsa yeniden kullan.
            try:
                if _sha256(download_current(folder, cand)) == target_hash:
                    return cand, info.get("webUrl")
            except Exception:
                pass
            continue
        if islenmis_stem_taken(db, cand_stem):
            continue
        return cand, None
    return f"{stem}_{uuid.uuid4().hex[:8]}{ext}", None


def _upload_bytes(content: bytes, target_name: str, folder: str) -> dict:
    suffix = Path(target_name).suffix or ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        return up.upload_file_to_sharepoint(
            filepath=tmp_path,
            target_filename=target_name,
            target_folder_name=folder,
            content_type="application/pdf" if suffix == ".pdf" else "application/octet-stream",
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ─── işlenmiş arşiv (02_YEDEK_ARSIV) onarımı ─────────────────────────────────

def _load_islenmis_groups(db, limit=None):
    sql = text(
        "SELECT stored_filename FROM case_documents "
        "GROUP BY stored_filename HAVING COUNT(*) > 1 "
        "ORDER BY MAX(uploaded_at) DESC"
    )
    names = [row[0] for row in db.execute(sql)]
    return names[:limit] if limit else names


def _repair_islenmis_group(db, name: str, apply: bool, notify: bool):
    rows = (
        db.query(models.CaseDocument)
        .filter(models.CaseDocument.stored_filename == name)
        .order_by(models.CaseDocument.id)
        .all()
    )
    rapor = {
        "grup": name,
        "satirlar": [
            {
                "doc_id": r.id,
                "case_id": r.case_id,
                "orijinal": r.original_filename,
                "yuklenme": str(r.uploaded_at),
            }
            for r in rows
        ],
        "eylemler": [],
    }
    if len(rows) < 2:
        rapor["durum"] = "grup_dagilmis (muhtemelen onceki kosuda onarildi)"
        return rapor

    info = item_info(ISLENMIS_FOLDER, name)
    if info is None:
        rapor["durum"] = "dosya_sharepointte_yok — elle incele"
        return rapor
    vers = list_versions(info["id"])
    if not vers:
        rapor["durum"] = "surum_listesi_bos — elle incele"
        return rapor

    versions_with_hash = []
    for v in vers:
        content = download_version(info["id"], v["id"], is_current=(v is vers[-1]))
        versions_with_hash.append(
            {
                "version_id": v["id"],
                "ts": v.get("lastModifiedDateTime"),
                "size": v.get("size"),
                "hash": _sha256(content),
                "content": content,
            }
        )
    distinct = _dedup_consecutive(versions_with_hash)
    rapor["surumler"] = [
        {"version_ids": d["version_ids"], "ts": d["ts"], "size": d["size"], "hash": d["hash"][:12]}
        for d in distinct
    ]

    if len(distinct) == 1:
        rapor["durum"] = "icerik_ozdes — ayni belge birden cok kez kaydedilmis, dosya kaybi yok"
        return rapor

    # Eşleme: satırlar (id ASC) ↔ farklı içerikler (kronolojik ASC), SONDAN hizalı.
    n, k = len(rows), len(distinct)
    m = min(n, k)
    paired = list(zip(rows[-m:], distinct[-m:], strict=True))
    for r in rows[: n - m]:
        rapor["eylemler"].append(
            {"doc_id": r.id, "eylem": "ESLESMEDI — elle incele (satir sayisi surum sayisini asiyor)"}
        )
    for d in distinct[: k - m]:
        rapor["eylemler"].append(
            {
                "eylem": "SAHIPSIZ_SURUM — elle incele (hicbir satirla eslesmedi)",
                "surum": {"ts": d["ts"], "size": d["size"], "hash": d["hash"][:12]},
            }
        )

    live_hash = distinct[-1]["hash"]
    for row, d in paired:
        if d is distinct[-1]:
            rapor["eylemler"].append(
                {"doc_id": row.id, "eylem": "ad_sahibi — canli dosya bu satirin icerigi, degisiklik yok"}
            )
            continue
        if d["hash"] == live_hash:
            rapor["eylemler"].append(
                {"doc_id": row.id, "eylem": "icerik_canliyla_ozdes — dosya cogaltilmadi, satir paylasimda kaldi"}
            )
            continue

        rec_name, existing_url = _recovery_name(db, name, d["hash"], ISLENMIS_FOLDER)
        eylem = {
            "doc_id": row.id,
            "eylem": "kurtar",
            "yeni_ad": rec_name,
            "kaynak_surum": {"ts": d["ts"], "size": d["size"], "hash": d["hash"][:12]},
            "yeniden_kullanildi": bool(existing_url),
        }
        if apply:
            web_url = existing_url
            if web_url is None:
                resp = _upload_bytes(d["content"], rec_name, ISLENMIS_FOLDER)
                web_url = (resp or {}).get("webUrl")
            row.stored_filename = rec_name
            if web_url:
                row.sharepoint_url = web_url
                row.upload_status = "uploaded"
            db.commit()
            eylem["uygulandi"] = True
            eylem["web_url"] = web_url
            if notify:
                exported = (
                    db.query(models.ExportOutbox)
                    .filter(models.ExportOutbox.document_id == row.id)
                    .first()
                )
                if exported is not None:
                    from services.export_publisher import notify_hukukbot

                    notify_hukukbot(row.id)
                    eylem["hukukbot_bildirildi"] = True
        rapor["eylemler"].append(eylem)

    rapor["durum"] = "onarim_plani" if not apply else "onarildi"
    return rapor


# ─── HAM arşiv (01_HAM_ARSIV) onarımı ────────────────────────────────────────

def _load_ham_groups(db, limit=None):
    """Aynı ham hedef adına birden çok BELGENİN düştüğü adlar (outbox tarihçesi).

    Aynı belgenin retry'ları yeni satır açmaz; birden çok satır = birden çok
    enqueue = potansiyel farklı içerik."""
    sql = text(
        "SELECT target_filename FROM upload_outbox WHERE kind = 'ham' "
        "GROUP BY target_filename HAVING COUNT(DISTINCT COALESCE(document_id, -id)) > 1 "
        "ORDER BY MAX(created_at) DESC"
    )
    names = [row[0] for row in db.execute(sql)]
    return names[:limit] if limit else names


def _ham_taken_on_sp(name: str) -> bool:
    return item_info(HAM_FOLDER, name) is not None


def _repair_ham_group(db, name: str, apply: bool):
    doc_ids = [
        row[0]
        for row in db.execute(
            text("SELECT DISTINCT document_id FROM upload_outbox WHERE kind='ham' AND target_filename=:n"),
            {"n": name},
        )
    ]
    rapor = {"grup": name, "belge_idleri": doc_ids, "eylemler": []}

    info = item_info(HAM_FOLDER, name)
    if info is None:
        rapor["durum"] = "dosya_sharepointte_yok — elle incele"
        return rapor
    vers = list_versions(info["id"])
    versions_with_hash = []
    for v in vers:
        content = download_version(info["id"], v["id"], is_current=(v is vers[-1]))
        versions_with_hash.append(
            {
                "version_id": v["id"],
                "ts": v.get("lastModifiedDateTime"),
                "size": v.get("size"),
                "hash": _sha256(content),
                "content": content,
            }
        )
    distinct = _dedup_consecutive(versions_with_hash)
    if len(distinct) == 1:
        rapor["durum"] = "icerik_ozdes — kayip yok"
        return rapor

    stem, ext = Path(name).stem, Path(name).suffix
    live_hash = distinct[-1]["hash"]
    for d in distinct[:-1]:
        if d["hash"] == live_hash:
            continue
        # Ham adları DB'de tutulmaz: ad uzayı = SharePoint'in kendisi.
        rec_name = None
        for n_ in range(2, _MAX_RECOVERY_SUFFIX + 1):
            cand = f"{stem}_{n_}{ext}"
            if not _ham_taken_on_sp(cand):
                rec_name = cand
                break
            try:
                if _sha256(download_current(HAM_FOLDER, cand)) == d["hash"]:
                    rec_name = cand  # önceki yarım koşu — yeniden kullan
                    break
            except Exception:
                continue
        if rec_name is None:
            rec_name = f"{stem}_{uuid.uuid4().hex[:8]}{ext}"
        eylem = {
            "eylem": "kurtar",
            "yeni_ad": rec_name,
            "kaynak_surum": {"ts": d["ts"], "size": d["size"], "hash": d["hash"][:12]},
        }
        if apply and not _ham_taken_on_sp(rec_name):
            _upload_bytes(d["content"], rec_name, HAM_FOLDER)
            eylem["uygulandi"] = True
        rapor["eylemler"].append(eylem)

    rapor["durum"] = (
        "onarim_plani" if not apply else ("onarildi" if rapor["eylemler"] else "icerik_ozdes")
    )
    return rapor


# ─── ana akış ────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Ezilen arşiv dosyalarını sürüm geçmişinden kurtarır.")
    ap.add_argument("--apply", action="store_true", help="Planı uygula (varsayılan: dry-run)")
    ap.add_argument("--skip-ham", action="store_true", help="HAM arşiv geçişini atla")
    ap.add_argument("--limit", type=int, default=None, help="En çok N grup işle")
    ap.add_argument("--json", dest="json_path", default=None, help="Raporu JSON olarak bu dosyaya yaz")
    ap.add_argument(
        "--notify-hukukbot",
        action="store_true",
        help="--apply ile: export edilmiş onarılan belgeleri hukukbot'a yeniden bildir",
    )
    args = ap.parse_args()

    mod = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mod}] İşlenmiş arşiv onarımı başlıyor (klasör: {ISLENMIS_FOLDER})")

    rapor = {"mod": mod, "islenmis": [], "ham": []}
    db = SessionLocal()
    try:
        groups = _load_islenmis_groups(db, args.limit)
        print(f"  {len(groups)} mükerrer ad grubu bulundu")
        for i, name in enumerate(groups, 1):
            try:
                g = _repair_islenmis_group(db, name, args.apply, args.notify_hukukbot)
            except Exception as e:
                db.rollback()
                g = {"grup": name, "durum": f"HATA: {e}"}
            rapor["islenmis"].append(g)
            kurtarma = sum(1 for a in g.get("eylemler", []) if a.get("eylem") == "kurtar")
            print(f"  [{i}/{len(groups)}] {name} → {g.get('durum')} (kurtarma: {kurtarma})")

        if not args.skip_ham:
            print(f"[{mod}] HAM arşiv onarımı başlıyor (klasör: {HAM_FOLDER})")
            ham_groups = _load_ham_groups(db, args.limit)
            print(f"  {len(ham_groups)} mükerrer ham ad grubu bulundu")
            for i, name in enumerate(ham_groups, 1):
                try:
                    g = _repair_ham_group(db, name, args.apply)
                except Exception as e:
                    db.rollback()
                    g = {"grup": name, "durum": f"HATA: {e}"}
                rapor["ham"].append(g)
                kurtarma = len(g.get("eylemler", []))
                print(f"  [{i}/{len(ham_groups)}] {name} → {g.get('durum')} (kurtarma: {kurtarma})")
    finally:
        db.close()

    toplam_kurtarma = sum(
        1 for g in rapor["islenmis"] for a in g.get("eylemler", []) if a.get("eylem") == "kurtar"
    ) + sum(len(g.get("eylemler", [])) for g in rapor["ham"])
    elle = [
        g["grup"]
        for g in rapor["islenmis"] + rapor["ham"]
        if "elle" in str(g.get("durum", ""))
        or any("ESLESMEDI" in str(a.get("eylem", "")) or "SAHIPSIZ" in str(a.get("eylem", "")) for a in g.get("eylemler", []))
    ]
    print(f"\nÖZET [{mod}]: işlenmiş grup {len(rapor['islenmis'])}, ham grup {len(rapor['ham'])}, "
          f"kurtarma eylemi {toplam_kurtarma}, elle incelenecek {len(elle)}")
    for isim in elle:
        print(f"  ELLE İNCELE: {isim}")

    if args.json_path:
        # content alanları rapora girmez (bytes) — zaten eylem sözlüklerinde yok.
        with open(args.json_path, "w", encoding="utf-8") as f:
            json.dump(rapor, f, ensure_ascii=False, indent=2, default=str)
        print(f"JSON rapor: {args.json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
