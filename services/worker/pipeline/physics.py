"""
physics.py — Cálculos físicos a partir das trajetórias em metros.

Etapa 6 do pipeline. Com as posições dos jogadores já em metros (via
homography.py), calculamos métricas reais: velocidade, aceleração, distância
percorrida, número de sprints e heatmap de ocupação do campo.

Convenções de unidades:
    - posições em METROS (x, y)
    - tempo (dt) em SEGUNDOS
    - velocidade retornada em KM/H
    - aceleração em M/S²
    - distância em METROS
"""

import logging
import math
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Fator de conversão de m/s para km/h.
MS_PARA_KMH = 3.6


def _distancia(pos1: Tuple[float, float], pos2: Tuple[float, float]) -> float:
    """Distância euclidiana entre dois pontos (em metros).

    Args:
        pos1: ponto (x, y) inicial em metros.
        pos2: ponto (x, y) final em metros.

    Returns:
        Distância em metros.
    """
    return math.hypot(pos2[0] - pos1[0], pos2[1] - pos1[1])


def calculate_speed(
    pos1: Tuple[float, float], pos2: Tuple[float, float], dt: float
) -> float:
    """Calcula a velocidade instantânea entre dois pontos.

    Args:
        pos1: posição anterior (x, y) em metros.
        pos2: posição atual (x, y) em metros.
        dt: intervalo de tempo entre as duas posições, em segundos.

    Returns:
        Velocidade em km/h. Retorna 0.0 se dt for inválido.
    """
    if dt is None or dt <= 0:
        # dt inválido: não dá para calcular velocidade.
        logger.warning("calculate_speed recebeu dt inválido (%s).", dt)
        return 0.0

    metros = _distancia(pos1, pos2)
    velocidade_ms = metros / dt
    return velocidade_ms * MS_PARA_KMH


def calculate_acceleration(v1: float, v2: float, dt: float) -> float:
    """Calcula a aceleração entre duas velocidades.

    Args:
        v1: velocidade anterior em km/h.
        v2: velocidade atual em km/h.
        dt: intervalo de tempo em segundos.

    Returns:
        Aceleração em m/s². Retorna 0.0 se dt for inválido.
    """
    if dt is None or dt <= 0:
        logger.warning("calculate_acceleration recebeu dt inválido (%s).", dt)
        return 0.0

    # Convertemos km/h -> m/s antes de derivar no tempo.
    v1_ms = v1 / MS_PARA_KMH
    v2_ms = v2 / MS_PARA_KMH
    return (v2_ms - v1_ms) / dt


def calculate_total_distance(positions: List[Tuple[float, float]]) -> float:
    """Soma a distância percorrida ao longo de uma sequência de posições.

    Args:
        positions: lista de posições (x, y) em metros, em ordem temporal.
            Valores None (gaps de rastreamento) são ignorados.

    Returns:
        Distância total percorrida em metros.
    """
    # Remove posições ausentes (None) antes de somar.
    validas = [p for p in positions if p is not None]
    if len(validas) < 2:
        return 0.0

    total = 0.0
    for anterior, atual in zip(validas[:-1], validas[1:]):
        total += _distancia(anterior, atual)
    return total


def calculate_sprint_count(speeds: List[float], threshold: float = 25.0) -> int:
    """Conta quantos sprints o jogador fez.

    Um sprint é definido como um trecho contínuo em que a velocidade fica
    acima do limiar. Contamos cada CRUZAMENTO de baixo para cima do limiar
    como um novo sprint (evita contar o mesmo sprint várias vezes).

    Args:
        speeds: lista de velocidades instantâneas em km/h.
        threshold: limiar de velocidade para considerar sprint (km/h).

    Returns:
        Número de sprints.
    """
    sprints = 0
    acima_antes = False
    for v in speeds:
        acima_agora = v >= threshold
        # Conta apenas a transição abaixo -> acima (início de um novo sprint).
        if acima_agora and not acima_antes:
            sprints += 1
        acima_antes = acima_agora
    return sprints


def generate_heatmap(
    positions: List[Tuple[float, float]],
    field_size: Tuple[float, float] = (105.0, 68.0),
    bins: Tuple[int, int] = (105, 68),
    sigma: float = 2.0,
) -> np.ndarray:
    """Gera um heatmap de densidade de posições no campo.

    Args:
        positions: lista de posições (x, y) em metros (None é ignorado).
        field_size: dimensões do campo em metros (comprimento, largura).
        bins: resolução do heatmap (células em x, células em y).
        sigma: desvio do borramento gaussiano (suaviza o mapa).

    Returns:
        Matriz numpy (bins_y x bins_x) com a densidade normalizada (0..1).
    """
    largura_m, altura_m = field_size
    nx, ny = bins

    # Matriz de contagem (linhas = y, colunas = x), padrão de imagem.
    heatmap = np.zeros((ny, nx), dtype=np.float32)

    validas = [p for p in positions if p is not None]
    if not validas:
        logger.warning("generate_heatmap recebeu lista vazia de posições.")
        return heatmap

    for x, y in validas:
        # Converte metros -> índice de célula, limitando às bordas do campo.
        ix = int(np.clip(x / largura_m * (nx - 1), 0, nx - 1))
        iy = int(np.clip(y / altura_m * (ny - 1), 0, ny - 1))
        heatmap[iy, ix] += 1.0

    # Borramento gaussiano para suavizar (opcional, melhora a visualização).
    if sigma > 0:
        try:
            import cv2

            ksize = int(sigma * 4) | 1  # tamanho ímpar do kernel
            heatmap = cv2.GaussianBlur(heatmap, (ksize, ksize), sigma)
        except Exception as exc:
            # Se o blur falhar, seguimos com o heatmap "cru".
            logger.warning("Falha ao aplicar blur no heatmap: %s", exc)

    # Normaliza para 0..1 (facilita renderização posterior).
    maximo = heatmap.max()
    if maximo > 0:
        heatmap = heatmap / maximo
    return heatmap
