"""
schemas.py — Contratos da API de autenticação (entrada e saída).

Note como o `UserOut` NÃO inclui o password_hash: a senha (mesmo embaralhada)
nunca sai da API. Isso é o `schemas.py` protegendo o que o cliente vê.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class RegisterIn(BaseModel):
    """Dados para criar uma conta."""

    email: EmailStr            # o Pydantic valida que é um e-mail válido
    password: str
    team_name: Optional[str] = None


class LoginIn(BaseModel):
    """Dados para login."""

    email: EmailStr
    password: str


class TokenOut(BaseModel):
    """Tokens devolvidos no login."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    """Dados públicos do usuário (sem senha)."""

    id: int
    email: EmailStr
    team_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    """Campos atualizáveis do perfil (todos opcionais)."""

    team_name: Optional[str] = None
    password: Optional[str] = None
