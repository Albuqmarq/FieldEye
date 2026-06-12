"""
consolidation.py — Consolidação de IDs em jogadores reais.

O rastreamento fragmenta um mesmo jogador em vários IDs (oclusões, falhas
momentâneas e, sobretudo, cortes de cena). Para um dashboard fazer sentido,
precisamos transformar esses fragmentos em JOGADORES reais.

Fazemos isso em duas etapas automáticas:

  1. COSTURA (stitch): liga fragmentos SEQUENCIAIS que são claramente o mesmo
     jogador — um termina e outro começa logo em seguida, perto no espaço e do
     mesmo time. (Conservador: não liga através de cortes, onde o fragmento
     reaparece longe.)

  2. FILTRO DE RUÍDO: descarta fragmentos curtos/parados (poucos frames ou
     distância ~0), que são detecções espúrias e poluem o resultado.

Tudo aqui é heurístico e automático. Para precisão máxima, uma etapa manual
(rotular quem é quem) ou OCR de número de camisa entram depois, no frontend.
"""

import logging
import math
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

Posicao = Optional[Tuple[float, float]]


def _resumo_track(traj: List[Posicao]) -> Optional[dict]:
    """Resume uma trajetória: primeiro/último frame, extremos e distância.

    Args:
        traj: lista (por frame) de posições (x, y) em metros ou None.

    Returns:
        Dict com os dados-resumo, ou None se a trajetória for toda vazia.
    """
    indices = [i for i, p in enumerate(traj) if p is not None]
    if not indices:
        return None

    primeiro, ultimo = indices[0], indices[-1]
    # Distância percorrida (soma dos passos válidos).
    dist = 0.0
    anterior = None
    for i in indices:
        if anterior is not None:
            dist += math.hypot(traj[i][0] - anterior[0], traj[i][1] - anterior[1])
        anterior = traj[i]

    return {
        "primeiro": primeiro,
        "ultimo": ultimo,
        "pos_ini": traj[primeiro],
        "pos_fim": traj[ultimo],
        "n_frames": len(indices),
        "distancia": dist,
    }


def costurar_tracks(
    pos_por_id: Dict[int, List[Posicao]],
    team_por_id: Dict[int, str],
    max_gap_frames: int = 45,
    max_dist_m: float = 5.0,
) -> Dict[int, int]:
    """Liga fragmentos sequenciais do mesmo jogador (track stitching).

    Estratégia gulosa em ordem cronológica: para cada fragmento, tenta anexá-lo
    a uma "corrente" já existente cujo fim seja logo antes (gap pequeno), perto
    no espaço e do mesmo time. Se não couber em nenhuma, vira uma corrente nova.

    Args:
        pos_por_id: {id: trajetória}.
        team_por_id: {id: time}.
        max_gap_frames: gap temporal máximo (frames) para considerar costura.
        max_dist_m: distância espacial máxima (metros) entre fim e início.

    Returns:
        Mapa {id_original: id_canônico} (o canônico é o 1º fragmento da corrente).
    """
    # Resume cada track e descarta os totalmente vazios.
    resumos = {}
    for tid, traj in pos_por_id.items():
        r = _resumo_track(traj)
        if r is not None:
            resumos[tid] = r

    # Processa em ordem de aparição (primeiro frame).
    ordem = sorted(resumos.keys(), key=lambda t: resumos[t]["primeiro"])

    # Cada corrente guarda o estado do "fim" atual.
    correntes = []  # lista de dicts: {canonico, ultimo, pos_fim, team}
    mapa: Dict[int, int] = {}

    for tid in ordem:
        r = resumos[tid]
        time = team_por_id.get(tid, "unknown")
        melhor = None
        melhor_custo = None

        for c in correntes:
            # Precisa ser sequencial (começa depois do fim da corrente).
            gap = r["primeiro"] - c["ultimo"]
            if gap < 0 or gap > max_gap_frames:
                continue
            # Mesmo time (ou um dos dois desconhecido).
            if c["team"] != time and "unknown" not in (c["team"], time):
                continue
            # Distância entre o fim da corrente e o início deste fragmento.
            d = math.hypot(
                r["pos_ini"][0] - c["pos_fim"][0],
                r["pos_ini"][1] - c["pos_fim"][1],
            )
            # Tolerância cresce um pouco com o gap (jogador andou nesse intervalo).
            limite = max_dist_m + 0.15 * gap
            if d > limite:
                continue
            # Custo: prioriza menor distância e menor gap.
            custo = d + 0.1 * gap
            if melhor_custo is None or custo < melhor_custo:
                melhor_custo = custo
                melhor = c

        if melhor is not None:
            # Anexa este fragmento à melhor corrente encontrada.
            mapa[tid] = melhor["canonico"]
            melhor["ultimo"] = r["ultimo"]
            melhor["pos_fim"] = r["pos_fim"]
            if melhor["team"] == "unknown":
                melhor["team"] = time
        else:
            # Nenhuma corrente serve: começa uma nova (este id é o canônico).
            mapa[tid] = tid
            correntes.append({
                "canonico": tid,
                "ultimo": r["ultimo"],
                "pos_fim": r["pos_fim"],
                "team": time,
            })

    n_antes = len(resumos)
    n_depois = len(set(mapa.values()))
    logger.info(
        "Costura: %d fragmentos -> %d correntes (%d ligações).",
        n_antes, n_depois, n_antes - n_depois,
    )
    return mapa


