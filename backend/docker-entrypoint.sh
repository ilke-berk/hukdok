#!/bin/bash
set -e

echo "🚀 Starting HukuDok Backend..."

# Migrasyonlar uvicorn'dan ÖNCE tek süreçte koşar (set -e: hata konteyneri
# durdurur, uygulama bozuk şemayla ayağa kalkmaz). --workers N'e geçişin
# önkoşulu: DDL asla worker süreci içinde koşmamalı (Faz 1-A).
echo "📊 Running database migrations (one-time step)..."
python migrate.py

echo "✅ Starting API server..."
# Faz 3-E: 2 worker — /process-/confirm çaprazı DiskTTLCache (disk destekli
# PROCESS_CACHE) ile, süreç-tekil arkaplan işleri lider kilidiyle
# (services/singleton_lock.py) güvenli. UVICORN_WORKERS=1 ile imaj
# değiştirmeden tek worker'a dönülebilir (compose env + recreate yeter).
exec uvicorn api:app --host 0.0.0.0 --port ${PORT:-8001} --workers ${UVICORN_WORKERS:-2}

