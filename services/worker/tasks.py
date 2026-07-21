"""Task Celery: pega o job da fila, roda o pipeline e grava os resultados."""

import json
import logging
import os
import subprocess
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import Json
from celery import Celery

# Garante o ajuste de OpenMP (Windows/dev) antes de importar o pipeline.
import pipeline  # noqa: F401  (executa pipeline/__init__.py)
from pipeline.runner import processar_video

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("worker.tasks")

# URLs da fila (broker) e do backend de resultados, vindas do ambiente.
BROKER_URL = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://redis:6379/0"))
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")

# Instância do Celery — é isto que o comando `celery -A tasks worker` usa.
app = Celery("fieldeye", broker=BROKER_URL, backend=RESULT_BACKEND)
app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)

# Diretórios de dados (montados como volume no contêiner).
OUTPUTS_DIR = os.getenv("OUTPUTS_DIR", "/data/outputs")


# Pós-processamento de vídeo
def _transcodificar_h264(caminho: str) -> None:
    """Reescreve o vídeo em H.264 (yuv420p) para tocar direto no navegador.

    O OpenCV grava com o codec mp4v (MPEG-4 Part 2), que players como VLC
    reproduzem, mas Chrome/Firefox/Safari NÃO. Convertemos para H.264 com
    `+faststart` (move o índice para o início, permitindo streaming) usando
    o ffmpeg já instalado na imagem do worker.

    Se a conversão falhar por qualquer motivo, mantemos o arquivo original
    (melhor um vídeo que ao menos baixa do que nenhum).
    """
    tmp = f"{caminho}.h264.mp4"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", caminho,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-an",  # sem áudio (o vídeo anotado não tem trilha)
        tmp,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        os.replace(tmp, caminho)
        logger.info("Vídeo %s convertido para H.264 (compatível com navegador).", caminho)
    except Exception as exc:
        logger.warning("Falha ao converter %s para H.264: %s", caminho, exc)
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


# Funções auxiliares de banco de dados
def _conectar():
    """Abre uma conexão com o PostgreSQL usando DATABASE_URL."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL não definida no ambiente.")
    return psycopg2.connect(url)


def _atualizar_job(conn, job_id, **campos):
    """Atualiza colunas do job (status, progress, etc.) de forma segura.

    Args:
        conn: conexão psycopg2.
        job_id: UUID do job.
        **campos: pares coluna=valor a atualizar.
    """
    if not campos:
        return
    colunas = ", ".join(f"{k} = %s" for k in campos)
    valores = list(campos.values()) + [job_id]
    with conn.cursor() as cur:
        cur.execute(f"UPDATE jobs SET {colunas} WHERE id = %s", valores)
    conn.commit()


def _salvar_resultados(conn, job_id, resultado):
    """Salva player_tracks (agregado) e frame_data (granular) no banco.

    Args:
        conn: conexão psycopg2.
        job_id: UUID do job.
        resultado: dict retornado por processar_video.
    """
    with conn.cursor() as cur:
        for p in resultado["players"]:
            # Linha agregada por jogador.
            cur.execute(
                """
                INSERT INTO player_tracks
                    (job_id, player_id, team, max_speed, avg_speed,
                     total_distance, trajectory, heatmap_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    job_id, p["player_id"], p["team"], p["max_speed"],
                    p["avg_speed"], p["total_distance"], Json(p["trajectory"]), None,
                ),
            )
            # Dados frame a frame (para gráficos de velocidade no tempo).
            for ponto in p["trajectory"]:
                cur.execute(
                    """
                    INSERT INTO frame_data
                        (job_id, player_id, frame_number, timestamp, x, y, speed)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        job_id, p["player_id"], ponto["frame"],
                        ponto["frame"] / resultado["fps"], ponto["x"],
                        ponto["y"], ponto["speed"],
                    ),
                )
    conn.commit()


# Task principal
@app.task(bind=True, name="process_video")
def process_video(self, job_id: str, video_path: str, options: dict = None):
    """Processa um vídeo de ponta a ponta e grava os resultados no banco.

    Args:
        job_id: UUID do job (criado pelo video-service).
        video_path: caminho do vídeo de entrada.
        options: ajustes opcionais do pipeline.

    Returns:
        Dicionário com um resumo (nº de jogadores e caminho do vídeo).
    """
    logger.info("Iniciando job %s (vídeo=%s).", job_id, video_path)
    conn = None
    try:
        conn = _conectar()
        _atualizar_job(conn, job_id, status="processing", progress=0)

        # Caminho de saída do vídeo anotado.
        os.makedirs(OUTPUTS_DIR, exist_ok=True)
        output_path = os.path.join(OUTPUTS_DIR, f"{job_id}.mp4")

        # Callback que grava o progresso no banco conforme processa.
        def progress_cb(p):
            try:
                _atualizar_job(conn, job_id, progress=p)
            except Exception:
                logger.warning("Falha ao atualizar progresso do job %s.", job_id)

        # Executa o pipeline (o "motor").
        resultado = processar_video(video_path, output_path, options, progress_cb)

        # Converte o vídeo anotado para H.264 para tocar no navegador.
        _transcodificar_h264(output_path)

        # Persiste os resultados e finaliza o job.
        _salvar_resultados(conn, job_id, resultado)
        _atualizar_job(
            conn, job_id,
            status="done", progress=100,
            completed_at=datetime.now(timezone.utc),
            output_path=output_path,
        )
        logger.info("Job %s concluído (%d jogadores).", job_id, len(resultado["players"]))
        return {"job_id": job_id, "players": len(resultado["players"]), "output": output_path}

    except Exception as exc:
        # Qualquer falha marca o job como "failed" com a mensagem de erro.
        logger.exception("Job %s falhou: %s", job_id, exc)
        if conn is not None:
            try:
                _atualizar_job(conn, job_id, status="failed", error_message=str(exc))
            except Exception:
                logger.error("Não foi possível marcar o job %s como failed.", job_id)
        raise
    finally:
        if conn is not None:
            conn.close()
