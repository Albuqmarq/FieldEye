"""
models.py — Modelos ORM (mapeamento das TABELAS do banco em classes Python).

ORM = Object-Relational Mapping. Cada classe aqui representa uma TABELA, e
cada instância representa uma LINHA. Em vez de escrever SQL na mão, manipulamos
objetos Python (ex.: job.status = "done") e o SQLAlchemy gera o SQL.

⚠️ Diferença importante (você perguntou isso):
   - models.py  -> como os dados são GUARDADOS no banco (tabelas/colunas).
   - schemas.py -> como os dados ENTRAM e SAEM da API (contrato JSON).
   São separados porque o banco e a API têm necessidades diferentes
   (ex.: a API nunca deve expor o password_hash).
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from database import Base


class User(Base):
    """Tabela de usuários (espelha o init.sql)."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    team_name = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Job(Base):
    """Tabela de jobs (cada análise de vídeo solicitada)."""

    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    status = Column(String(20), nullable=False, default="pending")
    progress = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    video_path = Column(Text)
    output_path = Column(Text)
    error_message = Column(Text)
    options = Column(JSONB)
