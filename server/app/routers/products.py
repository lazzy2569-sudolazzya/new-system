import csv
import io

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Category, Location, MovementType, Product, User
from app.permissions import RequirePermission, get_current_user
from app.schemas import (
    DEFAULT_PRODUCT_SCHEMA,
    PRODUCT_RESPONSE_SCHEMA_BY_PERMISSION,
    ImportResult,
    LowStockItem,
    ProductIn,
    ProductPublic,
    ProductWithCost,
)
from app.services.stock import low_stock_products, post_movement

router = APIRouter(prefix="/api/v1/products", tags=["products"])


def _product_schema_for(user: User) -> type[ProductPublic]:
    for permission, candidate in PRODUCT_RESPONSE_SCHEMA_BY_PERMISSION.items():
        if user.has_permission(permission):
            return candidate
    return DEFAULT_PRODUCT_SCHEMA


def _serialize(schema: type[ProductPublic], row: Product) -> ProductPublic:
    if schema is ProductWithCost:
        return ProductWithCost(
            id=row.id, sku=row.sku, name=row.name, category_id=row.category_id,
            unit_of_measure=row.unit_of_measure, reorder_level=row.reorder_level,
            unit_cost=row.unit_cost,
        )
    return ProductPublic(
        id=row.id, sku=row.sku, name=row.name, category_id=row.category_id,
        unit_of_measure=row.unit_of_measure, reorder_level=row.reorder_level,
    )


@router.get("", response_model=None, dependencies=[Depends(RequirePermission("inventory.view"))])
def list_products(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ProductPublic]:
    schema = _product_schema_for(user)
    rows = db.query(Product).order_by(Product.sku).all()
    return [_serialize(schema, r) for r in rows]


@router.post("", response_model=None, dependencies=[Depends(RequirePermission("inventory.manage"))])
def create_product(
    payload: ProductIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ProductPublic:
    # inventory.manage (can create/edit products) and inventory.view_cost
    # (can see cost) are deliberately separate permissions -- a role that
    # can set the cost is not automatically one that can see it back, so
    # this goes through the same permission-gated schema choice as
    # list_products rather than always returning ProductWithCost.
    if db.query(Product).filter_by(sku=payload.sku).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"SKU '{payload.sku}' already exists")
    row = Product(
        sku=payload.sku, name=payload.name, category_id=payload.category_id,
        unit_of_measure=payload.unit_of_measure, reorder_level=payload.reorder_level,
        unit_cost=payload.unit_cost,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize(_product_schema_for(user), row)


@router.get(
    "/low-stock",
    response_model=list[LowStockItem],
    dependencies=[Depends(RequirePermission("inventory.view"))],
)
def low_stock_report(db: Session = Depends(get_db)) -> list[LowStockItem]:
    return [
        LowStockItem(
            product_id=product.id, sku=product.sku, name=product.name,
            reorder_level=product.reorder_level, current_stock=stock,
        )
        for product, stock in low_stock_products(db)
    ]


@router.get("/export.xlsx", dependencies=[Depends(RequirePermission("inventory.view"))])
def export_products(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> StreamingResponse:
    include_cost = _product_schema_for(user) is ProductWithCost
    rows = db.query(Product).order_by(Product.sku).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Products"
    headers = ["SKU", "Name", "Unit", "Reorder Level"]
    if include_cost:
        headers.append("Unit Cost")
    ws.append(headers)
    for r in rows:
        row_values = [r.sku, r.name, r.unit_of_measure, float(r.reorder_level)]
        if include_cost:
            row_values.append(float(r.unit_cost) if r.unit_cost is not None else None)
        ws.append(row_values)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=products.xlsx"},
    )


@router.post(
    "/import",
    response_model=ImportResult,
    dependencies=[Depends(RequirePermission("inventory.manage"))],
)
def import_opening_balances(
    file: UploadFile,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportResult:
    """CSV columns: sku,name,category,unit_of_measure,reorder_level,unit_cost,opening_quantity,location

    Creates the product and, if opening_quantity is nonzero, a single
    opening_balance ledger row for it. A row whose SKU already exists is
    skipped, not overwritten -- re-running an import must never silently
    duplicate or clobber stock history.
    """
    reader = csv.DictReader(io.TextIOWrapper(file.file, encoding="utf-8"))
    created = 0
    skipped: list[str] = []

    for line in reader:
        sku = line["sku"].strip()
        if db.query(Product).filter_by(sku=sku).first() is not None:
            skipped.append(sku)
            continue

        category = None
        if line.get("category"):
            category = db.query(Category).filter_by(name=line["category"]).first()
            if category is None:
                category = Category(name=line["category"])
                db.add(category)
                db.flush()

        location_name = line.get("location") or "Main"
        location = db.query(Location).filter_by(name=location_name).first()
        if location is None:
            location = Location(name=location_name)
            db.add(location)
            db.flush()

        product = Product(
            sku=sku,
            name=line["name"],
            category_id=category.id if category else None,
            unit_of_measure=line["unit_of_measure"],
            reorder_level=line.get("reorder_level") or 0,
            unit_cost=line.get("unit_cost") or None,
        )
        db.add(product)
        db.flush()

        opening_quantity = line.get("opening_quantity") or "0"
        if float(opening_quantity) != 0:
            post_movement(
                db,
                product_id=product.id,
                location_id=location.id,
                movement_type=MovementType.opening_balance,
                quantity_signed=opening_quantity,
                reference_type="product",
                reference_id=product.id,
                user_id=user.id,
                unit_cost=product.unit_cost,
                note="opening balance import",
            )
        created += 1

    db.commit()
    return ImportResult(products_created=created, products_skipped=skipped)
