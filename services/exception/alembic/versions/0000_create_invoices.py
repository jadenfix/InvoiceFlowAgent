"""Create the original invoice schema before adding review fields.

Revision ID: 0000
Revises: None
"""

from alembic import op
import sqlalchemy as sa

revision = "0000"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "invoices",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("vendor_name", sa.String(255)),
        sa.Column("invoice_number", sa.String(100)),
        sa.Column("total_amount", sa.Numeric(10, 2)),
        sa.Column("invoice_date", sa.DateTime()),
        sa.Column("due_date", sa.DateTime()),
        sa.Column("file_path", sa.String(500)),
        sa.Column("file_type", sa.String(50)),
        sa.Column("status", sa.String(50)),
        sa.Column("matched_status", sa.String(50)),
        sa.Column("extracted_vendor", sa.String(255)),
        sa.Column("extracted_amount", sa.Numeric(10, 2)),
        sa.Column("extracted_invoice_number", sa.String(100)),
        sa.Column("extracted_date", sa.DateTime()),
        sa.Column("confidence_score", sa.Numeric(5, 4)),
        sa.Column("match_details", sa.Text()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )


def downgrade():
    op.drop_table("invoices")
