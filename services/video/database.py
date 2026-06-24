"""
database.py — Conexão assíncrona com o PostgreSQL (SQLAlchemy async).

"Assíncrono" significa que, enquanto uma consulta ao banco está em andamento,
o servidor pode atender OUTRAS requisições em vez de ficar parado esperando.
Isso deixa a API muito mais escalável (atende mais usuários ao mesmo tempo).

Usamos o driver `asyncpg` (rápido e assíncrono) via SQLAlchemy.
"""

import os

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

# URL assíncrona do banco (postgresql+asyncpg://...). Vem do .env.
DATABASE_URL = os.getenv(
    "DATABASE_URL_ASYNC",
    "postgresql+asyncpg://fieldeye:fieldeye@postgres:5432/fieldeye",
)

# O "engine" é o gerenciador de conexões com o banco.
engine = create_async_engine(DATABASE_URL, echo=False, future=True)

# "Fábrica" de sessões: cada requisição abre uma sessão para falar com o banco.
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# Base da qual os modelos ORM (models.py) herdam.
Base = declarative_base()


async def get_db():
    """Dependência do FastAPI: entrega uma sessão de banco por requisição.

    O `async with` garante que a sessão é fechada ao fim da requisição,
    mesmo se der erro (evita vazamento de conexões).
    """
    async with AsyncSessionLocal() as session:
        yield session
