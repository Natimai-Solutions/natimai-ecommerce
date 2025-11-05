#!/bin/bash
# Docker Entrypoint Script for FastAPI E-commerce Backend

set -e

# Default environment variables
WORKERS=${WORKERS:-4}
LOG_LEVEL=${LOG_LEVEL:-INFO}
PORT=${PORT:-8000}
HOST=${HOST:-0.0.0.0}

# Ensure UV environment is always in PATH
export PATH="/app/.venv/bin:$PATH"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Error handling
error() {
    log "ERROR: $1" >&2
    exit 1
}

# Health check function
check_dependencies() {
    log "Checking dependencies..."
    
    # Ensure UV is available
    if ! command -v uv >/dev/null 2>&1; then
        error "UV package manager not found"
    fi
    
    # Check if uv environment exists and is set up correctly
    if [ ! -d "/app/.venv" ]; then
        log "UV virtual environment not found, syncing dependencies..."
        uv sync --frozen
    fi
    
    # Verify UV environment is working
    if ! command -v uvicorn >/dev/null 2>&1; then
        log "uvicorn not found in PATH, checking UV environment..."
        if [ -f "/app/.venv/bin/uvicorn" ]; then
            log "Found uvicorn in UV environment"
        else
            error "uvicorn not found in UV environment. Dependencies may not be installed correctly."
        fi
    fi
    
    # Basic import test
    uv run python -c "
import sys
sys.path.insert(0, '/app')
try:
    import pydantic
    from pydantic import EmailStr
    print('✓ Pydantic and email validation: OK')
except ImportError as e:
    print(f'✗ Import failed: {e}')
    sys.exit(1)
" || error "Critical dependencies missing"
    
    log "Dependencies check completed"
}

# Database connectivity check
check_database_connection() {
    log "Testing database connection..."
    
    uv run python -c "
import asyncio
import sys
sys.path.insert(0, '/app')
try:
    from app.core.db import test_connection
    asyncio.run(test_connection())
    print('✓ Database connection: OK')
except Exception as e:
    print(f'✗ Database connection: FAILED - {e}')
    print('Warning: Database not ready, service will retry connections')
" || log "Warning: Database connection test failed - service will retry"
}

# Pre-startup tasks
pre_startup() {
    log "Running pre-startup tasks..."
    
    if [ -f "/app/.env" ]; then
        log "Loading environment variables from .env file"
        set -a
        source /app/.env
        set +a
    fi
    
    check_dependencies
    check_database_connection
}

case "$1" in
    "api")
        log "Starting FastAPI API server..."
        
        # Check if reload is requested (development mode)
        RELOAD_ARG=""
        if [ "$2" = "--reload" ] || [ "$RELOAD" = "true" ]; then
            log "Development mode: enabling auto-reload"
            RELOAD_ARG="--reload"
            WORKERS=1  # Force single worker for reload mode
        fi
        
        log "Configuration: workers=$WORKERS, host=$HOST, port=$PORT, log_level=$LOG_LEVEL, reload=${RELOAD_ARG:-disabled}"
        
        pre_startup
        
        log "Loading outbox event handlers..."
        uv run python -c "
import sys
sys.path.insert(0, '/app')
from app.outbox.loader import load_handlers
load_handlers()
print('Event handlers loaded successfully')
"
        
        if [ -n "$RELOAD_ARG" ]; then
            log "Starting API server in development mode with auto-reload"
            exec uv run uvicorn app.main:app \
                --host $HOST \
                --port $PORT \
                --reload \
                --log-level $(echo $LOG_LEVEL | tr '[:upper:]' '[:lower:]') \
                --access-log \
                --loop uvloop \
                --http httptools
        else
            log "Starting API server with $WORKERS workers"
            exec uv run uvicorn app.main:app \
                --host $HOST \
                --port $PORT \
                --workers $WORKERS \
                --log-level $(echo $LOG_LEVEL | tr '[:upper:]' '[:lower:]') \
                --access-log \
                --loop uvloop \
                --http httptools
        fi
        ;;
        
    "worker")
        log "Starting ARQ background worker..."
        
        pre_startup
        
        log "Loading outbox event handlers..."
        uv run python -c "
import sys
sys.path.insert(0, '/app')
from app.outbox.loader import load_handlers
load_handlers()
print('Event handlers loaded successfully')
"
        
        log "Starting ARQ worker for background job processing"
        
        # Add verbose flag if log level is DEBUG
        ARQ_ARGS=""
        if [ "$(echo $LOG_LEVEL | tr '[:upper:]' '[:lower:]')" = "debug" ]; then
            ARQ_ARGS="--verbose"
        fi
        
        exec uv run arq app.core.arq_worker.WorkerSettings $ARQ_ARGS
        ;;
        
    "poller")
        log "Starting Outbox event poller..."
        
        pre_startup
        
        shift
        POLLER_ARGS="$@"
        
        log "Starting outbox poller with arguments: $POLLER_ARGS"
        exec uv run python app/scripts/outbox_poller.py \
            --log-level $LOG_LEVEL \
            $POLLER_ARGS
        ;;
        
    "migrate")
        log "Running database migrations..."
        
        if [ ! -f "alembic.ini" ]; then
            error "alembic.ini not found. Are you in the correct directory?"
        fi
        
        log "Upgrading database to latest migration"
        uv run alembic upgrade head

        log "Importing initial data into database..."
        exec uv run python app/initial_data.py
        ;;
        
    "shell")
        log "Starting interactive Python shell..."
        
        pre_startup
        
        log "Loading application context..."
        exec uv run python -c "
import sys
sys.path.insert(0, '/app')
from app.outbox.loader import load_handlers
load_handlers()
print('Application context loaded')
import code
code.interact()
"
        ;;
        
    "test")
        log "Running test suite..."
        
        export ENVIRONMENT=test
        
        log "Running pytest with coverage"
        exec uv run pytest app/tests/ \
            --cov=app \
            --cov-report=term-missing \
            --cov-report=html \
            --verbose \
            "$@"
        ;;
        
    *)
        error "Unknown command: $1

Usage: $0 COMMAND [OPTIONS]

Available commands:
  api         Start FastAPI application server
  worker      Start ARQ worker for background jobs
  poller      Start outbox event poller
  migrate     Run database migrations
  shell       Start interactive Python shell
  test        Run test suite
"
        ;;
esac