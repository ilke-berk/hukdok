#!/bin/bash
set -e

echo "🚀 Starting HukuDok Backend..."

echo "📊 Initializing database and running migrations..."
python -c "
from database import Base, engine, check_and_migrate_tables
# Create all tables
Base.metadata.create_all(bind=engine)
# Run migrations for any new fields
check_and_migrate_tables()
print('✅ Database ready!')
"

if [ $? -ne 0 ]; then
    echo "❌ Database initialization failed!"
    exit 1
fi

echo "✅ Starting API server..."
exec uvicorn api:app --host 0.0.0.0 --port 8000

