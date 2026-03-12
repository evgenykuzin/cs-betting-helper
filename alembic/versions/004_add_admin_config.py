"""Add SignalConfig and AdminConfig tables for flexible admin panel."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004_add_admin_config'
down_revision = '003_add_autoincrement_sequences'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SignalConfig table
    op.create_table(
        'signal_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(50), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('send_telegram', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('description', sa.String(512), nullable=True),
        sa.Column('config_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_signal_config_kind_severity', 'signal_configs', ['kind', 'severity'])

    # AdminConfig table
    op.create_table(
        'admin_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(100), nullable=False),
        sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('description', sa.String(512), nullable=True),
        sa.Column('category', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key'),
    )
    op.create_index('ix_admin_config_key', 'admin_configs', ['key'])


def downgrade() -> None:
    op.drop_index('ix_admin_config_key', table_name='admin_configs')
    op.drop_table('admin_configs')
    op.drop_index('ix_signal_config_kind_severity', table_name='signal_configs')
    op.drop_table('signal_configs')
