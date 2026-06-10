"""
test_pipeline.py — Teste manual do pipeline de IA.

FASE 2: testa detecção (YOLODetector) e classificação de times (TeamClassifier).
FASE 3: testa rastreamento (PlayerTracker / BoT-SORT) com e sem ReID.
As fases seguintes expandirão este arquivo.

Como usar:
    # Com um vídeo real:
    python test_pipeline.py /caminho/para/video.mp4
    # ou via variável de ambiente:
    TEST_VIDEO=/caminho/para/video.mp4 python test_pipeline.py

    # Sem vídeo (modo sintético — gera frames coloridos artificiais):
    python test_pipeline.py
"""

import logging
import os
import sys

import cv2
import numpy as np

# Permite rodar tanto de dentro de services/worker/ quanto da raiz do projeto.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline.detector import YOLODetector
from pipeline.team_classifier import TeamClassifier
from pipeline.tracker import PlayerTracker

# Configuração de logging para vermos as mensagens do pipeline no terminal.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_pipeline")

# Número de frames a processar no teste de detecção.
N_FRAMES = 10

# Número de frames para o teste de rastreamento (Fase 3).
N_FRAMES_TRACK = 60


def gerar_frames_sinteticos(n: int):
    """Gera frames sintéticos com 'jogadores' coloridos (modo sem vídeo).

    Cada frame contém retângulos: alguns vermelhos (Time A), alguns azuis
    (Time B) e um amarelo (goleiro), sobre fundo verde (gramado). Serve
    para exercitar o TeamClassifier mesmo sem um vídeo real.

    Yields:
        Tuplas (frame, lista_de_crops) — o frame e os recortes coloridos.
    """
    cores = {
        "A": (0, 0, 200),       # vermelho (BGR)
        "B": (200, 0, 0),       # azul (BGR)
        "goalkeeper": (0, 220, 220),  # amarelo (BGR)
    }
    for _ in range(n):
        # Fundo verde simulando o gramado.
        frame = np.full((480, 640, 3), (40, 120, 40), dtype=np.uint8)
        crops = []
        x = 20
        # 4 do time A, 4 do time B, 1 goleiro.
        plano = ["A"] * 4 + ["B"] * 4 + ["goalkeeper"]
        for time in plano:
            cv2.rectangle(frame, (x, 100), (x + 40, 220), cores[time], -1)
            crops.append(frame[100:220, x:x + 40].copy())
            x += 60
        yield frame, crops


def carregar_frames_video(caminho: str, n: int):
    """Lê os primeiros n frames de um vídeo real.

    Args:
        caminho: caminho do arquivo de vídeo.
        n: quantidade de frames a ler.

    Yields:
        Frames (numpy arrays BGR).

    Raises:
        IOError: se o vídeo não puder ser aberto.
    """
    cap = cv2.VideoCapture(caminho)
    if not cap.isOpened():
        raise IOError(f"Não foi possível abrir o vídeo: {caminho}")
    try:
        for _ in range(n):
            ok, frame = cap.read()
            if not ok:
                break
            yield frame
    finally:
        cap.release()


def crops_de_deteccoes(frame, deteccoes):
    """Recorta as regiões de pessoas detectadas para o classificador de times.

    Args:
        frame: o frame completo (BGR).
        deteccoes: lista de Detection.

    Returns:
        Lista de recortes (apenas das pessoas, ignorando a bola).
    """
    crops = []
    for det in deteccoes:
        if det.class_name != "person":
            continue
        x1, y1, x2, y2 = det.bbox
        crop = frame[y1:y2, x1:x2]
        if crop.size > 0:
            crops.append(crop)
    return crops


def ler_frames_para_lista(caminho: str, n: int):
    """Lê os primeiros n frames de um vídeo para uma lista em memória.

    Necessário no teste de rastreamento porque rodamos o MESMO trecho duas
    vezes (com e sem ReID) e precisamos dos mesmos frames nas duas execuções.

    Args:
        caminho: caminho do vídeo.
        n: número de frames.

    Returns:
        Lista de frames (numpy arrays BGR).
    """
    cap = cv2.VideoCapture(caminho)
    if not cap.isOpened():
        raise IOError(f"Não foi possível abrir o vídeo: {caminho}")
    frames = []
    try:
        for _ in range(n):
            ok, frame = cap.read()
            if not ok:
                break
            frames.append(frame)
    finally:
        cap.release()
    return frames


def testar_rastreamento(frames, use_reid: bool, classifier: TeamClassifier):
    """Roda o PlayerTracker em uma sequência de frames e mede trocas de ID.

    Args:
        frames: lista de frames (BGR) já carregados.
        use_reid: liga/desliga o ReID do BoT-SORT.
        classifier: TeamClassifier já calibrado, para rotular o time.

    Returns:
        Dicionário com métricas: total de IDs únicos vistos e nº de IDs novos
        que surgiram após o 1º frame (proxy de "trocas de ID" — quanto menos,
        melhor a continuidade do rastreamento).
    """
    logger.info("----- RASTREAMENTO use_reid=%s -----", use_reid)
    tracker = PlayerTracker(use_reid=use_reid)

    ids_unicos = set()
    ids_primeiro_frame = set()
    ids_novos_apos_inicio = 0

    for i, frame in enumerate(frames):
        tracks = tracker.update(frame, team_classifier=classifier)

        ids_do_frame = [t.id for t in tracks]
        # Loga o ID e o time de cada jogador rastreado neste frame.
        resumo = ", ".join(f"#{t.id}({t.team})" for t in tracks)
        logger.info("Frame %d: %d tracks -> %s", i, len(tracks), resumo)

        for t in tracks:
            if t.id not in ids_unicos:
                ids_unicos.add(t.id)
                # IDs que aparecem só depois do início indicam jogadores
                # entrando OU trocas de ID após oclusão.
                if i == 0:
                    ids_primeiro_frame.add(t.id)
                else:
                    ids_novos_apos_inicio += 1

    metricas = {
        "ids_unicos": len(ids_unicos),
        "ids_primeiro_frame": len(ids_primeiro_frame),
        "ids_novos_apos_inicio": ids_novos_apos_inicio,
    }
    logger.info(
        "Resultado use_reid=%s -> IDs únicos=%d | IDs no 1º frame=%d | IDs novos após início=%d",
        use_reid,
        metricas["ids_unicos"],
        metricas["ids_primeiro_frame"],
        metricas["ids_novos_apos_inicio"],
    )
    return metricas


