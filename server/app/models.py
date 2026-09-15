from __future__ import annotations

import datetime as dt
import enum
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id"), primary_key=True),
)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    permissions: Mapped[list["Permission"]] = relationship(
        secondary=role_permissions, back_populates="roles"
    )
    users: Mapped[list["User"]] = relationship(back_populates="role")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    roles: Mapped[list["Role"]] = relationship(
        secondary=role_permissions, back_populates="permissions"
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Login lockout state (plan gap #4: the app's own login has no
    # brute-force protection beyond the Cloudflare Access gate in front of
    # it). Incremented on each failed attempt, reset on success.
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    role: Mapped["Role"] = relationship(back_populates="users")

    def has_permission(self, code: str) -> bool:
        return any(p.code == code for p in self.role.permissions)


class FiscalYear(Base):
    __tablename__ = "fiscal_years"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    start_date_ad: Mapped[dt.date] = mapped_column(Date, nullable=False)
    end_date_ad: Mapped[dt.date] = mapped_column(Date, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    address: Mapped[str | None] = mapped_column(Text)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    unit_of_measure: Mapped[str] = mapped_column(String(20), nullable=False)
    reorder_level: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    # Sensitive: never appears in a response schema a role without
    # inventory.view_cost can receive (plan section 3.4). See
    # app/schemas.py ProductPublic vs ProductWithCost.
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))

    category: Mapped["Category | None"] = relationship()


class MovementType(str, enum.Enum):
    opening_balance = "opening_balance"
    purchase_receipt = "purchase_receipt"
    sale_issue = "sale_issue"
    transfer_in = "transfer_in"
    transfer_out = "transfer_out"
    adjustment = "adjustment"
    reversal = "reversal"


class StockMovement(Base):
    """Append-only ledger (plan section 3.1). Current stock is never a
    stored number -- it is SUM(quantity_signed) over this table, grouped by
    product and location. UPDATE/DELETE are blocked at the database level
    by a Postgres RULE (see the migration), not just by convention, so a
    quick fix script against the database can't silently corrupt history.
    A mistake is corrected by inserting a `reversal` row via reverses_id,
    never by editing or deleting the original.
    """

    __tablename__ = "stock_movements"
    __table_args__ = (CheckConstraint("quantity_signed <> 0", name="ck_quantity_signed_nonzero"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    movement_type: Mapped[MovementType] = mapped_column(
        SAEnum(MovementType, name="movement_type", native_enum=True), nullable=False
    )
    quantity_signed: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    reference_type: Mapped[str] = mapped_column(Text, nullable=False)
    reference_id: Mapped[int] = mapped_column(nullable=False)
    reverses_id: Mapped[int | None] = mapped_column(ForeignKey("stock_movements.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    occurred_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    table_name: Mapped[str] = mapped_column(Text, nullable=False)
    record_id: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    old_values: Mapped[dict | None] = mapped_column(JSONB)
    new_values: Mapped[dict | None] = mapped_column(JSONB)
    occurred_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    client_ip: Mapped[str | None] = mapped_column(INET)
