"""
models.py — SQLAlchemy ORM models for VP CTRL license system.
Tables: licenses, activations, admin_users
"""

import secrets
import string
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_license_key() -> str:
    """Generate a key in format XXXX-XXXX-XXXX-XXXX using uppercase letters + digits."""
    alphabet = string.ascii_uppercase + string.digits
    groups = ["".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4)]
    return "-".join(groups)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class License(Base):
    __tablename__ = "licenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(19), unique=True, index=True, nullable=False)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # status: active | suspended | expired
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    # null = lifetime license
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    activations: Mapped[list["Activation"]] = relationship(
        "Activation", back_populates="license", cascade="all, delete-orphan"
    )

    @staticmethod
    def generate_key() -> str:
        return _generate_license_key()

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def effective_status(self) -> str:
        if self.is_expired():
            return "expired"
        return self.status

    def active_activation(self) -> "Activation | None":
        for act in self.activations:
            if act.is_active:
                return act
        return None


class Activation(Base):
    __tablename__ = "activations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    license_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("licenses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    machine_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    machine_name: Mapped[str] = mapped_column(String(255), nullable=True)
    machine_hostname: Mapped[str] = mapped_column(String(255), nullable=True)
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_heartbeat: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    license: Mapped["License"] = relationship("License", back_populates="activations")


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
