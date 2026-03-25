#!/usr/bin/env bash
# setup.sh — Full deployment script for VP CTRL License Server
# Run as root on Ubuntu 24.04 VPS
# Usage: bash setup.sh

set -euo pipefail

APP_DIR="/var/www/vp-license"
APP_USER="www-data"
DB_NAME="vpctrl_licenses"
DB_USER="vpctrl_user"

echo "=== VP CTRL License Server — Deployment ==="

# ── 1. System packages ──────────────────────────────────────
echo "[1/8] Installing system packages..."
apt-get update -q
apt-get install -y -q python3.12 python3.12-venv python3.12-dev \
    libpq-dev nginx postgresql-client openssl curl

# ── 2. App directory ────────────────────────────────────────
echo "[2/8] Setting up app directory at $APP_DIR..."
mkdir -p "$APP_DIR"
mkdir -p "$APP_DIR/keys"
mkdir -p "$APP_DIR/portal"
mkdir -p "$APP_DIR/routes"

# ── 3. Python virtual environment ───────────────────────────
echo "[3/8] Creating Python virtual environment..."
python3.12 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip -q
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" -q

# ── 4. PostgreSQL database ───────────────────────────────────
echo "[4/8] Setting up PostgreSQL database..."
echo "  Database: $DB_NAME"
echo "  User: $DB_USER"
echo ""
echo "  Run these commands as postgres user:"
echo "    sudo -u postgres psql -c \"CREATE USER $DB_USER WITH PASSWORD 'YOUR_SECURE_PASSWORD';\""
echo "    sudo -u postgres psql -c \"CREATE DATABASE $DB_NAME OWNER $DB_USER;\""
echo "    sudo -u postgres psql -c \"GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;\""
echo ""
read -p "  Press ENTER after creating the database user..."

# ── 5. RSA keys ──────────────────────────────────────────────
echo "[5/8] Generating RSA-2048 key pair for JWT signing..."
if [ ! -f "$APP_DIR/keys/private.pem" ]; then
    openssl genrsa -out "$APP_DIR/keys/private.pem" 2048
    openssl rsa -in "$APP_DIR/keys/private.pem" -pubout -out "$APP_DIR/keys/public.pem"
    chmod 600 "$APP_DIR/keys/private.pem"
    chmod 644 "$APP_DIR/keys/public.pem"
    echo "  Keys generated successfully."
    echo ""
    echo "  ┌─────────────────────────────────────────────────────────┐"
    echo "  │  IMPORTANT: Copy the public key below into              │"
    echo "  │  vp_ctrl_client/license_client.py (RSA_PUBLIC_KEY_PEM) │"
    echo "  └─────────────────────────────────────────────────────────┘"
    echo ""
    cat "$APP_DIR/keys/public.pem"
    echo ""
else
    echo "  Keys already exist — skipping."
fi

# ── 6. .env configuration ────────────────────────────────────
echo "[6/8] Configuring .env..."
if [ ! -f "$APP_DIR/.env" ]; then
    ADMIN_SECRET=$(openssl rand -hex 32)
    cat > "$APP_DIR/.env" <<EOF
DATABASE_URL=postgresql://${DB_USER}:CHANGE_THIS_PASSWORD@localhost:5432/${DB_NAME}
ADMIN_JWT_SECRET=${ADMIN_SECRET}
ADMIN_JWT_EXPIRE_HOURS=12
LICENSE_JWT_EXPIRE_DAYS=7
RSA_PRIVATE_KEY_PATH=/var/www/vp-license/keys/private.pem
RSA_PUBLIC_KEY_PATH=/var/www/vp-license/keys/public.pem
APP_TITLE=VP CTRL License Server
APP_VERSION=1.0.0
RATE_LIMIT_PER_MINUTE=30
EOF
    echo "  .env created. EDIT IT NOW to set DATABASE_URL with the correct password!"
    read -p "  Press ENTER after editing .env..."
else
    echo "  .env already exists — skipping."
fi

# ── 7. Systemd service ───────────────────────────────────────
echo "[7/8] Installing systemd service..."
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
cp "$APP_DIR/deploy/vp-license.service" /etc/systemd/system/vp-license.service
systemctl daemon-reload
systemctl enable vp-license
systemctl restart vp-license
echo "  Service started. Status:"
systemctl is-active vp-license && echo "  ✓ Running" || echo "  ✗ Failed — check: journalctl -u vp-license -n 50"

# ── 8. Bootstrap admin user ──────────────────────────────────
echo "[8/8] Creating admin user..."
echo ""
read -p "  Admin username [admin]: " ADMIN_USER
ADMIN_USER="${ADMIN_USER:-admin}"
read -s -p "  Admin password: " ADMIN_PASS
echo ""

curl -s -X POST "http://localhost:8010/api/admin/bootstrap" \
     -d "username=${ADMIN_USER}&password=${ADMIN_PASS}" \
     | python3 -c "import sys,json; d=json.load(sys.stdin); print(' ', d.get('message', d))"

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "  Portal:    https://license.cliquezoom.com.br"
echo "  API docs:  https://license.cliquezoom.com.br/docs"
echo "  Health:    https://license.cliquezoom.com.br/health"
echo ""
echo "  Next: Configure Nginx with deploy/nginx-license.conf"
echo "        Run: certbot --nginx -d license.cliquezoom.com.br"
