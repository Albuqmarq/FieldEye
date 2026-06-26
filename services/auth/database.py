"""
database.py — Conexão assíncrona com o PostgreSQL (auth-service).

Mesmo padrão dos outros serviços: cada microserviço tem sua própria conexão.
"""

import os

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

DATABASE_URL = os.getenv(
    "DATABASE_URL_ASYNC",
    "postgresql+asyncpg://fieldeye:fieldeye@postgres:5432/fieldeye",
)

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)
Base = declarative_base()


async def get_db():
    """Entrega uma sessão de banco por requisição (fechada ao final)."""
    async with AsyncSessionLocal() as session:
        yield session
