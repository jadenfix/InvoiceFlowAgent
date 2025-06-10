"""Create purchase_orders table and update invoices table with matching fields

Revision ID: 001
Revises: 
Create Date: 2024-01-20 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create purchase_orders table
    op.create_table(
        'purchase_orders',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('po_number', sa.Text(), nullable=False),
        sa.Column('order_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('po_number')
    )
    
    # Create indexes for purchase_orders
    op.create_index('idx_po_number', 'purchase_orders', ['po_number'], unique=False)
    op.create_index('idx_total_amount', 'purchase_orders', ['total_amount'], unique=False)
    
    # Check if invoices table exists, if not create it
    # (This assumes the table might exist from extract service)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'invoices' not in inspector.get_table_names():
        # Create invoices table if it doesn't exist
        op.create_table(
            'invoices',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('request_id', sa.String(length=255), nullable=False),
            sa.Column('vendor_name', sa.Text(), nullable=True),
            sa.Column('invoice_number', sa.String(length=255), nullable=True),
            sa.Column('invoice_date', sa.DateTime(timezone=True), nullable=True),
            sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
            sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=True),
            sa.Column('tax_amount', sa.Numeric(precision=12, scale=2), nullable=True),
            sa.Column('line_items', sa.JSON(), nullable=True),
            sa.Column('po_numbers', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('request_id')
        )
        
        # Create indexes for new invoices table
        op.create_index('idx_request_id', 'invoices', ['request_id'], unique=False)
        op.create_index('idx_invoice_number', 'invoices', ['invoice_number'], unique=False)
        op.create_index('idx_vendor_name', 'invoices', ['vendor_name'], unique=False)
    
    # Add matching columns to invoices table (these will be added regardless)
    op.add_column('invoices', sa.Column('matched_status', sa.String(length=20), nullable=False, server_default='NEEDS_REVIEW'))
    op.add_column('invoices', sa.Column('matched_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('invoices', sa.Column('matched_details', sa.JSON(), nullable=True))
    
    # Add check constraint for matched_status
    op.create_check_constraint(
        'ck_matched_status',
        'invoices',
        "matched_status IN ('AUTO_APPROVED', 'NEEDS_REVIEW')"
    )
    
    # Create index for matched_status
    op.create_index('idx_matched_status', 'invoices', ['matched_status'], unique=False)


def downgrade() -> None:
    # Remove matching columns from invoices table
    op.drop_index('idx_matched_status', table_name='invoices')
    op.drop_constraint('ck_matched_status', 'invoices', type_='check')
    op.drop_column('invoices', 'matched_details')
    op.drop_column('invoices', 'matched_at')
    op.drop_column('invoices', 'matched_status')
    
    # Drop purchase_orders table
    op.drop_index('idx_total_amount', table_name='purchase_orders')
    op.drop_index('idx_po_number', table_name='purchase_orders')
    op.drop_table('purchase_orders') 