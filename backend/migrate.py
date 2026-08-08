"""Tek seferlik DB migrasyon adımı (Faz 1-A).

docker-entrypoint.sh bunu uvicorn'dan ÖNCE çalıştırır: şema migrasyonları
worker sayısından bağımsız tek süreçte koşar (--workers N'e geçişin önkoşulu —
her worker kendi migrasyonunu koşarsa DDL yarışı olur). deploy.sh de sağlık
kapısından önce aynı adımı bağımsız çalıştırabilir (Faz 1-C).

Çıkış kodu: 0 = başarılı, 1 = migrasyon hatası. Entrypoint `set -e` ile durur,
konteyner ayağa kalkmaz — sessiz şema sapması yerine fail-fast.
"""
import logging
import sys

from logging_setup import configure_logging

configure_logging()


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
