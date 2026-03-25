"""
main.py — VP CTRL License Server entry point.
FastAPI application with public license endpoints and admin portal backend.
Port: 8010
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vp_license")

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

RATE_LIMIT = os.getenv("RATE_LIMIT_PER_MINUTE", "30")
limiter = Limiter(key_func=get_remote_address, default_limits=[f"{RATE_LIMIT}/minute"])

# ---------------------------------------------------------------------------
# Lifespan — create DB tables on startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Import here to ensure load_dotenv() has run first
    from database import Base, engine
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified/created.")

    # Warn if RSA keys are missing
    private_key = Path(os.getenv("RSA_PRIVATE_KEY_PATH", "/var/www/vp-license/keys/private.pem"))
    public_key = Path(os.getenv("RSA_PUBLIC_KEY_PATH", "/var/www/vp-license/keys/public.pem"))
    if not private_key.exists():
        logger.warning("RSA private key not found at %s — license token signing will fail!", private_key)
    if not public_key.exists():
        logger.warning("RSA public key not found at %s", public_key)

    logger.info("VP CTRL License Server started on port 8010.")
    yield
    logger.info("VP CTRL License Server shutting down.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title=os.getenv("APP_TITLE", "VP CTRL License Server"),
    version=os.getenv("APP_VERSION", "1.0.0"),
    description="License management backend for VP CTRL desktop application.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — allow the portal origin and the VP CTRL app (desktop apps use no-cors)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://license.cliquezoom.com.br",
        "http://localhost:8010",
        "http://127.0.0.1:8010",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

from routes.public import router as public_router
from routes.admin import router as admin_router

app.include_router(public_router)
app.include_router(admin_router)

# ---------------------------------------------------------------------------
# Apply rate limits to public endpoints explicitly
# ---------------------------------------------------------------------------

from routes.public import validate_license, activate_license, heartbeat, deactivate_license

# Override with decorated versions for rate limiting
# (slowapi decorators work on the function objects)
validate_license.__wrapped__ = limiter.limit(f"{RATE_LIMIT}/minute")(validate_license)
activate_license.__wrapped__ = limiter.limit("10/minute")(activate_license)

# ---------------------------------------------------------------------------
# Portal — serve the SPA
# ---------------------------------------------------------------------------

PORTAL_DIR = Path(__file__).parent / "portal"

@app.get("/", include_in_schema=False)
@app.get("/portal", include_in_schema=False)
async def serve_portal():
    index = PORTAL_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({"message": "Portal not found. Deploy portal/index.html."}, status_code=404)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "service": "vp-ctrl-license"}


# ---------------------------------------------------------------------------
# Public key endpoint — VP CTRL client can fetch public key for offline validation
# ---------------------------------------------------------------------------

@app.get("/api/v1/public-key", tags=["public"])
async def get_public_key():
    """Returns the RSA public key PEM for offline JWT validation."""
    from auth import get_public_key_pem
    try:
        pem = get_public_key_pem()
        return {"public_key": pem}
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=503)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8010,
        reload=False,
        log_level="info",
    )
