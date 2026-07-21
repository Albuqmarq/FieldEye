"""Classificação de times pela cor do uniforme (K-means)."""

import logging
import os
from typing import List, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class TeamClassifier:
    """Classifica jogadores em "A", "B" ou "goalkeeper" pela cor do uniforme.

    Estratégia:
      1. Para cada recorte (crop) de jogador, extraímos a cor média da
         região central do torso (evitando fundo/gramado nas bordas).
      2. Calibramos um K-means com k=3 sobre essas cores nos primeiros frames.
      3. Cada cluster vira um rótulo de time. O cluster menos populoso é
         tratado como goleiro (normalmente há só 1-2 goleiros em campo).
    """

    def __init__(self, k: int = 4):
        """Inicializa o classificador.

        Args:
            k: número de grupos de cor. Padrão 4: os 2 maiores são os times
                (A e B) e os demais (goleiros, juízes, ruído) viram "outro".
                Mais grupos = separação de cor mais fina.
        """
        self.k = k
        # Centros dos clusters (cores médias), preenchidos no fit().
        self.centers: Optional[np.ndarray] = None
        # Centros de cor dos DOIS times (A e B) e a distância entre eles.
        self.team_centers: Optional[np.ndarray] = None
        self.d_teams: float = 0.0
        # Razão para marcar "outro": só vira "outro" quem está longe dos dois
        # times em relação à distância entre eles. Valor alto = conservador
        # (assume time por padrão, evitando marcar jogador comum como "outro").
        self.outro_ratio: float = float(os.getenv("TEAM_OUTLIER_RATIO", "0.9"))
        # Indica se o modelo já foi calibrado.
        self.is_fitted: bool = False

    def _cor_central(self, crop: np.ndarray) -> Optional[np.ndarray]:
        """Extrai a cor característica do uniforme em HSV (matiz/saturação/valor).

        Usamos HSV em vez de BGR porque ele separa melhor uniformes de cores
        parecidas: por exemplo, BRANCO (saturação baixa) x AZUL-CLARO (saturação
        maior) ficam distantes no eixo de saturação, mas quase iguais em BGR.

        Além disso, mascaramos os pixels de GRAMA (verde) e os muito escuros
        (sombra/short), para que sobre principalmente a cor da camisa.

        Args:
            crop: recorte do jogador (imagem BGR).

        Returns:
            Vetor [H, S, V] médio da camisa, ou None se o crop for inválido.
        """
        if crop is None or crop.size == 0:
            return None

        h, w = crop.shape[:2]
        if h < 4 or w < 4:
            # Crop pequeno demais para extrair cor confiável.
            return None

        # Região central: faixa horizontal central e metade superior (torso).
        y1, y2 = int(h * 0.15), int(h * 0.55)
        x1, x2 = int(w * 0.25), int(w * 0.75)
        regiao = crop[y1:y2, x1:x2]
        if regiao.size == 0:
            return None

        # Converte para HSV (H:0-180, S:0-255, V:0-255 no OpenCV).
        hsv = cv2.cvtColor(regiao, cv2.COLOR_BGR2HSV).reshape(-1, 3)

        # Máscara de grama: matiz verde (~35-85) com alguma saturação.
        h_ch, s_ch, v_ch = hsv[:, 0], hsv[:, 1], hsv[:, 2]
        eh_grama = (h_ch >= 35) & (h_ch <= 85) & (s_ch >= 40)
        # Máscara de pixels muito escuros (sombra/short preto).
        muito_escuro = v_ch < 40
        validos = ~(eh_grama | muito_escuro)

        # Se sobrou pouca coisa, usa todos os pixels (evita ficar sem amostra).
        pixels = hsv[validos] if validos.sum() >= 10 else hsv
        return pixels.mean(axis=0)

    def fit(self, crops: List[np.ndarray]) -> None:
        """Calibra o classificador com recortes dos primeiros frames.

        Args:
            crops: lista de recortes (imagens BGR) de jogadores.
        """
        cores = []
        for crop in crops:
            cor = self._cor_central(crop)
            if cor is not None:
                cores.append(cor)

        if len(cores) < self.k:
            # Sem amostras suficientes, não dá para formar k clusters.
            logger.warning(
                "Amostras insuficientes para calibrar (%d < k=%d). "
                "Classificação ficará indisponível.",
                len(cores),
                self.k,
            )
            self.is_fitted = False
            return

        amostras = np.array(cores, dtype=np.float32)

        # Critério de parada do K-means do OpenCV: 100 iterações ou epsilon 0.2.
        criterio = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.2)

        try:
            # compactness, labels e centros dos clusters.
            _, labels, centers = cv2.kmeans(
                amostras,
                self.k,
                None,
                criterio,
                attempts=10,
                flags=cv2.KMEANS_PP_CENTERS,  # inicialização k-means++
            )
        except cv2.error as exc:
            logger.exception("Falha no K-means durante a calibração: %s", exc)
            self.is_fitted = False
            return

        self.centers = centers
        labels = labels.flatten()

        # Conta quantas amostras caíram em cada cluster.
        contagem = np.bincount(labels, minlength=self.k)

        # Os DOIS grupos MAIS populosos definem as cores dos times A e B (cada
        # time tem ~10-11 jogadores). Na classificação, cada jogador é atribuído
        # ao time de cor mais próxima; só quem está claramente longe dos DOIS
        # (juiz/goleiro de cor distinta) vira "outro".
        ordem = np.argsort(contagem)[::-1]  # do maior para o menor
        ca = centers[int(ordem[0])].astype(np.float32)
        cb = centers[int(ordem[1])].astype(np.float32)
        self.team_centers = np.stack([ca, cb])
        self.d_teams = float(np.linalg.norm(ca - cb))

        self.is_fitted = True
        logger.info(
            "TeamClassifier calibrado com %d amostras (distância entre times=%.1f).",
            len(cores),
            self.d_teams,
        )

    def classify(self, crop: np.ndarray) -> str:
        """Classifica um único jogador a partir de seu recorte.

        Args:
            crop: recorte (imagem BGR) do jogador.

        Returns:
            "A", "B", "goalkeeper" ou "unknown" se não calibrado/sem cor.
        """
        if not self.is_fitted or self.team_centers is None:
            # Sem calibração não há como atribuir time.
            return "unknown"

        cor = self._cor_central(crop)
        if cor is None:
            return "unknown"

        # Distância da cor a cada centro de TIME (A e B).
        dists = np.linalg.norm(self.team_centers - cor.astype(np.float32), axis=1)
        proximo = int(np.argmin(dists))

        # Só vira "outro" quem está claramente longe dos dois times (relativo à
        # distância entre eles). Caso contrário, assume o time mais próximo.
        if self.d_teams > 1e-6 and float(dists[proximo]) > self.outro_ratio * self.d_teams:
            return "outro"
        return "A" if proximo == 0 else "B"
