#!/bin/bash
# app/scripts/entrypoint.sh

set -e

case "$1" in
    "api")
        echo "🚀 Starting FastAPI API..."
        exec fastapi run --workers 4 app/main.py
        ;;
    "worker")
        echo "🚀 Starting ARQ Worker..."
        exec arq app.core.arq_worker.WorkerSettings
        ;;
    "poller")
        echo "🚀 Starting Outbox Poller..."
        exec python app/scripts/outbox_poller.py
        ;;
    "migrate")
        echo "🚀 Running database migrations..."
        exec alembic upgrade head
        ;;
    *)
        echo "Usage: $0 {api|worker|poller|migrate}"
        echo "Available commands:"
        echo "  api     - Start FastAPI application"
        echo "  worker  - Start ARQ worker"
        echo "  poller  - Start Outbox poller"
        echo "  migrate - Run database migrations"
        exit 1
        ;;
esac