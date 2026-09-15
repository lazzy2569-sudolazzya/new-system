"""Plan section 6.3.C: computed stock must always equal the sum of the
ledger, a reversal must restore the prior balance exactly, and the
database itself -- not just application code -- must reject UPDATE/DELETE
on stock_movements.

Note on fixtures + hypothesis: a pytest fixture is resolved once per test
*invocation*, not once per generated example, so seeding data naively
inside a @given-decorated function accumulates across examples and trips
unique constraints on the second example onward. _ledger_fixtures() is
therefore get-or-create, and each example gets its own fresh product so
examples never share ledger state.
"""
import uuid
from decimal import Decimal

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text

from app.models import Location, MovementType, Product, Role, User
from app.security import hash_password
from app.services.stock import current_stock, post_movement, reverse_movement

quantity_strategy = st.decimals(
    min_value="-1000", max_value="1000", places=2, allow_nan=False, allow_infinity=False
).filter(lambda d: d != 0)


def _ledger_fixtures(db):
    role = db.query(Role).filter_by(name="ledger_test_role").first()
    if role is None:
        role = Role(name="ledger_test_role")
        db.add(role)
        db.flush()
    user = db.query(User).filter_by(username="ledgeruser").first()
    if user is None:
        user = User(
            username="ledgeruser", full_name="Ledger User",
            password_hash=hash_password("x"), role_id=role.id,
        )
        db.add(user)
    location = db.query(Location).filter_by(name="Main").first()
    if location is None:
        location = Location(name="Main")
        db.add(location)
    db.commit()
    return user, location


def _new_product(db):
    product = Product(
        sku=f"LEDGER-{uuid.uuid4().hex[:16]}", name="Ledger Product",
        unit_of_measure="pcs", reorder_level=0,
    )
    db.add(product)
    db.commit()
    return product


@settings(deadline=None, max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(quantities=st.lists(quantity_strategy, min_size=1, max_size=30))
def test_computed_stock_equals_sum_of_movements(db, quantities):
    user, location = _ledger_fixtures(db)
    product = _new_product(db)

    for q in quantities:
        post_movement(
            db, product_id=product.id, location_id=location.id,
            movement_type=MovementType.adjustment, quantity_signed=q,
            reference_type="test", reference_id=product.id, user_id=user.id,
        )
    db.commit()

    assert current_stock(db, product.id, location.id) == sum(quantities)


@settings(deadline=None, max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(quantities=st.lists(quantity_strategy, min_size=1, max_size=10))
def test_reversal_restores_prior_balance(db, quantities):
    user, location = _ledger_fixtures(db)
    product = _new_product(db)

    for q in quantities:
        post_movement(
            db, product_id=product.id, location_id=location.id,
            movement_type=MovementType.adjustment, quantity_signed=q,
            reference_type="test", reference_id=product.id, user_id=user.id,
        )
    db.commit()
    before = current_stock(db, product.id, location.id)

    extra = post_movement(
        db, product_id=product.id, location_id=location.id,
        movement_type=MovementType.adjustment, quantity_signed=Decimal("7.5"),
        reference_type="test", reference_id=product.id, user_id=user.id,
    )
    db.commit()
    reverse_movement(db, extra, user_id=user.id)
    db.commit()

    assert current_stock(db, product.id, location.id) == before


def test_stock_movements_reject_update_and_delete(db):
    user, location = _ledger_fixtures(db)
    product = _new_product(db)
    movement = post_movement(
        db, product_id=product.id, location_id=location.id,
        movement_type=MovementType.adjustment, quantity_signed=Decimal("5"),
        reference_type="test", reference_id=product.id, user_id=user.id,
    )
    db.commit()

    db.execute(text("UPDATE stock_movements SET quantity_signed = 999 WHERE id = :i"), {"i": movement.id})
    db.commit()
    db.expire_all()
    refreshed = db.get(type(movement), movement.id)
    assert refreshed.quantity_signed == Decimal("5.0000"), "UPDATE was not blocked by the database rule"

    db.execute(text("DELETE FROM stock_movements WHERE id = :i"), {"i": movement.id})
    db.commit()
    still_there = db.get(type(movement), movement.id)
    assert still_there is not None, "DELETE was not blocked by the database rule"
