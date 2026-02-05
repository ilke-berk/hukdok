#!/bin/bash
set -e

echo "🚀 Starting HukuDok Backend..."

# 1. Initialize database if needed
echo "📊 Checking database..."
python init_db.py

if [ $? -ne 0 ]; then
    echo "❌ Database initialization failed!"
    exit 1
fi

# 2. Run database migrations
echo "🔄 Running migrations..."
python -c "from database import check_and_migrate_tables; check_and_migrate_tables()"

# 3. Start API server
echo "✅ Starting API server..."
exec uvicorn api:app --host 0.0.0.0 --port 8000
