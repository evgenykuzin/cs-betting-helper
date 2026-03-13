"""add authorized_users table for telegram alerts

Revision ID: 004
Revises: 003
Create Date: 2026-03-13 16:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create authorized_users table
    op.create_table(
        'authorized_users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('telegram_id', sa.BigInteger(), nullable=False, unique=True),
        sa.Column('username', sa.String(255), nullable=True),
        sa.Column('first_name', sa.String(255), nullable=True),
        sa.Column('language', sa.String(10), nullable=False, server_default='en'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('receive_alerts', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_authorized_users_telegram_id', 'authorized_users', ['telegram_id'])
    op.create_index('ix_authorized_users_enabled', 'authorized_users', ['enabled'])
    op.create_index('ix_authorized_users_receive_alerts', 'authorized_users', ['receive_alerts'])


def downgrade() -> None:
    """
    ⚠️  DOWNGRADE IS DISABLED FOR PRODUCTION SAFETY ⚠️
    """
    raise RuntimeError(
        "Downgrade is disabled for safety. "
        "This would delete authorized_users table. "
        "If you need to downgrade, contact the DBA and manually remove this protection."
    )
