"""
routes/admin.py — Admin portal backend endpoints.
All endpoints except /login require a valid admin JWT.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from auth import (
    create_admin_token,
    get_current_admin,
    hash_password,
    verify_password,
)
from database import get_db
from models import Activation, AdminUser, License

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class AdminTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


class ActivationOut(BaseModel):
    id: int
    machine_fingerprint: str
    machine_name: Optional[str]
    machine_hostname: Optional[str]
    activated_at: datetime
    last_heartbeat: Optional[datetime]
    is_active: bool

    class Config:
        from_attributes = True


class LicenseOut(BaseModel):
    id: int
    key: str
    customer_name: str
    customer_email: str
    status: str
    effective_status: str
    expires_at: Optional[datetime]
    created_at: datetime
    active_machine: Optional[str]  # machine_name or hostname of active activation
    total_activations: int

    class Config:
        from_attributes = True


class LicenseDetailOut(LicenseOut):
    activations: list[ActivationOut]


class CreateLicenseRequest(BaseModel):
    customer_name: str = Field(..., min_length=2, max_length=255)
    customer_email: EmailStr
    expires_at: Optional[datetime] = None  # null = lifetime


class UpdateLicenseRequest(BaseModel):
    status: Optional[str] = Field(None, pattern="^(active|suspended|expired)$")
    expires_at: Optional[datetime] = None
    customer_name: Optional[str] = Field(None, max_length=255)
    customer_email: Optional[EmailStr] = None


# ---------------------------------------------------------------------------
# Helper — build LicenseOut from ORM object
# ---------------------------------------------------------------------------

def _license_to_out(lic: License) -> dict:
    active_act = lic.active_activation()
    active_machine = None
    if active_act:
        active_machine = active_act.machine_name or active_act.machine_hostname
    return {
        "id": lic.id,
        "key": lic.key,
        "customer_name": lic.customer_name,
        "customer_email": lic.customer_email,
        "status": lic.status,
        "effective_status": lic.effective_status(),
        "expires_at": lic.expires_at,
        "created_at": lic.created_at,
        "active_machine": active_machine,
        "total_activations": len(lic.activations),
    }


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@router.post("/login", response_model=AdminTokenResponse)
def admin_login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Login with username + password, returns admin JWT."""
    user = db.query(AdminUser).filter(AdminUser.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_admin_token(user.username)
    return AdminTokenResponse(access_token=token, username=user.username)


# ---------------------------------------------------------------------------
# License management
# ---------------------------------------------------------------------------

@router.get("/licenses", response_model=list[LicenseOut])
def list_licenses(
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    """List all licenses, newest first."""
    licenses = db.query(License).order_by(License.created_at.desc()).all()
    return [LicenseOut(**_license_to_out(lic)) for lic in licenses]


@router.post("/licenses", response_model=LicenseDetailOut, status_code=status.HTTP_201_CREATED)
def create_license(
    req: CreateLicenseRequest,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    """Create a new license — generates a unique key automatically."""
    # Ensure uniqueness (extremely unlikely collision, but guard anyway)
    for _ in range(10):
        key = License.generate_key()
        if not db.query(License).filter(License.key == key).first():
            break
    else:
        raise HTTPException(status_code=500, detail="Could not generate unique license key")

    expires_at = req.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    lic = License(
        key=key,
        customer_name=req.customer_name,
        customer_email=req.customer_email,
        status="active",
        expires_at=expires_at,
    )
    db.add(lic)
    db.commit()
    db.refresh(lic)

    out = _license_to_out(lic)
    out["activations"] = []
    return LicenseDetailOut(**out)


@router.get("/licenses/{license_id}", response_model=LicenseDetailOut)
def get_license(
    license_id: int,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    """Get license detail with all activation history."""
    lic = db.query(License).filter(License.id == license_id).first()
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")
    out = _license_to_out(lic)
    out["activations"] = [ActivationOut.model_validate(a) for a in lic.activations]
    return LicenseDetailOut(**out)


@router.put("/licenses/{license_id}", response_model=LicenseDetailOut)
def update_license(
    license_id: int,
    req: UpdateLicenseRequest,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    """Update license status, expiry, or customer info."""
    lic = db.query(License).filter(License.id == license_id).first()
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")

    if req.status is not None:
        lic.status = req.status
    if req.expires_at is not None:
        expires_at = req.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        lic.expires_at = expires_at
    if req.customer_name is not None:
        lic.customer_name = req.customer_name
    if req.customer_email is not None:
        lic.customer_email = req.customer_email

    db.commit()
    db.refresh(lic)

    out = _license_to_out(lic)
    out["activations"] = [ActivationOut.model_validate(a) for a in lic.activations]
    return LicenseDetailOut(**out)


@router.delete("/licenses/{license_id}/activations/{activation_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_machine(
    license_id: int,
    activation_id: int,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    """
    Admin force-deactivates a machine activation.
    This allows the customer to activate on a new machine (license transfer).
    """
    activation = (
        db.query(Activation)
        .filter(
            Activation.id == activation_id,
            Activation.license_id == license_id,
        )
        .first()
    )
    if not activation:
        raise HTTPException(status_code=404, detail="Activation not found")

    activation.is_active = False
    db.commit()


# ---------------------------------------------------------------------------
# Bootstrap — create first admin user (only if no admin exists)
# ---------------------------------------------------------------------------

@router.post("/bootstrap", status_code=status.HTTP_201_CREATED, include_in_schema=False)
def bootstrap_admin(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    One-time endpoint to create the first admin user.
    Disabled automatically once any admin exists.
    Remove from production or protect with firewall after first use.
    """
    count = db.query(AdminUser).count()
    if count > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bootstrap disabled — admin user already exists.",
        )
    user = AdminUser(
        username=form_data.username,
        password_hash=hash_password(form_data.password),
    )
    db.add(user)
    db.commit()
    return {"message": f"Admin user '{form_data.username}' created successfully."}
