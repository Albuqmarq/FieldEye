"""
video_writer.py — Geração do vídeo anotado final.

Etapa 9 do pipeline. Recebe, frame a frame, os jogadores rastreados (com ID,
time e velocidade) e desenha sobre o vídeo:
    - caixa colorida por time (vermelho = Time A, azul = Time B, amarelo = goleiro)
    - ID do jogador e velocidade instantânea acima da caixa
    - timestamp do vídeo no canto superior esquerdo

O resultado é salvo como um arquivo .mp4 em data/outputs/.
"""

import logging
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Cores (BGR) por time. Vermelho = A, Azul = B, Amarelo = goleiro.
CORES_TIME = {
    "A": (0, 0, 230),
    "B": (230, 0, 0),
    "goalkeeper": (0, 230, 230),
    "unknown": (200, 200, 200),
}


@dataclass
class Anotacao:
    """Dados de um jogador a desenhar em um frame.

    Atributos:
        track_id: ID persistente do jogador.
        bbox: caixa (x1, y1, x2, y2) em pixels.
        team: time ("A", "B", "goalkeeper", "unknown").
        speed: velocidade instantânea em km/h (None se desconhecida).
    """

    track_id: int
    bbox: Tuple[int, int, int, int]
    team: str
    speed: Optional[float] = None


class AnnotatedVideoWriter:
    """Escreve um vídeo anotado a partir de frames + anotações por frame."""

    def __init__(
        self,
        output_path: str,
        fps: float,
        frame_size: Tuple[int, int],
        codec: str = "mp4v",
    ):
        """Inicializa o escritor de vídeo.

        Args:
            output_path: caminho de saída do .mp4.
            fps: quadros por segundo do vídeo de saída.
            frame_size: (largura, altura) em pixels.
            codec: FourCC do codec (padrão mp4v, compatível com .mp4).
        """
        self.output_path = output_path
        self.fps = fps if fps and fps > 0 else 25.0
        self.frame_size = frame_size

        # Garante que a pasta de saída exista.
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        fourcc = cv2.VideoWriter_fourcc(*codec)
        self.writer = cv2.VideoWriter(output_path, fourcc, self.fps, frame_size)
        if not self.writer.isOpened():
            # Falha ao abrir o writer é fatal — sem isso não há vídeo.
            msg = f"Não foi possível abrir o VideoWriter para {output_path}."
            logger.error(msg)
            raise IOError(msg)

        logger.info(
            "AnnotatedVideoWriter pronto: %s (%dx%d @ %.1ffps).",
            output_path,
            frame_size[0],
            frame_size[1],
            self.fps,
        )

    def write_frame(
        self,
        frame: np.ndarray,
        anotacoes: List[Anotacao],
        timestamp: float,
    ) -> None:
        """Desenha as anotações em um frame e o grava no vídeo.

        Args:
            frame: frame BGR original.
            anotacoes: lista de Anotacao (jogadores) deste frame.
            timestamp: tempo do frame em segundos (para o relógio do vídeo).
        """
        if frame is None:
            logger.warning("write_frame recebeu frame None — ignorado.")
            return

        # Desenha em uma cópia para não alterar o frame original.
        img = frame.copy()

        for ant in anotacoes:
            self._desenhar_jogador(img, ant)

        # Timestamp no canto superior esquerdo (mm:ss.mmm).
        self._desenhar_timestamp(img, timestamp)

        try:
            self.writer.write(img)
        except Exception as exc:
            logger.exception("Erro ao gravar frame no vídeo: %s", exc)

    def _desenhar_jogador(self, img: np.ndarray, ant: Anotacao) -> None:
        """Desenha a caixa, ID e velocidade de um jogador."""
        x1, y1, x2, y2 = ant.bbox
        cor = CORES_TIME.get(ant.team, CORES_TIME["unknown"])

        # Caixa delimitadora.
        cv2.rectangle(img, (x1, y1), (x2, y2), cor, 2)

        # Rótulo: ID + velocidade (se disponível).
        if ant.speed is not None:
            rotulo = f"#{ant.track_id} {ant.speed:.0f}km/h"
        else:
            rotulo = f"#{ant.track_id}"

        # Fundo do texto para garantir legibilidade sobre o gramado.
        (tw, th), _ = cv2.getTextSize(rotulo, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        y_texto = max(th + 2, y1 - 4)
        cv2.rectangle(
            img,
            (x1, y_texto - th - 3),
            (x1 + tw + 2, y_texto + 2),
            cor,
            -1,  # preenchido
        )
        cv2.putText(
            img,
            rotulo,
            (x1 + 1, y_texto),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

    def _desenhar_timestamp(self, img: np.ndarray, timestamp: float) -> None:
        """Desenha o relógio do vídeo no canto superior esquerdo."""
        minutos = int(timestamp // 60)
        segundos = timestamp - minutos * 60
        texto = f"{minutos:02d}:{segundos:06.3f}"
        cv2.putText(
            img,
            texto,
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 0),
            4,  # contorno preto (legibilidade)
            cv2.LINE_AA,
        )
        cv2.putText(
            img,
            texto,
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

    def close(self) -> None:
        """Finaliza e fecha o arquivo de vídeo."""
        if self.writer is not None:
            self.writer.release()
            logger.info("Vídeo finalizado: %s", self.output_path)
            self.writer = None

    # Permite uso com 'with AnnotatedVideoWriter(...) as w:'
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
