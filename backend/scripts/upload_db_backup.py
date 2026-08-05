"""DB yedeğini SharePoint 02_YEDEK_ARSIV klasörüne yükler (prod yedekleme rutini).

Konteyner içinden koşar — Graph env'leri hazırdır, yeni bağımlılık yok.
Teknik loglarla aynı klasör desenini kullanır (02_YEDEK_ARSIV kökü).
4 MB üzeri dosyalar uploader'daki chunk'lı upload session ile gider.

Kullanım (scripts/prod/backup_db.sh bu adımları otomatik koşar):
  docker cp yedek.dump hukdok_backend:/tmp/db_backup_2026-08-05.dump
  docker exec hukdok_backend python scripts/upload_db_backup.py /tmp/db_backup_2026-08-05.dump
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/ modulleri icin

from sharepoint.sharepoint_uploader_graph import upload_file_to_sharepoint  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print("Kullanım: python scripts/upload_db_backup.py <dump-dosyası>", file=sys.stderr)
        return 2
    path = sys.argv[1]
    if not os.path.isfile(path):
        print(f"Dosya bulunamadı: {path}", file=sys.stderr)
        return 2

    folder = os.getenv("SHAREPOINT_FOLDER_ISLENMIS_NAME", "02_YEDEK_ARSIV")
    name = os.path.basename(path)
    size = os.path.getsize(path)

    result = upload_file_to_sharepoint(
        filepath=path,
        target_filename=name,
        target_folder_name=folder,
        content_type="application/octet-stream",
    )
    print(f"Yüklendi: {folder}/{name} ({size} bayt, id={result.get('id')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
