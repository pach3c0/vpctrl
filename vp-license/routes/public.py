"""
routes/public.py — Public license endpoints called by the VP CTRL desktop app.

Endpoints:
  POST /api/v1/licenses/validate   — validate key + fingerprint, get JWT token
  POST /api/v1/licenses/activate   — first-time activation on a machine
  POST /api/v1/licenses/heartbeat  — periodic ping (every ~1 hour from client)
  POST /api/v1/licenses/deactivate — clean deactivation on app close
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import create_license_token
from database import get_db
from models import Activation, License

router = APIRouter(prefix="/api/v1/licenses", tags=["public"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ValidateRequest(BaseModel):
    license_key: str = Field(..., min_length=19, max_length=19, pattern=r"^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")
    machine_fingerprint: str = Field(..., min_length=64, max_length=64)


class ActivateRequest(BaseModel):
    license_key: str = Field(..., min_length=19, max_length=19, pattern=r"^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")
    machine_fingerprint: str = Field(..., min_length=64, max_length=64)
    machine_name: str = Field(..., max_length=255)
    machine_hostname: str = Field(..., max_length=255)


class HeartbeatRequest(BaseModel):
    license_key: str = Field(..., min_length=19, max_length=19)
    machine_fingerprint: str = Field(..., min_length=64, max_length=64)


class DeactivateRequest(BaseModel):
    license_key: str = Field(..., min_length=19, max_length=19)
    machine_fingerprint: str = Field(..., min_length=64, max_length=64)


class LicenseTokenResponse(BaseModel):
    token: str
    customer_name: str
    license_expires_at: str | None
    token_expires_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_valid_license(license_key: str, db: Session) -> License:
    """Fetch license and raise 404/403 if not found or not active."""
    lic = db.query(License).filter(License.key == license_key).first()
    if not lic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License key not found")

    eff = lic.effective_status()
    if eff == "expired":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="License has expired")
    if eff == "suspended":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="License is suspended")
    return lic


def _build_token_response(lic: License, fingerprint: str) -> LicenseTokenResponse:
    import jwt as _jwt
    token = create_license_token(
        license_key=lic.key,
        machine_fingerprint=fingerprint,
        customer_name=lic.customer_name,
        license_expires_at=lic.expires_at,
    )
    # Decode to get expiry for response (no verification needed — we just created it)
    decoded = _jwt.decode(token, options={"verify_signature": False})
    token_exp = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc).isoformat()
    return LicenseTokenResponse(
        token=token,
        customer_name=lic.customer_name,
        license_expires_at=lic.expires_at.isoformat() if lic.expires_at else None,
        token_expires_at=token_exp,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/validate", response_model=LicenseTokenResponse)
def validate_license(req: ValidateRequest, request: Request, db: Session = Depends(get_db)):
    """
    Validate a license key + machine fingerprint.
    Called on every app startup — returns a fresh JWT if valid.
    Requires an existing active activation matching the fingerprint.
    """
    lic = _get_valid_license(req.license_key, db)

    # Check activation exists for this fingerprint
    activation = (
        db.query(Activation)
        .filter(
            Activation.license_id == lic.id,
            Activation.machine_fingerprint == req.machine_fingerprint,
            Activation.is_active == True,
        )
        .first()
    )
    if not activation:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This machine is not activated for this license. Please activate first.",
        )

    # Update heartbeat on validate
    activation.last_heartbeat = datetime.now(timezone.utc)
    db.commit()

    return _build_token_response(lic, req.machine_fingerprint)


@router.post("/activate", response_model=LicenseTokenResponse)
def activate_license(req: ActivateRequest, request: Request, db: Session = Depends(get_db)):
    """
    First-time activation of a license on a machine.
    Only one machine can hold an active activation at a time (node-locked).
    If the license already has an active activation on a different machine, returns 409.
    """
    lic = _get_valid_license(req.license_key, db)

    # Check if this fingerprint is already activated (reactivation after reinstall)
    existing = (
        db.query(Activation)
        .filter(
            Activation.license_id == lic.id,
            Activation.machine_fingerprint == req.machine_fingerprint,
        )
        .first()
    )
    if existing:
        if existing.is_active:
            # Already activated on this machine — just refresh heartbeat and return token
            existing.last_heartbeat = datetime.now(timezone.utc)
            existing.machine_name = req.machine_name
            existing.machine_hostname = req.machine_hostname
            db.commit()
            return _build_token_response(lic, req.machine_fingerprint)
        else:
            # Was deactivated — reactivate on same machine
            # Check if another machine holds an active activation first
            other_active = (
                db.query(Activation)
                .filter(
                    Activation.license_id == lic.id,
                    Activation.machine_fingerprint != req.machine_fingerprint,
                    Activation.is_active == True,
                )
                .first()
            )
            if other_active:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"License is already active on machine '{other_active.machine_name or other_active.machine_hostname}'. "
                        "Contact support to transfer the license."
                    ),
                )
            existing.is_active = True
            existing.activated_at = datetime.now(timezone.utc)
            existing.last_heartbeat = datetime.now(timezone.utc)
            existing.machine_name = req.machine_name
            existing.machine_hostname = req.machine_hostname
            db.commit()
            return _build_token_response(lic, req.machine_fingerprint)

    # Check if any OTHER machine is already active
    active_on_other = (
        db.query(Activation)
        .filter(
            Activation.license_id == lic.id,
            Activation.is_active == True,
        )
        .first()
    )
    if active_on_other:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"License is already active on machine '{active_on_other.machine_name or active_on_other.machine_hostname}'. "
                "Contact support to transfer the license."
            ),
        )

    # Create new activation
    activation = Activation(
        license_id=lic.id,
        machine_fingerprint=req.machine_fingerprint,
        machine_name=req.machine_name,
        machine_hostname=req.machine_hostname,
        last_heartbeat=datetime.now(timezone.utc),
        is_active=True,
    )
    db.add(activation)
    db.commit()
    db.refresh(activation)

    return _build_token_response(lic, req.machine_fingerprint)


@router.post("/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
def heartbeat(req: HeartbeatRequest, request: Request, db: Session = Depends(get_db)):
    """
    Periodic ping from VP CTRL app to keep activation alive and detect suspensions.
    Client should call this every ~60 minutes.
    Returns 204 on success, 403 if license is no longer valid.
    """
    lic = _get_valid_license(req.license_key, db)

    activation = (
        db.query(Activation)
        .filter(
            Activation.license_id == lic.id,
            Activation.machine_fingerprint == req.machine_fingerprint,
            Activation.is_active == True,
        )
        .first()
    )
    if not activation:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active activation found for this machine.",
        )

    activation.last_heartbeat = datetime.now(timezone.utc)
    db.commit()


@router.post("/deactivate", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_license(req: DeactivateRequest, request: Request, db: Session = Depends(get_db)):
    """
    Clean deactivation when app closes gracefully.
    Marks the activation as inactive — machine can be reactivated later.
    This is a soft deactivation from the client side; admin can also force-deactivate.
    """
    lic = db.query(License).filter(License.key == req.license_key).first()
    if not lic:
        # Silent — no need to expose key existence on deactivation
        return

    activation = (
        db.query(Activation)
        .filter(
            Activation.license_id == lic.id,
            Activation.machine_fingerprint == req.machine_fingerprint,
            Activation.is_active == True,
        )
        .first()
    )
    if activation:
        activation.is_active = False
        db.commit()
