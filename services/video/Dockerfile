# Dockerfile do video-service (FastAPI).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Instala dependências primeiro (aproveita cache de build).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código do serviço.
COPY . .

# Sobe a API com uvicorn na porta 8000 (a mesma referida no docker-compose).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
