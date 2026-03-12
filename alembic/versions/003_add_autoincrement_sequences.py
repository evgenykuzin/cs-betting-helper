"""003: Add AUTOINCREMENT sequences to id columns

Revision ID: 003
Revises: 002
Create Date: 2026-03-12 00:10:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create sequences if they don't exist
    op.execute("CREATE SEQUENCE IF NOT EXISTS odds_snapshots_id_seq")
    op.execute("CREATE SEQUENCE IF NOT EXISTS signals_id_seq")
    op.execute("CREATE SEQUENCE IF NOT EXISTS logs_id_seq")
    
    # Set owned by (link sequence to column)
    op.execute("ALTER SEQUENCE odds_snapshots_id_seq OWNED BY odds_snapshots.id")
    op.execute("ALTER SEQUENCE signals_id_seq OWNED BY signals.id")
    op.execute("ALTER SEQUENCE logs_id_seq OWNED BY logs.id")
    
    # Set default values to nextval()
    op.execute("ALTER TABLE odds_snapshots ALTER COLUMN id SET DEFAULT nextval('odds_snapshots_id_seq')")
    op.execute("ALTER TABLE signals ALTER COLUMN id SET DEFAULT nextval('signals_id_seq')")
    op.execute("ALTER TABLE logs ALTER COLUMN id SET DEFAULT nextval('logs_id_seq')")


def downgrade() -> None:
    # Drop defaults
    op.execute("ALTER TABLE odds_snapshots ALTER COLUMN id DROP DEFAULT")
    op.execute("ALTER TABLE signals ALTER COLUMN id DROP DEFAULT")
    op.execute("ALTER TABLE logs ALTER COLUMN id DROP DEFAULT")
    
    # Drop sequences
    op.execute("DROP SEQUENCE IF EXISTS odds_snapshots_id_seq")
    op.execute("DROP SEQUENCE IF EXISTS signals_id_seq")
    op.execute("DROP SEQUENCE IF EXISTS logs_id_seq")
