"""Add review fields to invoices table

Revision ID: 0001
Revises: 
Create Date: 2024-01-11 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add review fields to invoices table
    op.add_column('invoices', sa.Column('reviewed_by', sa.String(255), nullable=True))
    op.add_column('invoices', sa.Column('reviewed_at', sa.DateTime(), nullable=True))
    op.add_column('invoices', sa.Column('review_notes', sa.Text(), nullable=True))
    
    # Add index for faster queries on reviewed status
    op.create_index('idx_invoices_reviewed_by', 'invoices', ['reviewed_by'])
    op.create_index('idx_invoices_matched_status_reviewed', 'invoices', ['matched_status', 'reviewed_by'])


def downgrade() -> None:
    # Remove indexes
    op.drop_index('idx_invoices_matched_status_reviewed', 'invoices')
    op.drop_index('idx_invoices_reviewed_by', 'invoices')
    
    # Remove review fields
    op.drop_column('invoices', 'review_notes')
    op.drop_column('invoices', 'reviewed_at')
    op.drop_column('invoices', 'reviewed_by') 