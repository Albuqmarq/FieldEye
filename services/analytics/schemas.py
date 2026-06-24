"""
schemas.py — Contratos de saída do analytics-service (JSON da API).
"""

from typing import Any, List, Optional

from pydantic import BaseModel


class PlayerStats(BaseModel):
    """Estatísticas de um jogador (card do dashboard)."""

    player_id: int
    team: Optional[str] = None
    max_speed: Optional[float] = None
    avg_speed: Optional[float] = None
    total_distance: Optional[float] = None

    class Config:
        from_attributes = True


class AnalyticsResult(BaseModel):
    """Resultado completo de um job (resumo + lista de jogadores)."""

    job_id: str
    status: str
    players: List[PlayerStats]


class TimelinePoint(BaseModel):
    """Um ponto da série temporal de velocidade."""

    frame: int
    timestamp: Optional[float] = None
    speed: Optional[float] = None


class PlayerTimeline(BaseModel):
    """Série temporal de velocidade de um jogador."""

    player_id: int
    points: List[TimelinePoint]
