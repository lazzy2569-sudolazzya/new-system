"""Ledger operations shared by routers and tests. Current stock is never a
stored number -- it is always computed from stock_movements (plan section
3.1). Every write here is a single INSERT; corrections go through
reverse_movement, never UPDATE/DELETE (which the database blocks anyway).
"""
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import MovementType, Product, StockMovement


def current_stock(db: Session, product_id: int, location_id: int) -> Decimal:
    total = db.execute(
        select(func.coalesce(func.sum(StockMovement.quantity_signed), 0)).where(
            StockMovement.product_id == product_id,
            StockMovement.location_id == location_id,
        )
    ).scalar_one()
    return Decimal(total)


def post_movement(
    db: Session,
    *,
    product_id: int,
    location_id: int,
    movement_type: MovementType,
    quantity_signed: Decimal,
    reference_type: str,
    reference_id: int,
    user_id: int,
    unit_cost: Decimal | None = None,
    note: str | None = None,
) -> StockMovement:
    movement = StockMovement(
        product_id=product_id,
        location_id=location_id,
        movement_type=movement_type,
        quantity_signed=quantity_signed,
        unit_cost=unit_cost,
        reference_type=reference_type,
        reference_id=reference_id,
        user_id=user_id,
        note=note,
    )
    db.add(movement)
    db.flush()
    return movement


def reverse_movement(db: Session, movement: StockMovement, *, user_id: int, note: str | None = None) -> StockMovement:
    """Corrects a mistake by inserting an offsetting row, never by editing
    or deleting the original (plan section 3.1) -- history stays intact.
    """
    return post_movement(
        db,
        product_id=movement.product_id,
        location_id=movement.location_id,
        movement_type=MovementType.reversal,
        quantity_signed=-movement.quantity_signed,
        reference_type=movement.reference_type,
        reference_id=movement.reference_id,
        user_id=user_id,
        unit_cost=movement.unit_cost,
        note=note or f"reversal of movement {movement.id}",
    )


def low_stock_products(db: Session) -> list[tuple[Product, Decimal]]:
    """Products whose current stock (summed across all locations) is at or
    below their reorder level.
    """
    rows = db.execute(
        select(Product, func.coalesce(func.sum(StockMovement.quantity_signed), 0))
        .outerjoin(StockMovement, StockMovement.product_id == Product.id)
        .group_by(Product.id)
        .having(func.coalesce(func.sum(StockMovement.quantity_signed), 0) <= Product.reorder_level)
    ).all()
    return [(product, Decimal(total)) for product, total in rows]
