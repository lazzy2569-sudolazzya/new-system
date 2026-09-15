"""The flagship example from plan sections 3.4 and 6.3: a storekeeper can
legitimately call GET /products, but unit_cost must never appear in that
response. Checks the raw JSON text, not the parsed object, so a cost field
added to a nested object later would still be caught.
"""
from app.models import Category, Product


def _seed_product(db):
    category = Category(name="Beverages")
    db.add(category)
    db.flush()
    product = Product(
        sku="SKU-001", name="Cola 500ml", category_id=category.id,
        unit_of_measure="bottle", reorder_level=10, unit_cost="25.50",
    )
    db.add(product)
    db.commit()
    return product


def test_storekeeper_sees_products_without_cost(client, make_user, login_as, db):
    _seed_product(db)
    make_user("storekeeper1", "pw123456789", role_name="storekeeper", permissions=["inventory.view"])
    token = login_as("storekeeper1", "pw123456789")

    resp = client.get("/api/v1/products", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.text
    for forbidden in ("unit_cost", "25.50", "25.5"):
        assert forbidden not in body, f"{forbidden} leaked to a role without inventory.view_cost"


def test_manager_sees_products_with_cost(client, make_user, login_as, db):
    _seed_product(db)
    make_user(
        "manager1", "pw123456789", role_name="manager",
        permissions=["inventory.view", "inventory.view_cost"],
    )
    token = login_as("manager1", "pw123456789")

    resp = client.get("/api/v1/products", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["unit_cost"] == "25.50" or float(body[0]["unit_cost"]) == 25.50


def test_export_excludes_cost_column_without_permission(client, make_user, login_as, db):
    _seed_product(db)
    make_user("storekeeper2", "pw123456789", role_name="storekeeper", permissions=["inventory.view"])
    token = login_as("storekeeper2", "pw123456789")

    resp = client.get("/api/v1/products/export.xlsx", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200

    import io

    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(resp.content))
    header_row = [cell.value for cell in wb.active[1]]
    assert "Unit Cost" not in header_row


def test_create_product_response_hides_cost_without_view_cost_permission(client, make_user, login_as):
    # inventory.manage (can set the cost) and inventory.view_cost (can see
    # it back) are separate permissions on purpose -- a role with only the
    # former must not have cost echoed back in the create response either.
    make_user("clerk1", "pw123456789", role_name="clerk", permissions=["inventory.manage"])
    token = login_as("clerk1", "pw123456789")

    resp = client.post(
        "/api/v1/products",
        json={"sku": "SKU-777", "name": "Clerk Item", "unit_of_measure": "pcs", "unit_cost": 42.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "unit_cost" not in resp.text


def test_create_product_response_includes_cost_with_view_cost_permission(client, make_user, login_as):
    make_user(
        "manager2", "pw123456789", role_name="manager2",
        permissions=["inventory.manage", "inventory.view_cost"],
    )
    token = login_as("manager2", "pw123456789")

    resp = client.post(
        "/api/v1/products",
        json={"sku": "SKU-778", "name": "Manager Item", "unit_of_measure": "pcs", "unit_cost": 42.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert float(resp.json()["unit_cost"]) == 42.0


def test_create_product_requires_manage_permission(client, make_user, login_as):
    make_user("storekeeper3", "pw123456789", role_name="storekeeper", permissions=["inventory.view"])
    token = login_as("storekeeper3", "pw123456789")

    resp = client.post(
        "/api/v1/products",
        json={"sku": "SKU-999", "name": "New Item", "unit_of_measure": "pcs"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
