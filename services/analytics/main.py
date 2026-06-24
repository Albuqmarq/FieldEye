"""
main.py — Analytics Service (FastAPI): entrega os resultados das análises.

Este serviço é de LEITURA: ele consulta o que o worker gravou no banco e
serve para o frontend (cards de jogador, gráficos, heatmap) e exportações
(CSV e PDF).

Como o video-service, valida o JWT sozinho e checa se o job pertence ao
usuário antes de devolver qualquer dado.
"""

import csv
import io
import os

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import FrameData, Job, PlayerTrack
from schemas import AnalyticsResult, PlayerStats, PlayerTimeline, TimelinePoint

app = FastAPI(title="FieldEye — Analytics Service")

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")
JWT_ALG = os.getenv("JWT_ALGORITHM", "HS256")
bearer = HTTPBearer()


async def usuario_atual(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> int:
    """Valida o JWT e devolve o ID do usuário."""
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALG])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Token inválido ou ausente.")


async def _job_do_usuario(job_id, user_id: int, db: AsyncSession) -> Job:
    """Busca o job e garante que ele pertence ao usuário (senão 404/403)."""
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    if job.user_id != user_id:
        raise HTTPException(status_code=403, detail="Este job não é seu.")
    return job


async def _players_do_job(job_id, db: AsyncSession):
    """Retorna as linhas de player_tracks de um job."""
    res = await db.execute(
        select(PlayerTrack).where(PlayerTrack.job_id == job_id).order_by(
            PlayerTrack.total_distance.desc()
        )
    )
    return res.scalars().all()


@app.get("/api/analytics/health")
async def health():
    """Endpoint de saúde."""
    return {"status": "ok", "service": "analytics"}


@app.get("/api/analytics/{job_id}", response_model=AnalyticsResult)
async def resultado_completo(
    job_id: str, user_id: int = Depends(usuario_atual), db: AsyncSession = Depends(get_db)
):
    """Resultado completo: resumo do job + estatísticas de cada jogador."""
    job = await _job_do_usuario(job_id, user_id, db)
    players = await _players_do_job(job_id, db)
    return AnalyticsResult(
        job_id=str(job.id),
        status=job.status,
        players=[PlayerStats.model_validate(p) for p in players],
    )


@app.get("/api/analytics/{job_id}/players", response_model=list[PlayerStats])
async def stats_por_jogador(
    job_id: str, user_id: int = Depends(usuario_atual), db: AsyncSession = Depends(get_db)
):
    """Lista as estatísticas agregadas de cada jogador."""
    await _job_do_usuario(job_id, user_id, db)
    return await _players_do_job(job_id, db)


@app.get("/api/analytics/{job_id}/heatmap/{player_id}")
async def heatmap_jogador(
    job_id: str,
    player_id: int,
    user_id: int = Depends(usuario_atual),
    db: AsyncSession = Depends(get_db),
):
    """Devolve as posições (x, y) de um jogador para o frontend desenhar o heatmap."""
    await _job_do_usuario(job_id, user_id, db)
    res = await db.execute(
        select(PlayerTrack).where(
            PlayerTrack.job_id == job_id, PlayerTrack.player_id == player_id
        )
    )
    pt = res.scalar_one_or_none()
    if pt is None:
        raise HTTPException(status_code=404, detail="Jogador não encontrado neste job.")
    # A trajetória (lista de {frame,x,y,speed}) é a base do heatmap.
    posicoes = [{"x": p["x"], "y": p["y"]} for p in (pt.trajectory or [])]
    return {"player_id": player_id, "positions": posicoes}


@app.get("/api/analytics/{job_id}/timeline", response_model=list[PlayerTimeline])
async def timeline(
    job_id: str, user_id: int = Depends(usuario_atual), db: AsyncSession = Depends(get_db)
):
    """Série temporal de velocidade de cada jogador (para o gráfico no tempo)."""
    await _job_do_usuario(job_id, user_id, db)
    res = await db.execute(
        select(FrameData)
        .where(FrameData.job_id == job_id)
        .order_by(FrameData.player_id, FrameData.frame_number)
    )
    linhas = res.scalars().all()

    # Agrupa os pontos por jogador.
    por_jogador: dict[int, list] = {}
    for fd in linhas:
        por_jogador.setdefault(fd.player_id, []).append(
            TimelinePoint(frame=fd.frame_number, timestamp=fd.timestamp, speed=fd.speed)
        )
    return [PlayerTimeline(player_id=pid, points=pts) for pid, pts in por_jogador.items()]


@app.get("/api/analytics/{job_id}/export/csv")
async def export_csv(
    job_id: str, user_id: int = Depends(usuario_atual), db: AsyncSession = Depends(get_db)
):
    """Exporta as estatísticas dos jogadores em CSV (download)."""
    await _job_do_usuario(job_id, user_id, db)
    players = await _players_do_job(job_id, db)

    # Monta o CSV em memória.
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["player_id", "team", "total_distance_m", "max_speed_kmh", "avg_speed_kmh"])
    for p in players:
        writer.writerow([p.player_id, p.team, p.total_distance, p.max_speed, p.avg_speed])
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=fieldeye_{job_id}.csv"},
    )


@app.get("/api/analytics/{job_id}/export/pdf")
async def export_pdf(
    job_id: str, user_id: int = Depends(usuario_atual), db: AsyncSession = Depends(get_db)
):
    """Exporta um relatório PDF simples com as estatísticas dos jogadores."""
    await _job_do_usuario(job_id, user_id, db)
    players = await _players_do_job(job_id, db)

    # Geração do PDF com reportlab (importado aqui para não pesar o startup).
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    estilos = getSampleStyleSheet()
    elementos = [Paragraph(f"FieldEye — Relatório do job {job_id}", estilos["Title"])]

    dados = [["Jogador", "Time", "Distância (m)", "Vel. máx (km/h)", "Vel. méd (km/h)"]]
    for p in players:
        dados.append([p.player_id, p.team, p.total_distance, p.max_speed, p.avg_speed])

    tabela = Table(dados)
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f77b4")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    elementos.append(tabela)
    doc.build(elementos)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=fieldeye_{job_id}.pdf"},
    )
