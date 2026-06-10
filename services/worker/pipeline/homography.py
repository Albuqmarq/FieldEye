"""
homography.py — Conversão de pixels para metros (homografia).

Etapa 5 do pipeline. A câmera enxerga o campo em PERSPECTIVA: o mesmo
deslocamento em metros ocupa muitos pixels perto da câmera e poucos pixels
longe dela. Para medir velocidade/distância reais precisamos converter as
posições em pixels para coordenadas no campo em metros.

Isso é feito com uma HOMOGRAFIA: uma matriz 3x3 que mapeia o plano da imagem
para o plano do campo. Calibramos com 4+ pontos de referência conhecidos
(cantos da área, interseções de linhas) e suas posições reais no campo.
"""

import logging
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class HomographyMapper:
    """Mapeia coordenadas de pixel para metros no campo.

    Uso ideal:
        mapper = HomographyMapper()
        mapper.set_keypoints(pontos_imagem, pontos_campo)
        x_m, y_m = mapper.pixel_to_meters(px, py)

    Sem calibração, cai em um modo de FALLBACK que estima uma escala linear
    (com aviso no log) — útil para testes, porém impreciso.
    """

    def __init__(self, field_size: Tuple[float, float] = (105.0, 68.0)):
        """Inicializa o mapeador.

        Args:
            field_size: dimensões do campo em metros (comprimento, largura).
                Padrão FIFA: 105m x 68m.
        """
        self.field_length, self.field_width = field_size
        # Matriz de homografia 3x3 (None enquanto não calibrada).
        self.H: Optional[np.ndarray] = None
        # Tamanho do frame (necessário para o fallback).
        self.frame_size: Optional[Tuple[int, int]] = None  # (largura, altura)
        # Evita repetir o aviso de fallback a cada chamada.
        self._aviso_fallback_emitido = False

    def set_frame_size(self, width: int, height: int) -> None:
        """Informa o tamanho do frame, usado apenas pelo modo de fallback.

        Args:
            width: largura do frame em pixels.
            height: altura do frame em pixels.
        """
        self.frame_size = (width, height)

    def set_keypoints(
        self,
        image_points: List[Tuple[float, float]],
        field_points: List[Tuple[float, float]],
    ) -> bool:
        """Calibra a homografia a partir de pontos de referência.

        Args:
            image_points: lista de (x, y) em PIXELS na imagem.
            field_points: lista de (x, y) em METROS no campo, na mesma ordem.

        Returns:
            True se a calibração funcionou, False caso contrário.
        """
        # Homografia exige no mínimo 4 correspondências (e mesma quantidade).
        if len(image_points) < 4 or len(image_points) != len(field_points):
            logger.error(
                "Calibração requer >= 4 pontos e listas do mesmo tamanho "
                "(imagem=%d, campo=%d).",
                len(image_points),
                len(field_points),
            )
            return False

        try:
            src = np.array(image_points, dtype=np.float32)
            dst = np.array(field_points, dtype=np.float32)
            # RANSAC torna a estimativa robusta a pontos imprecisos.
            H, _ = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
            if H is None:
                logger.error("findHomography não conseguiu estimar a matriz.")
                return False
            self.H = H
            logger.info("Homografia calibrada com %d pontos.", len(image_points))
            return True
        except cv2.error as exc:
            logger.exception("Erro ao calibrar homografia: %s", exc)
            return False

    def pixel_to_meters(self, x: float, y: float) -> Tuple[float, float]:
        """Converte uma posição em pixels para metros no campo.

        Args:
            x: coordenada horizontal em pixels.
            y: coordenada vertical em pixels.

        Returns:
            Tupla (x_metros, y_metros).
        """
        if self.H is not None:
            # Aplica a homografia: ponto homogêneo [x, y, 1] transformado.
            ponto = np.array([[[x, y]]], dtype=np.float32)
            transformado = cv2.perspectiveTransform(ponto, self.H)
            x_m, y_m = float(transformado[0][0][0]), float(transformado[0][0][1])
            return x_m, y_m

        # ----- FALLBACK: sem homografia calibrada -----
        return self._fallback_escala(x, y)

    def _fallback_escala(self, x: float, y: float) -> Tuple[float, float]:
        """Estimativa linear de metros quando não há calibração.

        Assume que o campo ocupa toda a largura/altura do frame — uma
        aproximação grosseira (ignora a perspectiva), mas suficiente para
        validar o restante do pipeline em testes.
        """
        if not self._aviso_fallback_emitido:
            logger.warning(
                "Homografia NÃO calibrada — usando escala linear aproximada "
                "(impreciso, ignora perspectiva). Calibre com set_keypoints()."
            )
            self._aviso_fallback_emitido = True

        if self.frame_size is None:
            # Sem tamanho do frame, assumimos Full HD como padrão razoável.
            largura, altura = 1920, 1080
        else:
            largura, altura = self.frame_size

        # Regra de três simples: pixels -> metros.
        metros_por_pixel_x = self.field_length / largura
        metros_por_pixel_y = self.field_width / altura
        return x * metros_por_pixel_x, y * metros_por_pixel_y

    @property
    def calibrada(self) -> bool:
        """Indica se a homografia foi calibrada (True) ou está em fallback."""
        return self.H is not None
