"""
tracker.py — Rastreamento de jogadores com BoT-SORT + ReID.

Etapa 4 do pipeline. Depois de detectar jogadores em cada frame, precisamos
dar a cada um uma IDENTIDADE persistente ao longo do vídeo — inclusive
quando dois jogadores se cruzam (oclusão).

Usamos BoT-SORT (via ultralytics), que combina Filtro de Kalman (previsão de
movimento) com ReID opcional (re-identificação por aparência visual). O ReID
é desligado por padrão para rodar rápido em CPU e ligado em produção com GPU.

Observação de arquitetura:
    No ultralytics, o BoT-SORT é INTEGRADO ao modelo: detecção e rastreamento
    ocorrem na mesma chamada `model.track()`. Por isso o PlayerTracker carrega
    seu próprio modelo YOLO e o método update() recebe o frame (não detecções
    externas). Mantemos, além disso, uma `reid_gallery` própria de aparência
    para logar quando um ID reaparece após oclusão.
"""

import logging
import os
import tempfile
from dataclasses import dataclass
from typing import List, Optional

import cv2
import numpy as np
from ultralytics import YOLO

logger = logging.getLogger(__name__)

# Mesmo diretório de modelos usado pelo detector (convenção do projeto).
MODELS_DIR = os.getenv("MODELS_DIR", os.path.join("data", "models"))

# IDs de classe no dataset COCO: pessoa=0, bola=32.
CLASSE_PESSOA = 0
CLASSE_BOLA = 32


@dataclass
class Track:
    """Representa um jogador rastreado em um frame.

    Atributos:
        id: identificador persistente do jogador ao longo do vídeo.
        bbox: caixa delimitadora (x1, y1, x2, y2) em pixels.
        team: time atribuído ("A", "B", "goalkeeper" ou "unknown").
    """

    id: int
    bbox: tuple
    team: str


