"""Tek seferlik DB migrasyon adımı (Faz 1-A).

docker-entrypoint.sh bunu uvicorn'dan ÖNCE çalıştırır: şema migrasyonları
worker sayısından bağımsız tek süreçte koşar (--workers N'e geçişin önkoşulu —
her worker kendi migrasyonunu koşarsa DDL yarışı olur). deploy.sh de sağlık
kapısından önce aynı adımı bağımsız çalıştırabilir (Faz 1-C).

Çıkış kodu: 0 = başarılı, 1 = migrasyon hatası. Entrypoint `set -e` ile durur,
konteyner ayağa kalkmaz — sessiz şema sapması yerine fail-fast.
"""
import logging
import os
import sys

from logging_setup import configure_logging

configure_logging()

# Faz 3-E (plan 3.6): app engine'i statement_timeout=30 sn ile kurulur; şema
# migrasyonları bu sınırın DIŞINDA kalmalı (create_all + backfill UPDATE'ler —
# örn. madde 24'ün case_documents taraması — 30 sn'yi meşru aşabilir).
# database.py bu env'i import ANINDA okur; migrate.py ayrı süreç olduğundan
# buradaki atama uygulamanın kendi engine ayarını etkilemez. (logging_setup
# database'i import etmez — sıra güvenli.)
os.environ["DB_STATEMENT_TIMEOUT_MS"] = "0"


def main() -> int:
    try:
        from database import init_db
        init_db()
        logging.info("✅ Database ready!")
        return 0
    except Exception:
        logging.critical("❌ Database migration failed!", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
