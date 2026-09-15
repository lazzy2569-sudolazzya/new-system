"""initial schema: roles, permissions, users, fiscal_years, audit_log

Revision ID: 0001
Revises:
Create Date: 2026-09-15

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("description", sa.Text),
    )

    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text),
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer, sa.ForeignKey("roles.id"), primary_key=True),
        sa.Column("permission_id", sa.Integer, sa.ForeignKey("permissions.id"), primary_key=True),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(255)),
        sa.Column("phone", sa.String(50)),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role_id", sa.Integer, sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("failed_login_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "fiscal_years",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(20), nullable=False, unique=True),
        sa.Column("start_date_ad", sa.Date, nullable=False),
        sa.Column("end_date_ad", sa.Date, nullable=False),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("table_name", sa.Text, nullable=False),
        sa.Column("record_id", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("old_values", postgresql.JSONB),
        sa.Column("new_values", postgresql.JSONB),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("client_ip", postgresql.INET),
    )

    # Generic audit trigger, attached here to `users` as the reference
    # implementation. Every future business table's migration should attach
    # the same trigger (plan section 3.5) -- this is what makes a direct SQL
    # edit against the database show up in audit_log too, not just edits
    # made through the API.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_row_change() RETURNS TRIGGER AS $$
        DECLARE
            acting_user INT;
        BEGIN
            BEGIN
                acting_user := current_setting('app.user_id', true)::INT;
            EXCEPTION WHEN OTHERS THEN
                acting_user := NULL;
            END;

            IF TG_OP = 'UPDATE' THEN
                INSERT INTO audit_log (user_id, table_name, record_id, action, old_values, new_values)
                VALUES (acting_user, TG_TABLE_NAME, NEW.id::TEXT, TG_OP, to_jsonb(OLD), to_jsonb(NEW));
            ELSIF TG_OP = 'DELETE' THEN
                INSERT INTO audit_log (user_id, table_name, record_id, action, old_values, new_values)
                VALUES (acting_user, TG_TABLE_NAME, OLD.id::TEXT, TG_OP, to_jsonb(OLD), NULL);
            ELSIF TG_OP = 'INSERT' THEN
                INSERT INTO audit_log (user_id, table_name, record_id, action, old_values, new_values)
                VALUES (acting_user, TG_TABLE_NAME, NEW.id::TEXT, TG_OP, NULL, to_jsonb(NEW));
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_users_audit
        AFTER INSERT OR UPDATE OR DELETE ON users
        FOR EACH ROW EXECUTE FUNCTION audit_row_change();
        """
    )

    # Baseline roles/permissions needed to bootstrap the first login.
    # Business-specific roles (storekeeper, accountant, ...) get added as
    # their modules land in later phases.
    op.execute("INSERT INTO roles (name, description) VALUES ('admin', 'Full system access')")
    op.execute("INSERT INTO permissions (code, description) VALUES ('users.view', 'List other users')")
    op.execute("INSERT INTO permissions (code, description) VALUES ('users.view_contact', 'See user email/phone')")
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p WHERE r.name = 'admin'
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_users_audit ON users")
    op.execute("DROP FUNCTION IF EXISTS audit_row_change")
    op.drop_table("audit_log")
    op.drop_table("fiscal_years")
    op.drop_table("users")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
