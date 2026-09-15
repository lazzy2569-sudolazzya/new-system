import datetime as dt
from decimal import Decimal

from pydantic import BaseModel

from app.models import MovementType


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserPublic(BaseModel):
    id: int
    username: str
    full_name: str
    role: str


class UserWithContact(UserPublic):
    """Superset of UserPublic, never the other way around.

    Plan section 3.4: a new sensitive field must be explicitly added to the
    privileged schema to become visible anywhere. A single schema with
    optional fields fails open (a new column defaults to visible); separate
    classes fail closed.
    """

    email: str | None = None
    phone: str | None = None


# Selected server-side by the caller's permissions -- see routers/users.py.
# Keyed by the permission that unlocks the richer schema; the endpoint picks
# the first match and falls back to UserPublic.
RESPONSE_SCHEMA_BY_PERMISSION: dict[str, type[UserPublic]] = {
    "users.view_contact": UserWithContact,
}
DEFAULT_USER_SCHEMA: type[UserPublic] = UserPublic


class CategoryIn(BaseModel):
    name: str
    description: str | None = None


class CategoryOut(CategoryIn):
    id: int


class LocationIn(BaseModel):
    name: str
    address: str | None = None


class LocationOut(LocationIn):
    id: int


class ProductIn(BaseModel):
    sku: str
    name: str
    category_id: int | None = None
    unit_of_measure: str
    reorder_level: Decimal = Decimal("0")
    unit_cost: Decimal | None = None


class ProductPublic(BaseModel):
    """This is the flagship example from plan section 3.4: the storekeeper
    can legitimately call GET /products, but unit_cost must never appear
    in that response. See ProductWithCost below and
    routers/products.py:list_products for how the schema is picked.
    """

    id: int
    sku: str
    name: str
    category_id: int | None
    unit_of_measure: str
    reorder_level: Decimal


class ProductWithCost(ProductPublic):
    unit_cost: Decimal | None = None


# Kept separate from RESPONSE_SCHEMA_BY_PERMISSION above -- these are two
# unrelated domains (products vs. users), and merging them into one dict
# would mean an admin's users.view_contact and inventory.view_cost
# permissions racing each other by dict iteration order.
PRODUCT_RESPONSE_SCHEMA_BY_PERMISSION: dict[str, type[ProductPublic]] = {
    "inventory.view_cost": ProductWithCost,
}
DEFAULT_PRODUCT_SCHEMA: type[ProductPublic] = ProductPublic


class StockAdjustmentIn(BaseModel):
    product_id: int
    location_id: int
    quantity_signed: Decimal
    note: str | None = None


class StockMovementOut(BaseModel):
    id: int
    product_id: int
    location_id: int
    movement_type: MovementType
    quantity_signed: Decimal
    occurred_at: dt.datetime
    note: str | None


class StockBalanceOut(BaseModel):
    product_id: int
    location_id: int
    quantity: Decimal


class LowStockItem(BaseModel):
    product_id: int
    sku: str
    name: str
    reorder_level: Decimal
    current_stock: Decimal


class ImportResult(BaseModel):
    products_created: int
    products_skipped: list[str]
