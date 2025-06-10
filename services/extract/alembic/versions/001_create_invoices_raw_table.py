"""Create invoices_raw table for extraction service

Revision ID: 001_invoices_raw
Revises: 
Create Date: 2024-01-09 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_invoices_raw'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create invoices_raw table
    op.create_table(
        'invoices_raw',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('request_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('raw_s3_key', sa.String(), nullable=False),
        sa.Column('fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['request_id'], ['ingestions.id'], ),
        sa.CheckConstraint("status IN ('PROCESSING', 'FAILED', 'COMPLETED')", name='valid_status'),
    )
    
    # Create index on request_id
    op.create_index('ix_invoices_raw_request_id', 'invoices_raw', ['request_id'])
    
    # Create trigger for updating updated_at timestamp
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)
    
    op.execute("""
        CREATE TRIGGER update_invoices_raw_updated_at 
        BEFORE UPDATE ON invoices_raw 
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)


def downgrade() -> None:
    # Drop trigger and function
    op.execute("DROP TRIGGER IF EXISTS update_invoices_raw_updated_at ON invoices_raw;")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column();")
    
    # Drop table
    op.drop_table('invoices_raw') 