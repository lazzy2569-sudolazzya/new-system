"""Gap from the original review: the plan's test suite covered correctness
(permissions, ledger invariants, offline sync) but had nothing on
concurrent load, and the phase-2 exit criterion is a client running real
concurrent stock activity in parallel with their existing process. This is
a basic version of that check -- N independent DB sessions writing to the
same ledger row-set simultaneously, verifying the total is exactly right
and nothing errors, deadlocks, or gets lost.

Uses real independent engine connections, not the shared per-test `db`
session -- a SQLAlchemy Session is not thread-safe, so sharing one across
threads would test the wrong thing (or just crash).
"""
import threading
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Location, MovementType, Product, Role, User
from app.security import hash_password
from app.services.stock import current_stock, post_movement
from tests.conftest import TEST_DATABASE_URL

NUM_WRITERS = 25


def test_concurrent_writers_produce_correct_total(db):
    role = Role(name="concurrency_role")
    db.add(role)
    db.flush()
    user = User(
        username="concurrencyuser", full_name="Concurrency User",
        password_hash=hash_password("x"), role_id=role.id,
    )
    location = Location(name="ConcurrencyLoc")
    product = Product(sku="CONC-1", name="Concurrency Product", unit_of_measure="pcs", reorder_level=0)
    db.add_all([user, location, product])
    db.commit()
    product_id, location_id, user_id = product.id, location.id, user.id

    engine = create_engine(TEST_DATABASE_URL)
    session_factory = sessionmaker(bind=engine)
    errors: list[Exception] = []

    def write_one() -> None:
        session = session_factory()
        try:
            post_movement(
                session, product_id=product_id, location_id=location_id,
                movement_type=MovementType.adjustment, quantity_signed=Decimal("1"),
                reference_type="concurrency_test", reference_id=product_id, user_id=user_id,
            )
            session.commit()
        except Exception as exc:  # surfaced via `errors`, not raised on a worker thread
            errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=write_one) for _ in range(NUM_WRITERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    engine.dispose()

    assert errors == [], f"concurrent writers raised: {errors}"
    assert current_stock(db, product_id, location_id) == Decimal(NUM_WRITERS)
