"""
camera_motion.py — Compensação de movimento de câmera (Nível 1).

Em transmissões de TV a câmera gira/dá zoom. Sem corrigir isso, um jogador
PARADO "anda" muitos pixels quando a câmera se move, gerando velocidade falsa.

Este módulo estima, a cada frame, como a CÂMERA se moveu em relação ao frame
anterior (usando pontos fixos do fundo) e acumula essa transformação. Assim
conseguimos mapear a posição de cada jogador de volta para o sistema de
coordenadas do PRIMEIRO frame (referência fixa). Resultado: o movimento da
câmera é descontado e sobra só o movimento real do jogador.

Usa fluxo óptico esparso (goodFeaturesToTrack + Lucas-Kanade) e estima uma
transformação de similaridade (translação + rotação + escala), que cobre
pan, giro e zoom.
"""

import logging
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def _para_3x3(M: np.ndarray) -> np.ndarray:
    """Converte uma matriz afim 2x3 em homogênea 3x3."""
    H = np.eye(3, dtype=np.float64)
    H[:2, :] = M
    return H


class CameraMotionCompensator:
    """Acumula o movimento da câmera para estabilizar coordenadas.

    Uso:
        comp = CameraMotionCompensator()
        comp.reset(frame0)
        for frame in frames:
            comp.update(frame, exclude_boxes=[...])  # caixas dos jogadores
            x_ref, y_ref = comp.transform_point(px, py)  # coords no frame 0
    """

    def __init__(self, max_corners: int = 400, min_pontos: int = 8):
        """Inicializa o compensador.

        Args:
            max_corners: nº máximo de pontos de referência por frame.
            min_pontos: mínimo de pontos casados para confiar na estimativa.
        """
        self.max_corners = max_corners
        self.min_pontos = min_pontos
        self.prev_gray: Optional[np.ndarray] = None
        # C mapeia coordenadas do frame ATUAL -> frame de referência (0).
        self.C: np.ndarray = np.eye(3, dtype=np.float64)

    def reset(self, frame: np.ndarray) -> None:
        """Reinicia o compensador definindo o frame de referência (0).

        Args:
            frame: primeiro frame (BGR), que vira o sistema de referência.
        """
        self.prev_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self.C = np.eye(3, dtype=np.float64)

    def _mascara_sem_jogadores(
        self, shape: Tuple[int, int], exclude_boxes: Optional[List[tuple]]
    ) -> Optional[np.ndarray]:
        """Cria máscara que exclui as regiões dos jogadores.

        Pontos de referência devem vir do FUNDO (campo, arquibancada, linhas),
        não dos jogadores — que se movem por conta própria e contaminariam a
        estimativa do movimento da câmera.
        """
        if not exclude_boxes:
            return None
        h, w = shape
        mask = np.full((h, w), 255, dtype=np.uint8)
        for (x1, y1, x2, y2) in exclude_boxes:
            # Zera (ignora) a área de cada jogador, com uma pequena margem.
            x1 = max(0, x1 - 5); y1 = max(0, y1 - 5)
            x2 = min(w, x2 + 5); y2 = min(h, y2 + 5)
            mask[y1:y2, x1:x2] = 0
        return mask

    def update(
        self, frame: np.ndarray, exclude_boxes: Optional[List[tuple]] = None
    ) -> np.ndarray:
        """Atualiza a estimativa de movimento com o frame atual.

        Args:
            frame: frame atual (BGR).
            exclude_boxes: caixas (x1,y1,x2,y2) dos jogadores a ignorar.

        Returns:
            Matriz 3x3 que mapeia o frame atual para o frame de referência.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Primeiro frame após reset: nada a comparar ainda.
        if self.prev_gray is None:
            self.prev_gray = gray
            return self.C

        T = np.eye(3, dtype=np.float64)  # transformação frame_atual -> anterior
        try:
            mask = self._mascara_sem_jogadores(gray.shape, exclude_boxes)
            pts_prev = cv2.goodFeaturesToTrack(
                self.prev_gray,
                maxCorners=self.max_corners,
                qualityLevel=0.01,
                minDistance=8,
                mask=mask,
            )

            if pts_prev is not None and len(pts_prev) >= self.min_pontos:
                # Segue os pontos do frame anterior no frame atual.
                pts_curr, status, _ = cv2.calcOpticalFlowPyrLK(
                    self.prev_gray, gray, pts_prev, None
                )
                status = status.reshape(-1).astype(bool)
                p_prev = pts_prev[status]
                p_curr = pts_curr[status]

                if len(p_prev) >= self.min_pontos:
                    # Estima similaridade que leva curr -> prev (frame i -> i-1).
                    M, _ = cv2.estimateAffinePartial2D(
                        p_curr, p_prev, method=cv2.RANSAC
                    )
                    if M is not None:
                        T = _para_3x3(M)
                else:
                    logger.debug("Poucos pontos casados — assumindo câmera parada.")
            else:
                logger.debug("Poucos pontos de referência — assumindo câmera parada.")
        except cv2.error as exc:
            # Em caso de falha, assumimos sem movimento (T = identidade).
            logger.warning("Falha na estimativa de movimento de câmera: %s", exc)

        # Acumula: frame atual -> referência = (anterior -> referência) ∘ T.
        self.C = self.C @ T
        self.prev_gray = gray
        return self.C

    def transform_point(self, x: float, y: float) -> Tuple[float, float]:
        """Mapeia um ponto do frame atual para o frame de referência (0).

        Args:
            x: coordenada x em pixels no frame atual.
            y: coordenada y em pixels no frame atual.

        Returns:
            (x_ref, y_ref) no sistema de coordenadas do frame de referência.
        """
        v = self.C @ np.array([x, y, 1.0], dtype=np.float64)
        # Transformação afim/similaridade: terceira coordenada permanece 1.
        return float(v[0]), float(v[1])
