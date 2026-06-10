"""
Pacote `pipeline` — módulos do worker de visão computacional.

Cada submódulo cobre uma etapa do pipeline de IA:
    detector        -> detecção (YOLOv8)
    team_classifier -> classificação de time (K-means)
    tracker         -> rastreamento (BoT-SORT + ReID)
    homography      -> conversão pixel -> metros   (Fase 4)
    physics         -> velocidade/distância/heatmap (Fase 4)
    interpolation   -> preenchimento de gaps        (Fase 5)
    video_writer    -> vídeo anotado                (Fase 5)
"""

import os

# Workaround para ambiente de desenvolvimento local em Windows/Anaconda:
# PyTorch e o runtime OpenMP da Anaconda podem carregar duas cópias da
# libiomp5md.dll, causando "OMP: Error #15". Definir esta variável ANTES de
# importar torch evita o crash. Em produção (Docker/Linux) o conflito não
# existe, então isto é inofensivo lá. Só definimos se ainda não estiver setada.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
