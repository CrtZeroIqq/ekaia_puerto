#!/bin/bash
# EKAIA Puerto - Production Start Script

set -e

echo "🚀 Starting EKAIA Puerto..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found"
    echo "📝 Please copy .env.example to .env and configure it"
    exit 1
fi

# Load environment
source .env

# Check Python version
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "🐍 Python version: $PYTHON_VERSION"

# Activate virtual environment (if exists)
if [ -d "venv" ]; then
    echo "📦 Activating virtual environment..."
    source venv/bin/activate
fi

# Start MySQL (Docker)
echo "🗄️  Starting MySQL..."
docker-compose up -d mysql

# Wait for MySQL
echo "⏳ Waiting for MySQL to be ready..."
until docker-compose exec -T mysql mysqladmin ping -h localhost --silent; do
    sleep 1
done
echo "✅ MySQL ready"

# Run migrations (optional)
if command -v alembic &> /dev/null; then
    echo "🔄 Running database migrations..."
    alembic upgrade head
fi

# Start Cloudflare Tunnel (if configured)
if [ ! -z "$CF_TUNNEL_TOKEN" ]; then
    echo "🌐 Starting Cloudflare Tunnel..."
    docker-compose up -d cloudflared
fi

# Start FastAPI
echo "🚀 Starting EKAIA API..."
python3 -m uvicorn app.main:app \
    --host ${API_HOST:-0.0.0.0} \
    --port ${API_PORT:-8000} \
    --workers 1 \
    --log-level info

echo "✅ EKAIA Puerto started successfully!"
echo "📊 Dashboard: http://localhost:${API_PORT:-8000}"
echo "📚 API Docs: http://localhost:${API_PORT:-8000}/docs"