class PlayerTracker:
    """Rastreador de jogadores baseado em BoT-SORT.

    Atributos principais:
        use_reid: liga/desliga o ReID do BoT-SORT (custo extra de CPU/GPU).
        reid_gallery: {track_id: histograma_de_aparência} — memória visual
            da última aparência conhecida de cada jogador. Usada para detectar
            e logar re-associações de ID após oclusão.
    """

    def __init__(
        self,
        use_reid: bool = False,
        model_name: str = None,
        track_buffer: int = 45,
        match_thresh: float = 0.7,
        reid_threshold: float = 0.6,
        confidence: float = None,
        imgsz: int = None,
    ):
        """Inicializa o rastreador.

        Args:
            use_reid: se True, ativa o modelo de ReID do BoT-SORT (máxima
                precisão, mais lento — ideal para GPU). Se False, desativa
                o ReID para economizar processamento em CPU.
            model_name: peso YOLO a usar (mesmo da detecção).
            track_buffer: por quantos frames manter vivo um track perdido
                (oclusão). Maior = tolera oclusões mais longas.
            match_thresh: limiar de similaridade para associar detecção a track.
            reid_threshold: limiar de similaridade de aparência para considerar
                que um ID reaparecido é o mesmo jogador.
            confidence: confiança mínima nas detecções.
        """
        self.use_reid = use_reid
        self.track_buffer = track_buffer
        self.match_thresh = match_thresh
        self.reid_threshold = reid_threshold
        # Mesmas variáveis de ambiente do detector, para usar o mesmo modelo.
        model_name = model_name or os.getenv("MODEL_NAME", "yolov8n.pt")
        self.confidence = confidence if confidence is not None else float(os.getenv("YOLO_CONF", "0.3"))
        self.imgsz = imgsz if imgsz is not None else int(os.getenv("YOLO_IMGSZ", "0"))

        # Carrega o modelo YOLO (reutiliza o peso baixado na Fase 2).
        os.makedirs(MODELS_DIR, exist_ok=True)
        model_path = os.path.join(MODELS_DIR, model_name)
        try:
            if os.path.exists(model_path):
                self.model = YOLO(model_path)
            else:
                # Se ainda não houver peso local, o ultralytics baixa.
                self.model = YOLO(model_name)
        except Exception as exc:
            logger.exception("Falha ao carregar modelo YOLO no tracker: %s", exc)
            raise

        # Gera o arquivo de configuração do BoT-SORT com nossos parâmetros.
        self.cfg_path = self._gerar_config_botsort()

        # Estruturas de memória de identidade.
        self.reid_gallery: dict = {}      # {track_id: histograma de aparência}
        self.active_ids: set = set()      # IDs presentes no frame anterior
        self.seen_ids: set = set()        # todos os IDs já vistos no vídeo

        logger.info(
            "PlayerTracker pronto (use_reid=%s, track_buffer=%d, match_thresh=%.2f).",
            self.use_reid,
            self.track_buffer,
            self.match_thresh,
        )

    def _gerar_config_botsort(self) -> str:
        """Escreve um YAML de configuração do BoT-SORT em arquivo temporário.

        Traduz nossos parâmetros para os nomes esperados pelo ultralytics e
        liga/desliga o ReID conforme `use_reid`.

        Returns:
            Caminho do arquivo .yaml gerado.
        """
        # appearance_thresh do ultralytics corresponde ao nosso reid_threshold.
        conteudo = (
            "tracker_type: botsort\n"
            "track_high_thresh: 0.25\n"
            "track_low_thresh: 0.1\n"
            "new_track_thresh: 0.25\n"
            f"track_buffer: {self.track_buffer}\n"
            f"match_thresh: {self.match_thresh}\n"
            "fuse_score: True\n"
            "gmc_method: sparseOptFlow\n"
            "proximity_thresh: 0.5\n"
            f"appearance_thresh: {self.reid_threshold}\n"
            f"with_reid: {self.use_reid}\n"
            "model: auto\n"
        )
        # delete=False para o arquivo sobreviver enquanto o tracker existir.
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix="_botsort.yaml", delete=False, encoding="utf-8"
        )
        tmp.write(conteudo)
        tmp.close()
        logger.info("Config BoT-SORT gerada em %s (with_reid=%s).", tmp.name, self.use_reid)
        return tmp.name

    def _histograma_aparencia(self, crop: np.ndarray) -> Optional[np.ndarray]:
        """Calcula um histograma de cor (HSV) como descritor de aparência.

        Esse histograma é a nossa "assinatura visual" simplificada do jogador,
        usada para a galeria de ReID. (O ReID pesado de fato é feito pelo
        BoT-SORT internamente quando use_reid=True; aqui mantemos uma memória
        própria para detectar e logar reaparições.)

        Args:
            crop: recorte BGR do jogador.

        Returns:
            Histograma normalizado (numpy) ou None se o crop for inválido.
        """
        if crop is None or crop.size == 0:
            return None
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        # Histograma 2D de matiz (H) e saturação (S).
        hist = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
        return hist.flatten()

    def _similaridade(self, hist_a: np.ndarray, hist_b: np.ndarray) -> float:
        """Compara dois histogramas de aparência (correlação 0..1)."""
        return float(
            cv2.compareHist(
                hist_a.astype(np.float32),
                hist_b.astype(np.float32),
                cv2.HISTCMP_CORREL,
            )
        )

    def update(self, frame: np.ndarray, team_classifier=None) -> List[Track]:
        """Processa um frame e devolve os jogadores rastreados.

        Args:
            frame: imagem BGR do frame atual.
            team_classifier: instância opcional de TeamClassifier (já calibrada)
                para preencher o campo `team` de cada Track.

        Returns:
            Lista de Track (id, bbox, team).
        """
        if frame is None or not isinstance(frame, np.ndarray):
            logger.error("update() recebeu frame inválido.")
            return []

        try:
            # persist=True mantém o estado do tracker entre chamadas (frames).
            # classes restringe a pessoas e bola.
            kwargs = {
                "persist": True,
                "tracker": self.cfg_path,
                "conf": self.confidence,
                "classes": [CLASSE_PESSOA, CLASSE_BOLA],
                "verbose": False,
            }
            if self.imgsz and self.imgsz > 0:
                kwargs["imgsz"] = self.imgsz
            resultados = self.model.track(frame, **kwargs)
        except Exception as exc:
            logger.exception("Erro durante o rastreamento BoT-SORT: %s", exc)
            return []

        tracks: List[Track] = []
        ids_atuais: set = set()

        resultado = resultados[0]
        # Se nada foi rastreado neste frame, registramos sumiços e saímos.
        if resultado.boxes is None or resultado.boxes.id is None:
            self._registrar_sumicos(ids_atuais)
            self.active_ids = ids_atuais
            return tracks

        for box in resultado.boxes:
            # Só processamos caixas que receberam um ID de track.
            if box.id is None:
                continue
            track_id = int(box.id[0])
            class_id = int(box.cls[0])

            x1, y1, x2, y2 = box.xyxy[0].tolist()
            bbox = (int(x1), int(y1), int(x2), int(y2))
            ids_atuais.add(track_id)

            # Recorte do jogador para aparência + classificação de time.
            crop = frame[bbox[1]:bbox[3], bbox[0]:bbox[2]]
            hist = self._histograma_aparencia(crop)

            # Classificação de time (só faz sentido para pessoas).
            team = "unknown"
            if class_id == CLASSE_PESSOA and team_classifier is not None:
                try:
                    team = team_classifier.classify(crop)
                except Exception as exc:  # nunca deixar a classificação quebrar o tracking
                    logger.warning("Falha ao classificar time do track %d: %s", track_id, exc)

            # Lógica de identidade: novo, reaparecido (após oclusão) ou contínuo.
            self._atualizar_identidade(track_id, hist)

            tracks.append(Track(id=track_id, bbox=bbox, team=team))

        # Detecta quem sumiu em relação ao frame anterior.
        self._registrar_sumicos(ids_atuais)
        self.active_ids = ids_atuais
        return tracks

    def _atualizar_identidade(self, track_id: int, hist: Optional[np.ndarray]) -> None:
        """Atualiza a galeria de ReID e loga entradas/reaparições.

        Args:
            track_id: ID do track no frame atual.
            hist: histograma de aparência atual (pode ser None).
        """
        if track_id not in self.seen_ids:
            # Jogador nunca visto antes: entrou em cena.
            logger.info("Novo jogador entrou em cena: ID %d.", track_id)
            self.seen_ids.add(track_id)
        elif track_id not in self.active_ids:
            # ID conhecido que estava ausente e voltou: reaparição após oclusão.
            similaridade = -1.0
            if hist is not None and track_id in self.reid_gallery:
                similaridade = self._similaridade(self.reid_gallery[track_id], hist)
            if similaridade >= self.reid_threshold:
                logger.info(
                    "Jogador ID %d re-associado após oclusão (similaridade=%.2f).",
                    track_id,
                    similaridade,
                )
            else:
                logger.info(
                    "Jogador ID %d reapareceu após oclusão (similaridade=%.2f, abaixo do limiar).",
                    track_id,
                    similaridade,
                )

        # Atualiza a galeria com a aparência mais recente.
        if hist is not None:
            self.reid_gallery[track_id] = hist

    def _registrar_sumicos(self, ids_atuais: set) -> None:
        """Loga jogadores que estavam presentes e sumiram neste frame."""
        sumiram = self.active_ids - ids_atuais
        for sid in sumiram:
            logger.info("Jogador ID %d saiu de cena (possível oclusão).", sid)

    def __del__(self):
        """Remove o arquivo de config temporário ao destruir o tracker."""
        try:
            if hasattr(self, "cfg_path") and os.path.exists(self.cfg_path):
                os.remove(self.cfg_path)
        except OSError:
            pass
