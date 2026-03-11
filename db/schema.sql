-- CS Betting Helper — Production Schema
-- PostgreSQL 16 + TimescaleDB

-- ── Matches ──
CREATE TABLE IF NOT EXISTS matches (
    id SERIAL PRIMARY KEY,
    external_id VARCHAR(255) UNIQUE NOT NULL,
    sport VARCHAR(50) NOT NULL DEFAULT 'cs2',
    tournament VARCHAR(255),
    team1_name VARCHAR(255) NOT NULL,
    team2_name VARCHAR(255) NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    source VARCHAR(50) NOT NULL DEFAULT 'oddspapi',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_matches_external ON matches(external_id);
CREATE INDEX IF NOT EXISTS idx_matches_start ON matches(start_time);
CREATE INDEX IF NOT EXISTS idx_matches_sport ON matches(sport);

-- ── Odds Snapshots (timeseries) ──
CREATE TABLE IF NOT EXISTS odds_snapshots (
    id SERIAL,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    bookmaker VARCHAR(100) NOT NULL,
    team1_odds DOUBLE PRECISION NOT NULL,
    team2_odds DOUBLE PRECISION NOT NULL,
    map1_team1_odds DOUBLE PRECISION,
    map1_team2_odds DOUBLE PRECISION,
    total_maps_over DOUBLE PRECISION,
    total_maps_under DOUBLE PRECISION,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, timestamp)
);

-- TimescaleDB hypertable
SELECT create_hypertable('odds_snapshots', 'timestamp', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS ix_odds_match_bk_ts ON odds_snapshots(match_id, bookmaker, timestamp);

-- ── Signals (unified: arbitrage, steam, value, suspicious, etc.) ──
CREATE TABLE IF NOT EXISTS signals (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    kind VARCHAR(50) NOT NULL,
    severity VARCHAR(20) DEFAULT 'info',
    title VARCHAR(512) NOT NULL,
    detail TEXT,
    meta_json TEXT,
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    notified BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS ix_signals_kind_detected ON signals(kind, detected_at);
CREATE INDEX IF NOT EXISTS ix_signals_match ON signals(match_id, detected_at DESC);

-- ── Logs ──
CREATE TABLE IF NOT EXISTS logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    level VARCHAR(20),
    source VARCHAR(50),
    message TEXT NOT NULL,
    meta_json TEXT
);

CREATE INDEX IF NOT EXISTS ix_logs_timestamp ON logs(timestamp);

-- ── Helpers ──
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_matches_updated ON matches;
CREATE TRIGGER trg_matches_updated
    BEFORE UPDATE ON matches
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ── Views ──
CREATE OR REPLACE VIEW latest_odds AS
SELECT DISTINCT ON (match_id, bookmaker)
    match_id, bookmaker, team1_odds, team2_odds, timestamp
FROM odds_snapshots
ORDER BY match_id, bookmaker, timestamp DESC;

CREATE OR REPLACE VIEW recent_signals AS
SELECT s.*, m.team1_name, m.team2_name, m.tournament, m.start_time
FROM signals s
JOIN matches m ON s.match_id = m.id
ORDER BY s.detected_at DESC;
