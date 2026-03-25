RSA Key Generation Instructions
================================

Run these commands on the VPS in /var/www/vp-license/ after deployment:

  mkdir -p keys
  openssl genrsa -out keys/private.pem 2048
  openssl rsa -in keys/private.pem -pubout -out keys/public.pem
  chmod 600 keys/private.pem
  chmod 644 keys/public.pem

The PUBLIC KEY (keys/public.pem) must be embedded in the VP CTRL desktop app
for offline JWT validation. See versions/v3/core/license_client.py.

NEVER commit private.pem to version control.
