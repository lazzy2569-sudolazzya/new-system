from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MovementType, User
from app.permissions import RequirePermission, get_current_user
from app.schemas import StockAdjustmentIn, StockBalanceOut, StockMovementOut
from app.services.stock import current_stock, post_movement

router = APIRouter(prefix="/api/v1/stock", tags=["stock"])


@router.post(
    "/adjustments",
    response_model=StockMovementOut,
    dependencies=[Depends(RequirePermission("inventory.adjust"))],
)
def post_adjustment(
    payload: StockAdjustmentIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StockMovementOut:
    movement = post_movement(
        db,
        product_id=payload.product_id,
        location_id=payload.location_id,
        movement_type=MovementType.adjustment,
        quantity_signed=payload.quantity_signed,
        reference_type="manual_adjustment",
        reference_id=payload.product_id,
        user_id=user.id,
        note=payload.note,
    )
    db.commit()
    return StockMovementOut(
        id=movement.id, product_id=movement.product_id, location_id=movement.location_id,
        movement_type=movement.movement_type, quantity_signed=movement.quantity_signed,
        occurred_at=movement.occurred_at, note=movement.note,
    )


@router.get(
    "/balance",
    response_model=StockBalanceOut,
    dependencies=[Depends(RequirePermission("inventory.view"))],
)
def get_balance(
    product_id: int = Query(...), location_id: int = Query(...), db: Session = Depends(get_db)
) -> StockBalanceOut:
    quantity = current_stock(db, product_id, location_id)
    return StockBalanceOut(product_id=product_id, location_id=location_id, quantity=quantity)
