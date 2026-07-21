"""
main.py — Auth Service (FastAPI): registro, login e perfil do usuário.

É o serviço que EMITE os tokens JWT que os outros serviços (video, analytics)
validam. Ele é o único que mexe em senha — e guarda só o hash (bcrypt).

Fluxo:
  register -> cria o usuário (senha embaralhada por bcrypt)
  login    -> confere a senha e devolve access (24h) + refresh (7d)
  GET /me  -> dados do usuário do token
  PUT /me  -> atualiza nome do time / senha
"""

import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from schemas import LoginIn, RegisterIn, TokenOut, UserOut, UserUpdate

app = FastAPI(title="FieldEye — Auth Service")

# Configurações
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")
JWT_ALG = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_MIN = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))   # 24h
REFRESH_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))      # 7 dias

# Contexto de hashing de senha (bcrypt). passlib cuida de salt e verificação.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer()


# Funções auxiliares
def _hash_senha(senha: str) -> str:
    """Gera o hash bcrypt da senha (com salt aleatório embutido)."""
    return pwd_context.hash(senha)


def _conferir_senha(senha: str, hash_: str) -> bool:
    """Confere a senha digitada contra o hash guardado."""
    return pwd_context.verify(senha, hash_)


def _criar_token(user_id: int, tipo: str, expira: timedelta) -> str:
    """Cria um JWT assinado com o ID do usuário, tipo e validade.

    Args:
        user_id: ID do usuário (vai no campo 'sub').
        tipo: "access" ou "refresh".
        expira: validade do token.
    """
    agora = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),     # 'subject' = de quem é o token
        "type": tipo,
        "iat": agora,            # emitido em
        "exp": agora + expira,   # expira em
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


async def usuario_atual(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Valida o token e devolve o objeto User correspondente."""
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALG])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Token inválido ou ausente.")

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Usuário não existe mais.")
    return user


# Endpoints
@app.get("/api/auth/health")
async def health():
    """Endpoint de saúde."""
    return {"status": "ok", "service": "auth"}


@app.post("/api/auth/register", response_model=UserOut, status_code=201)
async def register(dados: RegisterIn, db: AsyncSession = Depends(get_db)):
    """Cria uma conta nova (e-mail único, senha embaralhada com bcrypt)."""
    # Verifica se o e-mail já existe.
    existe = await db.execute(select(User).where(User.email == dados.email))
    if existe.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="E-mail já cadastrado.")

    user = User(
        email=dados.email,
        password_hash=_hash_senha(dados.password),
        team_name=dados.team_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@app.post("/api/auth/login", response_model=TokenOut)
async def login(dados: LoginIn, db: AsyncSession = Depends(get_db)):
    """Confere as credenciais e devolve access + refresh tokens."""
    res = await db.execute(select(User).where(User.email == dados.email))
    user = res.scalar_one_or_none()
    # Mesma mensagem para e-mail errado OU senha errada (não dá pistas a atacantes).
    if user is None or not _conferir_senha(dados.password, user.password_hash):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos.")

    return TokenOut(
        access_token=_criar_token(user.id, "access", timedelta(minutes=ACCESS_MIN)),
        refresh_token=_criar_token(user.id, "refresh", timedelta(days=REFRESH_DAYS)),
    )


@app.get("/api/auth/me", response_model=UserOut)
async def perfil(user: User = Depends(usuario_atual)):
    """Devolve os dados do usuário autenticado."""
    return user


@app.put("/api/auth/me", response_model=UserOut)
async def atualizar_perfil(
    dados: UserUpdate,
    user: User = Depends(usuario_atual),
    db: AsyncSession = Depends(get_db),
):
    """Atualiza o perfil (nome do time e/ou senha)."""
    if dados.team_name is not None:
        user.team_name = dados.team_name
    if dados.password:
        user.password_hash = _hash_senha(dados.password)
    await db.commit()
    await db.refresh(user)
    return user