def aplicar_mapa(
    pos_por_id: Dict[int, List[Posicao]],
    mapa: Dict[int, int],
    n_frames: int,
) -> Dict[int, List[Posicao]]:
    """Funde as trajetórias dos fragmentos em suas correntes canônicas.

    Args:
        pos_por_id: {id: trajetória}.
        mapa: {id_original: id_canônico}.
        n_frames: número de frames (tamanho das trajetórias).

    Returns:
        {id_canônico: trajetória combinada}.
    """
    combinado: Dict[int, List[Posicao]] = {}
    for tid, traj in pos_por_id.items():
        canon = mapa.get(tid, tid)
        if canon not in combinado:
            combinado[canon] = [None] * n_frames
        destino = combinado[canon]
        for i, p in enumerate(traj):
            # Mantém a posição existente; preenche onde estava vazio.
            if p is not None and destino[i] is None:
                destino[i] = p
    return combinado


def filtrar_ruido(
    pos_por_id: Dict[int, List[Posicao]],
    min_frames: int = 15,
    min_distancia: float = 2.0,
) -> Dict[int, List[Posicao]]:
    """Remove fragmentos curtos/parados (detecções espúrias).

    Args:
        pos_por_id: {id: trajetória}.
        min_frames: nº mínimo de frames para o track ser considerado real.
        min_distancia: distância mínima (metros) percorrida.

    Returns:
        Dicionário apenas com os tracks que passaram no filtro.
    """
    mantidos = {}
    descartados = 0
    for tid, traj in pos_por_id.items():
        r = _resumo_track(traj)
        if r is None:
            descartados += 1
            continue
        if r["n_frames"] < min_frames or r["distancia"] < min_distancia:
            descartados += 1
            continue
        mantidos[tid] = traj

    logger.info(
        "Filtro de ruído: mantidos %d, descartados %d (min_frames=%d, min_dist=%.1fm).",
        len(mantidos), descartados, min_frames, min_distancia,
    )
    return mantidos


def consolidar(
    pos_por_id: Dict[int, List[Posicao]],
    team_por_id: Dict[int, str],
    n_frames: int,
    max_gap_frames: int = 45,
    max_dist_m: float = 5.0,
    min_frames: int = 15,
    min_distancia: float = 2.0,
) -> Tuple[Dict[int, List[Posicao]], Dict[int, int]]:
    """Pipeline de consolidação: costura -> funde -> filtra ruído.

    Args:
        pos_por_id: {id: trajetória}.
        team_por_id: {id: time}.
        n_frames: número de frames.
        max_gap_frames, max_dist_m: parâmetros da costura.
        min_frames, min_distancia: parâmetros do filtro de ruído.

    Returns:
        Tupla (trajetórias_consolidadas, mapa_id_original_para_final).
        IDs descartados pelo filtro NÃO aparecem no mapa final.
    """
    # 1) Costura de fragmentos sequenciais.
    mapa = costurar_tracks(pos_por_id, team_por_id, max_gap_frames, max_dist_m)
    # 2) Funde as trajetórias por corrente canônica.
    combinado = aplicar_mapa(pos_por_id, mapa, n_frames)
    # 3) Filtra ruído (correntes curtas/paradas).
    final = filtrar_ruido(combinado, min_frames, min_distancia)

    # Mapa final: só ids cujo canônico sobreviveu ao filtro.
    sobreviventes = set(final.keys())
    mapa_final = {
        orig: canon for orig, canon in mapa.items() if canon in sobreviventes
    }
    logger.info("Consolidação final: %d jogadores reais.", len(final))
    return final, mapa_final
