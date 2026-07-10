#!/bin/bash
# ============================================================
# start.sh — sobe o FieldEye completo com um comando.
# ============================================================
set -e

# 1) Cria o .env a partir do exemplo, se ainda não existir.
if [ ! -f .env ]; then
  cp .env.example .env
  echo ".env criado a partir de .env.example — revise as senhas antes de produção."
fi

# 2) Garante que as pastas de dados existam (montadas como volume).
mkdir -p data/uploads data/outputs data/models

# 3) Sobe todos os serviços (constrói as imagens na primeira vez).
echo "Subindo o FieldEye... (a primeira build baixa o PyTorch e pode demorar)"
docker compose up --build
