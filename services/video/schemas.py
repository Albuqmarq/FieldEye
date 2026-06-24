"""
schemas.py — Modelos Pydantic (o CONTRATO da API: o que entra e o que sai).

Enquanto models.py descreve o banco, os schemas descrevem o JSON que a API
recebe e devolve. O Pydantic VALIDA automaticamente os dados (ex.: rejeita um
progress que não seja inteiro) e gera a documentação automática do FastAPI.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


class JobOut(BaseModel):
    """Formato de um job devolvido pela API (note: SEM dados internos sensíveis)."""

    id: UUID
    status: str
    progress: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    output_path: Optional[str] = None
    error_message: Optional[str] = None
    options: Optional[Any] = None

    class Config:
        # Permite criar o schema diretamente de um objeto ORM (model).
        from_attributes = True


class UploadResponse(BaseModel):
    """Resposta do upload: confirma que o job foi criado e enfileirado."""

    job_id: UUID
    status: str
    message: str
