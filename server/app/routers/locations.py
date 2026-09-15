from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Location
from app.permissions import RequirePermission
from app.schemas import LocationIn, LocationOut

router = APIRouter(prefix="/api/v1/locations", tags=["locations"])


@router.get("", response_model=list[LocationOut], dependencies=[Depends(RequirePermission("inventory.view"))])
def list_locations(db: Session = Depends(get_db)) -> list[LocationOut]:
    rows = db.query(Location).order_by(Location.name).all()
    return [LocationOut(id=r.id, name=r.name, address=r.address) for r in rows]


@router.post("", response_model=LocationOut, dependencies=[Depends(RequirePermission("inventory.manage"))])
def create_location(payload: LocationIn, db: Session = Depends(get_db)) -> LocationOut:
    row = Location(name=payload.name, address=payload.address)
    db.add(row)
    db.commit()
    db.refresh(row)
    return LocationOut(id=row.id, name=row.name, address=row.address)
