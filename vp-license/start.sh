#!/usr/bin/env bash
# start.sh — Start the VP CTRL License Server
# Usage: ./start.sh [--reload]
# Recommended: run via systemd (see deployment notes)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
  source venv/bin/activate
fi

# Check RSA keys exist
if [ ! -f "keys/private.pem" ] || [ ! -f "keys/public.pem" ]; then
  echo "[ERROR] RSA keys not found in keys/. Generate them first:"
  echo "  mkdir -p keys"
  echo "  openssl genrsa -out keys/private.pem 2048"
  echo "  openssl rsa -in keys/private.pem -pubout -out keys/public.pem"
  echo "  chmod 600 keys/private.pem"
  exit 1
fi

# Check .env exists
if [ ! -f ".env" ]; then
  echo "[ERROR] .env file not found. Copy and edit the template:"
  echo "  cp .env.example .env"
  exit 1
fi

RELOAD=""
if [ "$1" = "--reload" ]; then
  RELOAD="--reload"
  echo "[INFO] Starting in development mode with auto-reload..."
else
  echo "[INFO] Starting VP CTRL License Server on port 8010..."
fi

exec uvicorn main:app \
  --host 0.0.0.0 \
  --port 8010 \
  --workers 2 \
  --log-level info \
  $RELOAD
