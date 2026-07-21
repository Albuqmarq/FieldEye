"""
main.py — Video Service (FastAPI): upload de vídeos e gestão de jobs.

Responsabilidades:
  - receber o upload, validar e salvar o arquivo;
  - criar o job no banco;
  - ENFILEIRAR o processamento no Celery (o worker pega depois);
  - listar/consultar/deletar jobs do usuário autenticado.

Comunicação com o worker: usamos `celery_app.send_task("process_video", ...)`.
Repare que o video-service NÃO importa o código do worker — ele só manda uma
"mensagem" pela fila (Redis) dizendo "processem este job". Isso DESACOPLA os
serviços: cada um evolui independente, contanto que respeitem o nome da task.
"""

import json
import os
import uuid

from celery import Celery
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Job
from schemas import JobOut, UploadResponse

app = FastAPI(title="FieldEye — Video Service")

# --- Configurações de ambiente ---
UPLOADS_DIR = os.getenv("UPLOADS_DIR", "/data/uploads")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")
JWT_ALG = os.getenv("JWT_ALGORITHM", "HS256")
EXTENSOES_OK = {".mp4", ".avi", ".mov", ".mkv"}

# Cliente Celery (só para ENVIAR tarefas; o worker é quem executa).
celery_app = Celery(
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1"),
)

# Esquema de autenticação: espera um header "Authorization: Bearer <token>".
bearer = HTTPBearer()


async def usuario_atual(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> int:
    """Valida o JWT e devolve o ID do usuário (campo 'sub' do token).

    Cada serviço valida o token SOZINHO (com o JWT_SECRET compartilhado), sem
    precisar chamar o auth-service a cada requisição. Isso é o poder do JWT:
    autenticação 'stateless' (sem estado), rápida e escalável.
    """
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALG])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido ou ausente."
        )


@app.get("/api/videos/health")
async def health():
    """Endpoint simples de saúde (para healthcheck/monitoramento)."""
    return {"status": "ok", "service": "video"}


@app.post("/api/videos/upload", response_model=UploadResponse)
async def upload_video(
    file: UploadFile = File(...),
    mode: str = Form("velocidade"),        # "velocidade" (rápido) ou "qualidade"
    area: str = Form("regiao"),            # "regiao" (marcar no vídeo) ou "oficial"
    field_type: str = Form(None),          # "futebol" | "futsal" | "society" (campo oficial)
    device: str = Form(None),              # "gpu" | "cpu" (dispositivo de inferência)
    field_points: str = Form(None),        # JSON: [[x,y],...] 4 cantos do campo (px)
    user_id: int = Depends(usuario_atual),
    db: AsyncSession = Depends(get_db),
):
    """Recebe um vídeo, cria o job e o envia para a fila de processamento.

    As opções `mode` e `area` são escolhidas pelo usuário no painel antes de
    clicar em "Executar" e seguem para o worker via fila (options).
    """
    # 1) Valida a extensão do arquivo.
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in EXTENSOES_OK:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Extensão {ext} não suportada. Use: {', '.join(EXTENSOES_OK)}",
        )

    # 2) Salva o arquivo com um nome único (evita colisão de nomes).
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    nome_unico = f"{uuid.uuid4()}{ext}"
    caminho = os.path.join(UPLOADS_DIR, nome_unico)
    try:
        conteudo = await file.read()
        with open(caminho, "wb") as f:
            f.write(conteudo)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Falha ao salvar o vídeo: {exc}")

    # 3) Metadados/opções. Guardamos mode/area/filename NO job (para o
    #    histórico do perfil); os pontos do campo vão apenas para o worker.
    meta = {"mode": mode, "area": area, "filename": file.filename}
    if area == "oficial" and field_type:
        meta["field_type"] = field_type
    if device:
        meta["device"] = device
    opcoes_task = dict(meta)
    if field_points:
        try:
            pts = json.loads(field_points)
            if isinstance(pts, list) and len(pts) == 4:
                opcoes_task["field_points"] = pts
        except (json.JSONDecodeError, TypeError):
            pass  # marcação inválida é ignorada (cai no fallback)

    # 4) Cria o job no banco (status inicial 'pending').
    job = Job(user_id=user_id, status="pending", progress=0, video_path=caminho, options=meta)
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # 5) Enfileira o processamento (o worker pega esta mensagem no Redis).
    celery_app.send_task("process_video", args=[str(job.id), caminho, opcoes_task])

    return UploadResponse(
        job_id=job.id, status=job.status, message="Vídeo recebido e na fila de processamento."
    )


@app.get("/api/videos/jobs", response_model=list[JobOut])
async def listar_jobs(
    user_id: int = Depends(usuario_atual),
    db: AsyncSession = Depends(get_db),
):
    """Lista todos os jobs do usuário autenticado (mais recentes primeiro)."""
    resultado = await db.execute(
        select(Job).where(Job.user_id == user_id).order_by(Job.created_at.desc())
    )
    return resultado.scalars().all()


@app.get("/api/videos/jobs/{job_id}", response_model=JobOut)
async def consultar_job(
    job_id: uuid.UUID,
    user_id: int = Depends(usuario_atual),
    db: AsyncSession = Depends(get_db),
):
    """Consulta o status/progresso de um job (apenas o dono pode ver)."""
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    if job.user_id != user_id:
        # 403 = autenticado, mas sem permissão para ESTE recurso.
        raise HTTPException(status_code=403, detail="Este job não é seu.")
    return job


@app.delete("/api/videos/jobs/{job_id}")
async def deletar_job(
    job_id: uuid.UUID,
    user_id: int = Depends(usuario_atual),
    db: AsyncSession = Depends(get_db),
):
    """Cancela/deleta um job (apenas o dono). Remove também os resultados (cascade)."""
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    if job.user_id != user_id:
        raise HTTPException(status_code=403, detail="Este job não é seu.")

    # Remove o arquivo de vídeo de entrada, se existir.
    if job.video_path and os.path.exists(job.video_path):
        try:
            os.remove(job.video_path)
        except OSError:
            pass  # falha ao apagar arquivo não impede a remoção do registro

    await db.execute(delete(Job).where(Job.id == job_id))
    await db.commit()
    return {"deleted": str(job_id)}
