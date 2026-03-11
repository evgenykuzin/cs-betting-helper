"""Convert meta_json to JSONB, use server-side timestamps

Revision ID: 002
Revises: 001
Create Date: 2026-03-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Convert Text to JSONB for signals.meta_json
    op.execute("ALTER TABLE signals ALTER COLUMN meta_json TYPE jsonb USING meta_json::jsonb")

    # 2. Convert Text to JSONB for logs.meta_json
    op.execute("ALTER TABLE logs ALTER COLUMN meta_json TYPE jsonb USING meta_json::jsonb")

    # 3. Update server defaults for timestamps (use CURRENT_TIMESTAMP)
    op.execute("ALTER TABLE matches ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP")
    op.execute("ALTER TABLE matches ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP")
    op.execute("ALTER TABLE odds_snapshots ALTER COLUMN timestamp SET DEFAULT CURRENT_TIMESTAMP")
    op.execute("ALTER TABLE signals ALTER COLUMN detected_at SET DEFAULT CURRENT_TIMESTAMP")
    op.execute("ALTER TABLE logs ALTER COLUMN timestamp SET DEFAULT CURRENT_TIMESTAMP")

    # 4. Create function for updated_at trigger
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    
    # 5. Drop old trigger if exists (separate command)
    op.execute("DROP TRIGGER IF EXISTS trg_matches_updated ON matches")
    
    # 6. Create new trigger (separate command)
    op.execute("""
        CREATE TRIGGER trg_matches_updated
        BEFORE UPDATE ON matches
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at()
    """)


def downgrade() -> None:
    # Revert JSONB to Text
    op.execute("ALTER TABLE signals ALTER COLUMN meta_json TYPE text USING meta_json::text")
    op.execute("ALTER TABLE logs ALTER COLUMN meta_json TYPE text USING meta_json::text")
    
    # Drop trigger and function
    op.execute("DROP TRIGGER IF EXISTS trg_matches_updated ON matches")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at()")
