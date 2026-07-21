"""
models.py — Modelo ORM de usuário (auth-service).

Segurança: guardamos apenas o `password_hash` (a senha embaralhada por
bcrypt), NUNCA a senha em texto puro. Se o banco vazar, ninguém recupera as
senhas originais.
"""

from sqlalchemy import Column, DateTime, Integer, String
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
