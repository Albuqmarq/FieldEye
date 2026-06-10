"""
calibrate.py — Ferramenta de calibração da homografia por clique.

Use em vídeos de CÂMERA FIXA (treinos que você grava). Você abre um frame,
clica em 4 pontos de referência do campo e a ferramenta gera a calibração
(pixel -> metros), salvando em JSON para reuso.

Para jogos AO VIVO (câmera que mexe/zoom), não calibre — o pipeline usa o
modo aproximado (fallback) automaticamente.

Como usar:
    python calibrate.py <caminho_do_video> [--frame N] [--output arquivo.json]

Pontos a clicar (NESTA ORDEM), referentes à GRANDE ÁREA ESQUERDA:
    1) Canto da área na linha de fundo — lado INFERIOR
    2) Canto da área na linha de fundo — lado SUPERIOR
    3) Quina frontal da área — lado SUPERIOR
    4) Quina frontal da área — lado INFERIOR
"""

import argparse
import logging
import os
import sys

import cv2

# Garante import do pacote pipeline rodando de dentro de services/worker/.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline.homography import GRANDE_AREA_ESQUERDA, HomographyMapper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("calibrate")

# Descrições mostradas ao usuário, na mesma ordem de GRANDE_AREA_ESQUERDA.
DESCRICOES = [
    "1) Canto da area na LINHA DE FUNDO - lado INFERIOR  (0.0, 13.84)",
    "2) Canto da area na LINHA DE FUNDO - lado SUPERIOR  (0.0, 54.16)",
    "3) Quina FRONTAL da area - lado SUPERIOR            (16.5, 54.16)",
    "4) Quina FRONTAL da area - lado INFERIOR            (16.5, 13.84)",
]


def carregar_frame(caminho: str, indice: int):
    """Lê um frame específico do vídeo.

    Args:
        caminho: caminho do vídeo.
        indice: número do frame a capturar.

    Returns:
        Frame BGR (numpy array).

    Raises:
        IOError: se o vídeo não abrir ou o frame não existir.
    """
    cap = cv2.VideoCapture(caminho)
    if not cap.isOpened():
        raise IOError(f"Não foi possível abrir o vídeo: {caminho}")
    cap.set(cv2.CAP_PROP_POS_FRAMES, indice)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise IOError(f"Não foi possível ler o frame {indice} do vídeo.")
    return frame


def coletar_cliques(frame):
    """Mostra o frame e coleta 4 cliques do usuário via matplotlib.

    Args:
        frame: frame BGR.

    Returns:
        Lista de 4 tuplas (x_pixel, y_pixel) na ordem clicada.
    """
    # Import tardio para não exigir matplotlib quando só se carrega calibração.
    import matplotlib.pyplot as plt

    # OpenCV usa BGR; matplotlib espera RGB.
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    fig, ax = plt.subplots(figsize=(14, 8))
    ax.imshow(frame_rgb)
    ax.set_title(
        "Clique os 4 pontos NA ORDEM indicada no terminal.\n"
        "(botão direito desfaz o último, ENTER finaliza)"
    )
    print("\n=== Clique os pontos NESTA ORDEM ===")
    for d in DESCRICOES:
        print("   " + d)
    print("====================================\n")

    # ginput coleta exatamente 4 cliques (timeout=0 = sem limite de tempo).
    pontos = plt.ginput(n=4, timeout=0, show_clicks=True)
    plt.close(fig)
    return pontos


def main():
    parser = argparse.ArgumentParser(description="Calibração de homografia por clique.")
    parser.add_argument("video", help="Caminho do vídeo")
    parser.add_argument("--frame", type=int, default=0, help="Índice do frame (padrão 0)")
    parser.add_argument(
        "--output",
        default=None,
        help="Arquivo JSON de saída (padrão: data/models/calibration_<video>.json)",
    )
    args = parser.parse_args()

    try:
        frame = carregar_frame(args.video, args.frame)
    except IOError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    h, w = frame.shape[:2]
    logger.info("Frame %d carregado (%dx%d).", args.frame, w, h)

    pontos_pixel = coletar_cliques(frame)
    if len(pontos_pixel) != 4:
        logger.error("Foram coletados %d cliques (precisa de 4). Abortando.", len(pontos_pixel))
        sys.exit(1)

    logger.info("Pontos clicados (pixels): %s", [(round(x), round(y)) for x, y in pontos_pixel])

    # Calibra usando os 4 cantos conhecidos da grande área esquerda.
    mapper = HomographyMapper()
    mapper.set_frame_size(w, h)
    ok = mapper.set_keypoints(pontos_pixel, GRANDE_AREA_ESQUERDA)
    if not ok:
        logger.error("Calibração falhou. Verifique se clicou os pontos corretamente.")
        sys.exit(1)

    # Define o caminho de saída padrão a partir do nome do vídeo.
    if args.output:
        saida = args.output
    else:
        nome = os.path.splitext(os.path.basename(args.video))[0]
        saida = os.path.join("..", "..", "data", "models", f"calibration_{nome}.json")

    if mapper.save_calibration(saida):
        logger.info("Calibração concluída e salva em: %s", saida)
        # Verificação rápida: converte um ponto clicado e mostra o resultado.
        x_m, y_m = mapper.pixel_to_meters(*pontos_pixel[0])
        logger.info(
            "Verificação: 1º ponto clicado vira (%.2f, %.2f)m (esperado ~%.2f, %.2f).",
            x_m, y_m, GRANDE_AREA_ESQUERDA[0][0], GRANDE_AREA_ESQUERDA[0][1],
        )
    else:
        logger.error("Não foi possível salvar a calibração.")
        sys.exit(1)


if __name__ == "__main__":
    main()
