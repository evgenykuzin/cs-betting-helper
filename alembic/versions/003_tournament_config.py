"""add tournament_config table

Revision ID: 003
Revises: 001_initial_schema
Create Date: 2026-03-13 13:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '003'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create tournament_configs table
    op.create_table(
        'tournament_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tournament_id', sa.Integer(), nullable=False),
        sa.Column('tournament_name', sa.String(255), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('tier', sa.String(20), nullable=False, server_default='tier2'),
        sa.Column('description', sa.String(512), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_tournament_id', 'tournament_configs', ['tournament_id'], unique=True)
    op.create_index('ix_tournament_enabled', 'tournament_configs', ['enabled'])
    op.create_index('ix_tournament_enabled_tier', 'tournament_configs', ['enabled', 'tier'])


def downgrade() -> None:
    op.drop_index('ix_tournament_enabled_tier', table_name='tournament_configs')
    op.drop_index('ix_tournament_enabled', table_name='tournament_configs')
    op.drop_index('ix_tournament_id', table_name='tournament_configs')
    op.drop_table('tournament_configs')
