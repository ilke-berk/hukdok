#!/bin/bash
set -e

echo "🚀 Starting HukuDok Backend..."

# Migrasyonlar uvicorn'dan ÖNCE tek süreçte koşar (set -e: hata konteyneri
# durdurur, uygulama bozuk şemayla ayağa kalkmaz). --workers N'e geçişin
# önkoşulu: DDL asla worker süreci içinde koşmamalı (Faz 1-A).
echo "📊 Running database migrations (one-time step)..."
python migrate.py

echo "✅ Starting API server..."
exec uvicorn api:app --host 0.0.0.0 --port ${PORT:-8001}

