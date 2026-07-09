#!/bin/bash

# Simple start script for development/testing
# For production, use run.sh which has add-on integration

set -e

echo "Starting HAOS Orchestrator in development mode..."

# Create data directories if they don't exist
mkdir -p data/orchestrator
mkdir -p data/orchestrator/logs
mkdir -p data/orchestrator/config
mkdir -p data/orchestrator/tokens

# Copy example config if not exists
if [ ! -f .env ]; then
    cp .env.example .env || cp /app/.env.example .env || true
fi

# Start the application
exec python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --log-level info
