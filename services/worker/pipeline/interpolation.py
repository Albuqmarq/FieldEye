"""
interpolation.py — Preenchimento de falhas (gaps) de rastreamento.

Etapa 7 do pipeline. O rastreamento às vezes "perde" um jogador por alguns
frames (ele passa atrás de outro, o detector falha momentaneamente, etc.).
Isso cria buracos (gaps) na trajetória — frames sem posição.

Para gaps CURTOS (jogador sumiu por pouco tempo), preenchemos por
interpolação linear: estimamos as posições intermediárias em linha reta entre
a última e a próxima posição conhecida. Para gaps LONGOS (o jogador realmente
saiu do campo/quadro), mantemos None, pois "chutar" a posição seria impreciso.
"""

import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Tipo de uma posição: (x, y) em metros, ou None quando ausente naquele frame.
Posicao = Optional[Tuple[float, float]]


def interpolate_gaps(
    trajectory: List[Posicao], max_gap: int = 45
) -> List[Posicao]:
    """Preenche gaps curtos de uma trajetória por interpolação linear.

    Args:
        trajectory: lista indexada por frame; cada item é (x, y) em metros
            ou None quando o jogador não foi rastreado naquele frame.
        max_gap: tamanho máximo de gap (em frames) que ainda preenchemos.
            Gaps maiores que isso ficam como None (jogador saiu de fato).

    Returns:
        Nova lista de mesmo tamanho com os gaps curtos preenchidos.
    """
    n = len(trajectory)
    # Cópia para não modificar a lista original (função pura).
    resultado: List[Posicao] = list(trajectory)

    # Índice da última posição conhecida (antes do gap atual).
    ultimo_valido = None

    for i in range(n):
        if trajectory[i] is not None:
            # Encontramos uma posição válida. Se havia um gap antes dela,
            # decidimos se interpolamos.
            if ultimo_valido is not None and i - ultimo_valido > 1:
                tamanho_gap = i - ultimo_valido - 1
                if tamanho_gap <= max_gap:
                    _preencher_linear(resultado, ultimo_valido, i)
                else:
                    # Gap grande: mantemos None e registramos.
                    logger.info(
                        "Gap longo de %d frames (frames %d..%d) mantido como None "
                        "(jogador provavelmente saiu do campo).",
                        tamanho_gap,
                        ultimo_valido + 1,
                        i - 1,
                    )
            ultimo_valido = i

    return resultado


def _preencher_linear(
    trajetoria: List[Posicao], inicio: int, fim: int
) -> None:
    """Preenche, in-place, as posições entre os índices `inicio` e `fim`.

    Interpola linearmente entre a posição conhecida em `inicio` e a em `fim`.

    Args:
        trajetoria: lista de posições sendo preenchida (modificada in-place).
        inicio: índice da última posição válida antes do gap.
        fim: índice da próxima posição válida depois do gap.
    """
    x0, y0 = trajetoria[inicio]
    x1, y1 = trajetoria[fim]
    passos = fim - inicio  # número de intervalos

    for k in range(1, passos):
        # Fração do caminho percorrido (0..1) entre inicio e fim.
        t = k / passos
        x = x0 + (x1 - x0) * t
        y = y0 + (y1 - y0) * t
        trajetoria[inicio + k] = (x, y)


def smooth_trajectory(
    trajectory: List[Posicao], window: int = 5
) -> List[Posicao]:
    """Suaviza uma trajetória com média móvel (reduz tremor frame a frame).

    O rastreamento oscila um pouco a cada frame (a caixa "treme"), o que gera
    pequenos deslocamentos falsos e, consequentemente, ruído na velocidade.
    A média móvel substitui cada posição pela média das posições vizinhas
    dentro de uma janela, deixando o movimento mais suave e as métricas mais
    estáveis. Posições ausentes (None) são preservadas como None.

    Args:
        trajectory: lista de posições (x, y) em metros, com possíveis None.
        window: tamanho da janela (nº de vizinhos de cada lado). window=5
            considera até 5 frames antes e 5 depois.

    Returns:
        Nova trajetória suavizada (mesmo tamanho da original).
    """
    if window <= 0:
        return list(trajectory)

    n = len(trajectory)
    resultado: List[Posicao] = [None] * n

    for i in range(n):
        if trajectory[i] is None:
            # Mantém gaps não preenchidos como None.
            resultado[i] = None
            continue

        # Coleta as posições válidas dentro da janela [i-window, i+window].
        xs, ys = [], []
        inicio = max(0, i - window)
        fim = min(n, i + window + 1)
        for j in range(inicio, fim):
            p = trajectory[j]
            if p is not None:
                xs.append(p[0])
                ys.append(p[1])

        # Média das posições vizinhas (sempre há pelo menos a própria).
        resultado[i] = (sum(xs) / len(xs), sum(ys) / len(ys))

    return resultado


def contar_gaps(trajectory: List[Posicao]) -> Tuple[int, int]:
    """Conta gaps em uma trajetória (útil para diagnóstico/logs).

    Args:
        trajectory: lista de posições (com possíveis None).

    Returns:
        Tupla (numero_de_gaps, total_de_frames_ausentes).
    """
    num_gaps = 0
    frames_ausentes = 0
    dentro_de_gap = False

    # Só contamos gaps "internos" (entre duas posições válidas) seriam ideais,
    # mas para diagnóstico simples contamos qualquer sequência de None.
    for pos in trajectory:
        if pos is None:
            frames_ausentes += 1
            if not dentro_de_gap:
                num_gaps += 1
                dentro_de_gap = True
        else:
            dentro_de_gap = False

    return num_gaps, frames_ausentes
