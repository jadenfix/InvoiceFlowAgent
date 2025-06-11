"""Add notifications table

Revision ID: 001_add_notifications_table
Revises: 
Create Date: 2024-01-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_add_notifications_table'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create notifications table"""
    op.create_table(
        'notifications',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('invoice_id', sa.UUID(), nullable=False),
        sa.Column('method', sa.Text(), nullable=False),
        sa.Column('recipient', sa.Text(), nullable=False),
        sa.Column('sent_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.CheckConstraint("method IN ('email','sms')", name='check_method'),
        sa.CheckConstraint("status IN ('SENT','FAILED')", name='check_status'),
        sa.UniqueConstraint('invoice_id', 'method', 'recipient', name='unique_notification')
    )


def downgrade() -> None:
    """Drop notifications table"""
    op.drop_table('notifications') 