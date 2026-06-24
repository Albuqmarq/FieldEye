"""
models.py — Modelos ORM do analytics-service.

Este serviço LÊ os resultados que o worker gravou: a tabela `jobs` (para
checar dono/permissão), `player_tracks` (estatísticas agregadas por jogador)
e `frame_data` (série temporal frame a frame).
"""

import uuid

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from database import Base


class Job(Base):
    """Tabela de jobs (usada para validar o dono dos resultados)."""

    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer)
    status = Column(String(20))
    progress = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    output_path = Column(Text)


class PlayerTrack(Base):
    """Estatísticas AGREGADAS por jogador (uma linha por jogador)."""

    __tablename__ = "player_tracks"

    id = Column(Integer, primary_key=True)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"))
    player_id = Column(Integer, nullable=False)
    team = Column(String(20))
    max_speed = Column(Float)
    avg_speed = Column(Float)
    total_distance = Column(Float)
    trajectory = Column(JSONB)
    heatmap_data = Column(JSONB)


class FrameData(Base):
    """Dados FRAME A FRAME (para os gráficos de velocidade no tempo)."""

    __tablename__ = "frame_data"

    id = Column(BigInteger, primary_key=True)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"))
    player_id = Column(Integer, nullable=False)
    frame_number = Column(Integer)
    timestamp = Column(Float)
    x = Column(Float)
    y = Column(Float)
    speed = Column(Float)
