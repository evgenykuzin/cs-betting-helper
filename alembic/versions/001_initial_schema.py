"""Initial schema: matches, odds_snapshots, signals, logs

Revision ID: 001
Revises: 
Create Date: 2026-03-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create matches table
    op.create_table(
        'matches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('external_id', sa.String(255), nullable=False),
        sa.Column('sport', sa.String(50), nullable=False, server_default='cs2'),
        sa.Column('tournament', sa.String(255), nullable=True),
        sa.Column('team1_name', sa.String(255), nullable=False),
        sa.Column('team2_name', sa.String(255), nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source', sa.String(50), nullable=False, server_default='oddspapi'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('external_id'),
    )
    op.create_index('ix_matches_external', 'matches', ['external_id'])
    op.create_index('ix_matches_start', 'matches', ['start_time'])
    op.create_index('ix_matches_sport', 'matches', ['sport'])

    # Create odds_snapshots table (with hypertable later)
    op.create_table(
        'odds_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('match_id', sa.Integer(), nullable=False),
        sa.Column('bookmaker', sa.String(100), nullable=False),
        sa.Column('team1_odds', sa.Float(), nullable=False),
        sa.Column('team2_odds', sa.Float(), nullable=False),
        sa.Column('map1_team1_odds', sa.Float(), nullable=True),
        sa.Column('map1_team2_odds', sa.Float(), nullable=True),
        sa.Column('total_maps_over', sa.Float(), nullable=True),
        sa.Column('total_maps_under', sa.Float(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['match_id'], ['matches.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', 'timestamp'),
    )
    op.create_index('ix_odds_match_bk_ts', 'odds_snapshots', ['match_id', 'bookmaker', 'timestamp'])

    # Create signals table
    op.create_table(
        'signals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('match_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(50), nullable=False),
        sa.Column('severity', sa.String(20), nullable=True, server_default='info'),
        sa.Column('title', sa.String(512), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('meta_json', sa.Text(), nullable=True),
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notified', sa.Boolean(), nullable=True, server_default='false'),
        sa.ForeignKeyConstraint(['match_id'], ['matches.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_signals_kind_detected', 'signals', ['kind', 'detected_at'])
    op.create_index('ix_signals_match', 'signals', ['match_id', 'detected_at'])

    # Create logs table
    op.create_table(
        'logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('level', sa.String(20), nullable=True),
        sa.Column('source', sa.String(50), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('meta_json', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_logs_timestamp', 'logs', ['timestamp'])


def downgrade() -> None:
    op.drop_index('ix_logs_timestamp')
    op.drop_table('logs')
    op.drop_index('ix_signals_match')
    op.drop_index('ix_signals_kind_detected')
    op.drop_table('signals')
    op.drop_index('ix_odds_match_bk_ts')
    op.drop_table('odds_snapshots')
    op.drop_index('ix_matches_sport')
    op.drop_index('ix_matches_start')
    op.drop_index('ix_matches_external')
    op.drop_table('matches')
