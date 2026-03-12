"""Initial schema: matches, odds_snapshots, signals, logs, configs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Matches table
    op.create_table(
        'matches',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('external_id', sa.String(255), nullable=False, unique=True),
        sa.Column('sport', sa.String(50), nullable=False, server_default='cs2'),
        sa.Column('tournament', sa.String(255), nullable=True),
        sa.Column('team1_name', sa.String(255), nullable=False),
        sa.Column('team2_name', sa.String(255), nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source', sa.String(50), nullable=False, server_default='oddspapi'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_matches_external_id', 'matches', ['external_id'])
    op.create_index('ix_matches_start_time', 'matches', ['start_time'])

    # OddsSnapshot table
    op.create_table(
        'odds_snapshots',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('match_id', sa.Integer(), nullable=False),
        sa.Column('bookmaker', sa.String(100), nullable=False),
        sa.Column('team1_odds', sa.Float(), nullable=False),
        sa.Column('team2_odds', sa.Float(), nullable=False),
        sa.Column('map1_team1_odds', sa.Float(), nullable=True),
        sa.Column('map1_team2_odds', sa.Float(), nullable=True),
        sa.Column('total_maps_over', sa.Float(), nullable=True),
        sa.Column('total_maps_under', sa.Float(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['match_id'], ['matches.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_odds_match_bk_ts', 'odds_snapshots', ['match_id', 'bookmaker', 'timestamp'])
    op.create_index('ix_odds_timestamp', 'odds_snapshots', ['timestamp'])

    # Signal table
    op.create_table(
        'signals',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('match_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(50), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False, server_default='info'),
        sa.Column('title', sa.String(512), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('meta_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('notified', sa.Boolean(), nullable=False, server_default='false'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['match_id'], ['matches.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_signals_kind', 'signals', ['kind'])
    op.create_index('ix_signals_kind_detected', 'signals', ['kind', 'detected_at'])
    op.create_index('ix_signals_detected', 'signals', ['detected_at'])

    # Log table
    op.create_table(
        'logs',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('level', sa.String(20), nullable=False),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('meta_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_logs_timestamp_level', 'logs', ['timestamp', 'level'])

    # SignalConfig table
    op.create_table(
        'signal_configs',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
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
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('key', sa.String(100), nullable=False, unique=True),
        sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('description', sa.String(512), nullable=True),
        sa.Column('category', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_admin_config_key', 'admin_configs', ['key'])


def downgrade() -> None:
    op.drop_index('ix_admin_config_key', table_name='admin_configs')
    op.drop_table('admin_configs')
    op.drop_index('ix_signal_config_kind_severity', table_name='signal_configs')
    op.drop_table('signal_configs')
    op.drop_index('ix_logs_timestamp_level', table_name='logs')
    op.drop_table('logs')
    op.drop_index('ix_signals_detected', table_name='signals')
    op.drop_index('ix_signals_kind_detected', table_name='signals')
    op.drop_index('ix_signals_kind', table_name='signals')
    op.drop_table('signals')
    op.drop_index('ix_odds_timestamp', table_name='odds_snapshots')
    op.drop_index('ix_odds_match_bk_ts', table_name='odds_snapshots')
    op.drop_table('odds_snapshots')
    op.drop_index('ix_matches_start_time', table_name='matches')
    op.drop_index('ix_matches_external_id', table_name='matches')
    op.drop_table('matches')
