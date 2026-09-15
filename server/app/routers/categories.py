from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Category
from app.permissions import RequirePermission
from app.schemas import CategoryIn, CategoryOut

router = APIRouter(prefix="/api/v1/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut], dependencies=[Depends(RequirePermission("inventory.view"))])
def list_categories(db: Session = Depends(get_db)) -> list[CategoryOut]:
    rows = db.query(Category).order_by(Category.name).all()
    return [CategoryOut(id=r.id, name=r.name, description=r.description) for r in rows]


@router.post("", response_model=CategoryOut, dependencies=[Depends(RequirePermission("inventory.manage"))])
def create_category(payload: CategoryIn, db: Session = Depends(get_db)) -> CategoryOut:
    row = Category(name=payload.name, description=payload.description)
    db.add(row)
    db.commit()
    db.refresh(row)
    return CategoryOut(id=row.id, name=row.name, description=row.description)
