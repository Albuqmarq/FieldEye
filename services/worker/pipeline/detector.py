"""Detecção de jogadores e bola com YOLOv8."""

import logging
import os
import shutil
from dataclasses import dataclass
from typing import List

import numpy as np
from ultralytics import YOLO

# Logger do módulo — usamos logging em vez de print (convenção do projeto)
logger = logging.getLogger(__name__)

# Diretório onde o peso do modelo é baixado/armazenado.
# Pode ser sobrescrito via variável de ambiente (convenção do projeto).
MODELS_DIR = os.getenv("MODELS_DIR", os.path.join("data", "models"))

# Classes do dataset COCO que nos interessam no futebol.
# O YOLOv8 pré-treinado em COCO usa esses nomes exatos.
CLASSES_DE_INTERESSE = {"person", "sports ball"}


@dataclass
class Detection:
    """Representa uma única detecção em um frame.

    Atributos:
        bbox: caixa delimitadora no formato (x1, y1, x2, y2) em pixels.
        confidence: confiança da detecção (0.0 a 1.0).
        class_name: nome da classe detectada ("person" ou "sports ball").
    """

    bbox: tuple  # (x1, y1, x2, y2)
    confidence: float
    class_name: str


class YOLODetector:
    """Detector de jogadores e bola baseado no YOLOv8.

    Carrega o modelo YOLOv8n (versão "nano", leve o suficiente para rodar
    em CPU durante os testes). Se o peso ainda não existir em disco, o
    ultralytics o baixa automaticamente na primeira execução.
    """

    def __init__(self, model_name: str = None, confidence: float = None, imgsz: int = None, device: str = None):
        """Inicializa o detector.

        Todos os parâmetros podem ser sobrescritos por variáveis de ambiente,
        permitindo trocar o modelo/resolução sem mexer no código:
            MODEL_NAME  -> ex.: "yolov8x.pt" para câmera tática aberta
            YOLO_CONF   -> confiança mínima (ex.: 0.15)
            YOLO_IMGSZ  -> resolução de inferência (ex.: 2560 p/ jogadores pequenos)

        Args:
            model_name: nome/arquivo do modelo YOLO. Padrão: yolov8n.pt (leve).
            confidence: confiança mínima para aceitar uma detecção.
            imgsz: resolução de inferência. 0/None usa o padrão do modelo (640).
        """
        # Resolve cada parâmetro: argumento explícito > variável de ambiente > padrão.
        model_name = model_name or os.getenv("MODEL_NAME", "yolov8n.pt")
        self.confidence = confidence if confidence is not None else float(os.getenv("YOLO_CONF", "0.3"))
        self.imgsz = imgsz if imgsz is not None else int(os.getenv("YOLO_IMGSZ", "0"))
        # Dispositivo de inferência: "cuda:0" (GPU), "cpu" ou None (automático).
        self.device = device

        # Garante que o diretório de modelos exista antes de baixar o peso.
        os.makedirs(MODELS_DIR, exist_ok=True)

        # Caminho final do peso dentro de data/models/.
        model_path = os.path.join(MODELS_DIR, model_name)

        try:
            # Se o peso já estiver baixado em data/models/, usamos ele.
            # Caso contrário, passamos só o nome e o ultralytics baixa
            # automaticamente (e nós movemos/baixamos para MODELS_DIR).
            if os.path.exists(model_path):
                logger.info("Carregando modelo YOLO de %s", model_path)
                self.model = YOLO(model_path)
            else:
                logger.info(
                    "Modelo %s não encontrado em %s — será baixado automaticamente.",
                    model_name,
                    MODELS_DIR,
                )
                # YOLO baixa o peso no diretório atual; depois o movemos.
                self.model = YOLO(model_name)
                self._persistir_modelo(model_name, model_path)
        except Exception as exc:
            # Falha ao carregar/baixar o modelo é fatal para o pipeline.
            logger.exception("Falha ao carregar o modelo YOLO: %s", exc)
            raise

        # Mapa {índice_da_classe: nome} fornecido pelo próprio modelo.
        self.names = self.model.names
        logger.info("YOLODetector pronto (confiança mínima=%.2f).", self.confidence)

    def _persistir_modelo(self, model_name: str, destino: str) -> None:
        """Move o peso recém-baixado para data/models/ (se necessário).

        O ultralytics baixa o .pt no diretório de trabalho atual. Para manter
        a organização do projeto, movemos para MODELS_DIR.
        """
        try:
            if os.path.exists(model_name) and not os.path.exists(destino):
                # shutil.move (e não os.replace) para funcionar entre discos
                # diferentes: os dados ficam em D: e o /app no disco do container.
                shutil.move(model_name, destino)
                logger.info("Peso do modelo movido para %s", destino)
        except OSError as exc:
            # Não é fatal: o modelo já está em memória e funciona mesmo assim.
            logger.warning("Não foi possível mover o peso para %s: %s", destino, exc)

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """Detecta pessoas e bola em um frame.

        Args:
            frame: imagem BGR (numpy array) como o OpenCV devolve.

        Returns:
            Lista de objetos Detection já filtrados pelas classes de interesse.
        """
        if frame is None or not isinstance(frame, np.ndarray):
            # Frame inválido: registramos e devolvemos lista vazia em vez de quebrar.
            logger.error("detect() recebeu um frame inválido (None ou tipo errado).")
            return []

        try:
            # verbose=False evita que o ultralytics imprima no stdout (usamos logging).
            # imgsz só é passado quando configurado (>0); senão usa o padrão do modelo.
            kwargs = {"conf": self.confidence, "verbose": False}
            if self.imgsz and self.imgsz > 0:
                kwargs["imgsz"] = self.imgsz
            if self.device:
                kwargs["device"] = self.device
            resultados = self.model(frame, **kwargs)
        except Exception as exc:
            logger.exception("Erro durante a inferência do YOLO: %s", exc)
            return []

        deteccoes: List[Detection] = []

        # O ultralytics devolve uma lista de Results (um por imagem).
        for resultado in resultados:
            # boxes pode ser None se nada for detectado.
            if resultado.boxes is None:
                continue

            for box in resultado.boxes:
                # Índice da classe detectada e seu nome textual.
                class_id = int(box.cls[0])
                class_name = self.names.get(class_id, str(class_id))

                # Filtra apenas pessoas e bola — descarta o resto do COCO.
                if class_name not in CLASSES_DE_INTERESSE:
                    continue

                # Coordenadas da caixa em formato (x1, y1, x2, y2).
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])

                deteccoes.append(
                    Detection(
                        bbox=(int(x1), int(y1), int(x2), int(y2)),
                        confidence=conf,
                        class_name=class_name,
                    )
                )

        # Log do número de detecções por frame (exigido pela especificação).
        logger.info("Frame processado: %d detecções encontradas.", len(deteccoes))
        return deteccoes
