# Dockerfile do worker (Celery + YOLOv8 + OpenCV headless).
# Cada linha vira uma "camada" da imagem; ordená-las bem aproveita o cache.

FROM python:3.11-slim

# Evita buffer nos logs (saída aparece em tempo real) e arquivos .pyc.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Dependências de sistema que o OpenCV/ffmpeg precisam mesmo na versão headless.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala as dependências ANTES de copiar o código: assim, se só o código
# mudar, o Docker reaproveita a camada de dependências (build mais rápido).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código do worker (pipeline/, tasks.py, etc.).
COPY . .

# Sobe o worker Celery, que fica escutando a fila do Redis.
# concurrency=1: processa 1 vídeo por vez por contêiner (vídeo é pesado).
CMD ["celery", "-A", "tasks", "worker", "--loglevel=info", "--concurrency=1"]
