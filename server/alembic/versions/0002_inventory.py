"""inventory: categories, locations, products, append-only stock ledger

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-15

"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

MOVEMENT_TYPE = sa.Enum(
    "opening_balance",
    "purchase_receipt",
    "sale_issue",
    "transfer_in",
    "transfer_out",
    "adjustment",
    "reversal",
    name="movement_type",
)


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text),
    )

    op.create_table(
        "locations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("address", sa.Text),
    )

    op.create_table(
        "products",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sku", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category_id", sa.Integer, sa.ForeignKey("categories.id")),
        sa.Column("unit_of_measure", sa.String(20), nullable=False),
        sa.Column("reorder_level", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("unit_cost", sa.Numeric(18, 4)),
    )

    op.create_table(
        "stock_movements",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id"), nullable=False),
        sa.Column("location_id", sa.Integer, sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("movement_type", MOVEMENT_TYPE, nullable=False),
        sa.Column("quantity_signed", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 4)),
        sa.Column("reference_type", sa.Text, nullable=False),
        sa.Column("reference_id", sa.BigInteger, nullable=False),
        sa.Column("reverses_id", sa.BigInteger, sa.ForeignKey("stock_movements.id")),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("note", sa.Text),
        sa.CheckConstraint("quantity_signed <> 0", name="ck_quantity_signed_nonzero"),
    )
    op.create_index("ix_sm_product_location", "stock_movements", ["product_id", "location_id"])
    op.create_index("ix_sm_occurred", "stock_movements", ["occurred_at"])

    # Append-only, enforced at the database, not by application convention
    # -- a quick fix script run directly against the database is blocked
    # the same as the API would be (plan section 3.1).
    op.execute(
        "CREATE RULE stock_movements_no_update AS ON UPDATE TO stock_movements DO INSTEAD NOTHING"
    )
    op.execute(
        "CREATE RULE stock_movements_no_delete AS ON DELETE TO stock_movements DO INSTEAD NOTHING"
    )

    # Audit trigger on the mutable inventory tables, reusing the generic
    # function from migration 0001. stock_movements itself needs no audit
    # trigger -- it can only ever be inserted into, so every row already
    # is its own permanent record.
    for table in ("categories", "locations", "products"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_audit
            AFTER INSERT OR UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION audit_row_change();
            """
        )

    op.execute(
        "INSERT INTO permissions (code, description) VALUES "
        "('inventory.view', 'List products, categories, locations'),"
        "('inventory.view_cost', 'See product unit cost'),"
        "('inventory.manage', 'Create/edit products, categories, locations'),"
        "('inventory.adjust', 'Post stock adjustments and opening balances')"
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE r.name = 'admin'
          AND p.code IN ('inventory.view', 'inventory.view_cost', 'inventory.manage', 'inventory.adjust')
        """
    )

    op.execute(
        "INSERT INTO roles (name, description) VALUES "
        "('storekeeper', 'Inventory floor staff, no cost visibility')"
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE r.name = 'storekeeper' AND p.code IN ('inventory.view', 'inventory.adjust')
        """
    )


def downgrade() -> None:
    # role_permissions rows must go first -- both roles and permissions are
    # referenced by it, so deleting either one first trips a foreign key
    # violation.
    op.execute(
        "DELETE FROM role_permissions WHERE role_id IN (SELECT id FROM roles WHERE name = 'storekeeper')"
    )
    op.execute(
        "DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code IN "
        "('inventory.view', 'inventory.view_cost', 'inventory.manage', 'inventory.adjust'))"
    )
    op.execute("DELETE FROM roles WHERE name = 'storekeeper'")
    op.execute(
        "DELETE FROM permissions WHERE code IN "
        "('inventory.view', 'inventory.view_cost', 'inventory.manage', 'inventory.adjust')"
    )
    for table in ("categories", "locations", "products"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_audit ON {table}")
    op.execute("DROP RULE IF EXISTS stock_movements_no_delete ON stock_movements")
    op.execute("DROP RULE IF EXISTS stock_movements_no_update ON stock_movements")
    op.drop_index("ix_sm_occurred", table_name="stock_movements")
    op.drop_index("ix_sm_product_location", table_name="stock_movements")
    op.drop_table("stock_movements")
    # op.create_table auto-creates an Enum column's type as part of table
    # creation, but op.drop_table is just a bare DROP TABLE -- it has no
    # column information and so never drops the type. Without this, the
    # type is left behind and the *next* upgrade fails with "type
    # movement_type already exists" when create_table tries to recreate it.
    MOVEMENT_TYPE.drop(op.get_bind())
    op.drop_table("products")
    op.drop_table("locations")
    op.drop_table("categories")
