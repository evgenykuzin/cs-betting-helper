"""
Pydantic v2 response schemas for FastAPI.
"""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict


class MatchResponse(BaseModel):
    """Match model for API responses."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    external_id: str
    sport: str
    tournament: Optional[str]
    team1_name: str
    team2_name: str
    start_time: datetime
    source: str
    created_at: datetime
    updated_at: datetime


class OddsSnapshotResponse(BaseModel):
    """Odds snapshot for API responses."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    match_id: int
    bookmaker: str
    team1_odds: float
    team2_odds: float
    map1_team1_odds: Optional[float] = None
    map1_team2_odds: Optional[float] = None
    total_maps_over: Optional[float] = None
    total_maps_under: Optional[float] = None
    timestamp: datetime


class SignalResponse(BaseModel):
    """Signal for API responses."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    match_id: int
    kind: str
    severity: str
    title: str
    detail: Optional[str] = None
    meta_json: Optional[dict] = None
    detected_at: datetime
    notified: bool


class LogResponse(BaseModel):
    """Log entry for API responses."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    timestamp: datetime
    level: str
    source: str
    message: str
    meta_json: Optional[dict] = None


class OddsComparisonResponse(BaseModel):
    """Odds comparison analysis."""
    team1_odds: dict[str, float]
    team2_odds: dict[str, float]
    best_team1: dict[str, Any]
    best_team2: dict[str, Any]
    market_avg_team1: float
    market_avg_team2: float
    spread_team1: float
    spread_team2: float
    bookmaker_count: int


# ─────────────────────────────────────────────────────────
# Admin Schemas
# ─────────────────────────────────────────────────────────

class SignalConfigResponse(BaseModel):
    id: int
    kind: str
    severity: str
    enabled: bool
    send_telegram: bool
    description: Optional[str] = None
    config_json: Optional[Any] = None

    class Config:
        from_attributes = True


class SignalConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    send_telegram: Optional[bool] = None
    description: Optional[str] = None
    config_json: Optional[dict] = None


class AdminConfigResponse(BaseModel):
    id: int
    key: str
    value: Any
    category: Optional[str]
    description: Optional[str]

    class Config:
        from_attributes = True


class AdminConfigUpdate(BaseModel):
    value: Any
    category: Optional[str] = None
    description: Optional[str] = None


class AdminConfigCreate(BaseModel):
    value: Any
    category: Optional[str] = "general"
    description: Optional[str] = None


