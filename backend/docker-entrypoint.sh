#!/bin/bash
set -e

echo "🚀 Starting HukuDok Backend..."

echo "📊 Initializing database and running migrations..."
python -c "
from database import init_db
# Robust initialization including models import, table creation, migrations and seeding
init_db()
print('✅ Database ready!')
"

if [ $? -ne 0 ]; then
    echo "❌ Database initialization failed!"
    exit 1
fi

echo "✅ Starting API server..."
exec uvicorn api:app --host 0.0.0.0 --port ${PORT:-8001}