def testar_com_video(caminho: str):
    """Roda detecção + classificação de times em um vídeo real."""
    logger.info("=== MODO VÍDEO: %s ===", caminho)
    detector = YOLODetector()
    classifier = TeamClassifier()

    todos_os_crops = []
    frames_guardados = []

    # 1ª passada: detecção em cada frame.
    for i, frame in enumerate(carregar_frames_video(caminho, N_FRAMES)):
        deteccoes = detector.detect(frame)
        logger.info("Frame %d: %d detecções", i, len(deteccoes))
        for det in deteccoes:
            logger.info(
                "   -> %s conf=%.2f bbox=%s",
                det.class_name,
                det.confidence,
                det.bbox,
            )
        crops = crops_de_deteccoes(frame, deteccoes)
        todos_os_crops.extend(crops)
        frames_guardados.append((frame, deteccoes))

    if not todos_os_crops:
        logger.warning("Nenhum jogador detectado — não há crops para o TeamClassifier.")
        return

    # Calibra o classificador com todos os crops coletados.
    classifier.fit(todos_os_crops)

    # Classifica os jogadores do primeiro frame que teve detecções.
    for frame, deteccoes in frames_guardados:
        crops = crops_de_deteccoes(frame, deteccoes)
        if not crops:
            continue
        logger.info("Classificação de times no primeiro frame com jogadores:")
        for idx, crop in enumerate(crops):
            time = classifier.classify(crop)
            logger.info("   jogador %d -> time %s", idx, time)
        break

    # ===== FASE 3: rastreamento em 60 frames, com e sem ReID =====
    logger.info("==================================================")
    logger.info("FASE 3 — RASTREAMENTO (BoT-SORT) em %d frames", N_FRAMES_TRACK)
    logger.info("==================================================")
    frames = ler_frames_para_lista(caminho, N_FRAMES_TRACK)
    logger.info("%d frames carregados para o teste de rastreamento.", len(frames))

    # Execução 1: sem ReID (rápido, CPU).
    metricas_sem = testar_rastreamento(frames, use_reid=False, classifier=classifier)
    # Execução 2: com ReID (mais preciso, mais lento).
    metricas_com = testar_rastreamento(frames, use_reid=True, classifier=classifier)

    # Comparação final entre as duas execuções.
    logger.info("==================== COMPARAÇÃO ====================")
    logger.info(
        "SEM ReID: IDs únicos=%d | novos após início=%d",
        metricas_sem["ids_unicos"],
        metricas_sem["ids_novos_apos_inicio"],
    )
    logger.info(
        "COM ReID: IDs únicos=%d | novos após início=%d",
        metricas_com["ids_unicos"],
        metricas_com["ids_novos_apos_inicio"],
    )
    logger.info(
        "Menos 'IDs novos após início' = melhor continuidade (menos trocas de ID)."
    )


def testar_sintetico():
    """Roda o teste em modo sintético (sem vídeo real)."""
    logger.info("=== MODO SINTÉTICO (sem vídeo) ===")
    logger.warning(
        "Sem vídeo fornecido. O YOLO dificilmente detecta formas sintéticas, "
        "então testamos o TeamClassifier diretamente com crops coloridos. "
        "Para um teste real, rode: python test_pipeline.py <caminho_do_video>"
    )

    # Ainda assim instanciamos o detector para validar que o modelo carrega.
    detector = YOLODetector()
    classifier = TeamClassifier()

    todos_os_crops = []
    primeiro_frame_crops = None

    for i, (frame, crops) in enumerate(gerar_frames_sinteticos(N_FRAMES)):
        deteccoes = detector.detect(frame)
        logger.info("Frame sintético %d: %d detecções do YOLO", i, len(deteccoes))
        todos_os_crops.extend(crops)
        if primeiro_frame_crops is None:
            primeiro_frame_crops = crops

    # Calibra e classifica usando os crops coloridos sintéticos.
    classifier.fit(todos_os_crops)
    logger.info("Classificação dos 9 'jogadores' sintéticos do primeiro frame:")
    esperado = ["A"] * 4 + ["B"] * 4 + ["goalkeeper"]
    for idx, crop in enumerate(primeiro_frame_crops):
        time = classifier.classify(crop)
        logger.info("   jogador %d -> time %s (esperado: %s)", idx, time, esperado[idx])


def main():
    """Ponto de entrada do teste."""
    caminho = None
    if len(sys.argv) > 1:
        caminho = sys.argv[1]
    elif os.getenv("TEST_VIDEO"):
        caminho = os.getenv("TEST_VIDEO")

    if caminho and os.path.exists(caminho):
        testar_com_video(caminho)
    else:
        if caminho:
            logger.error("Vídeo não encontrado: %s — caindo no modo sintético.", caminho)
        testar_sintetico()


if __name__ == "__main__":
    main()
