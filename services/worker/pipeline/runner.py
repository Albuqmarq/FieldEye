"""
runner.py — Motor reutilizável do pipeline de IA.

Empacota TODO o processamento (detecção -> tracking -> time -> física ->
consolidação -> vídeo anotado) numa única função `processar_video`, que pode
ser chamada tanto pelo teste manual quanto pela task Celery (Fase 7).

Boa prática: separar o "motor" (aqui) da "casca" (a task Celery / o teste).
Assim o mesmo código roda local e em produção, sem duplicação.
"""

import logging
import os
import subprocess
import tempfile
from typing import Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from pipeline.detector import YOLODetector
from pipeline.team_classifier import TeamClassifier
from pipeline.tracker import PlayerTracker
from pipeline.homography import HomographyMapper
from pipeline.camera_motion import CameraMotionCompensator
from pipeline import physics
from pipeline.interpolation import (
    interpolate_gaps,
    smooth_trajectory,
    reject_outliers,
)
from pipeline.consolidation import consolidar
from pipeline.video_writer import AnnotatedVideoWriter, Anotacao

logger = logging.getLogger(__name__)

# Teto físico de velocidade (km/h) — descarta saltos residuais.
TETO_KMH = 40.0

# Dimensões oficiais (comprimento x largura, em metros) por tipo de campo.
# Usadas quando o usuário escolhe "Campo oficial" (sem marcar a região).
FIELD_SIZES = {
    "futebol": (105.0, 68.0),
    "futsal": (40.0, 20.0),
    "society": (50.0, 30.0),
}


def _preset_modo(mode: str) -> dict:
    """Escolhe modelo/resolução/confiança do YOLO conforme o modo de análise.

    - "velocidade": modelo nano em baixa resolução — rápido, roda em qualquer
      CPU, mas perde jogadores pequenos/distantes.
    - "qualidade": modelo maior e resolução alta — detecta jogadores pequenos
      (câmera alta/tática), ao custo de bem mais tempo e memória (ideal com GPU).

    Todos os valores podem ser sobrescritos por variáveis de ambiente, para
    ajustar ao hardware sem tocar no código.
    """
    if mode == "qualidade":
        return {
            "model": os.getenv("MODEL_NAME_HQ", "yolov8s.pt"),
            "imgsz": int(os.getenv("YOLO_IMGSZ_HQ", "1280")),
            "conf": float(os.getenv("YOLO_CONF_HQ", "0.2")),
        }
    return {
        "model": os.getenv("MODEL_NAME", "yolov8n.pt"),
        "imgsz": int(os.getenv("YOLO_IMGSZ", "0")) or 640,
        "conf": float(os.getenv("YOLO_CONF", "0.3")),
    }


def _normalizar_cfr(caminho: str, fps: int = 25) -> str:
    """Reescreve o vídeo em frame rate CONSTANTE (CFR) para leitura confiável.

    Vídeos VFR (frame rate variável — ex.: 59.94 nominal / 23.66 real) fazem o
    OpenCV ler um número NÃO-determinístico de frames sob pressão de memória,
    truncando o resultado (o vídeo de saída sai mais curto que o original).
    Normalizar para CFR com o ffmpeg resolve: a leitura passa a ser completa e
    determinística. A resolução é preservada (não reescalona), então pontos de
    calibração marcados em pixels continuam válidos.

    Returns:
        Caminho do arquivo normalizado (temporário). Se o ffmpeg falhar,
        devolve o caminho ORIGINAL (melhor processar VFR do que nada).
    """
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.close()
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", caminho,
            "-vsync", "cfr", "-r", str(fps),
            "-c:v", "libx264", "-preset", "veryfast", "-an",
            tmp.name,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        logger.info("Vídeo normalizado para CFR %dfps: %s", fps, tmp.name)
        return tmp.name
    except Exception as exc:
        logger.warning("Falha ao normalizar CFR (%s) — usando o vídeo original.", exc)
        return caminho


def _meta_video(caminho: str) -> Tuple[float, int, int, int]:
    """Lê apenas os METADADOS do vídeo (sem carregar frames na memória).

    Returns:
        (fps, largura, altura, n_frames).
    """
    cap = cv2.VideoCapture(caminho)
    if not cap.isOpened():
        raise IOError(f"Não foi possível abrir o vídeo: {caminho}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    largura = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    altura = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return (fps if fps > 0 else 25.0), largura, altura, n


def _iter_frames(caminho: str):
    """Gera os frames do vídeo UM A UM (streaming), sem acumular na memória.

    Essencial para não estourar a RAM: um vídeo 1080p de 16s tem ~400 frames
    de ~6 MB cada (~2,5 GB se carregados juntos, o que matava o worker por
    falta de memória — SIGKILL). Em streaming, só um frame fica na RAM por vez.
    """
    cap = cv2.VideoCapture(caminho)
    if not cap.isOpened():
        raise IOError(f"Não foi possível abrir o vídeo: {caminho}")
    try:
        while True:
            ok, fr = cap.read()
            if not ok:
                break
            yield fr
    finally:
        cap.release()


def processar_video(
    video_path: str,
    output_path: str,
    options: Optional[dict] = None,
    progress_cb: Optional[Callable[[int], None]] = None,
) -> Dict:
    """Executa o pipeline completo de um vídeo e gera o vídeo anotado.

    Args:
        video_path: caminho do vídeo de entrada.
        output_path: caminho do vídeo anotado de saída (.mp4).
        options: dicionário opcional de ajustes (use_reid, team_k,
            cons_min_frames, cons_min_dist, cons_max_gap, cons_max_dist).
        progress_cb: função chamada com o progresso (0..100) ao longo do
            processamento. Útil para a task Celery atualizar o banco.

    Returns:
        Dicionário com os resultados:
            {
              "fps": float,
              "n_frames": int,
              "players": [
                 {"player_id", "team", "frames", "total_distance",
                  "max_speed", "avg_speed", "sprints",
                  "trajectory": [{"frame","x","y","speed"}, ...]},
                 ...
              ]
            }
    """
    options = options or {}

    def _progresso(p: int) -> None:
        if progress_cb is not None:
            try:
                progress_cb(int(p))
            except Exception:  # progresso nunca pode derrubar o processamento
                logger.warning("Falha ao reportar progresso.", exc_info=True)

    # --- Normalização CFR + metadados (processamento em STREAMING) ---
    # Normaliza para frame rate constante (evita truncar vídeos VFR) e lê só os
    # METADADOS. Os frames são lidos um a um (streaming) nas etapas seguintes,
    # para não estourar a RAM — carregar todos de uma vez matava o worker (OOM).
    video_norm = _normalizar_cfr(video_path)
    fps, largura, altura, n = _meta_video(video_norm)
    if n <= 0:  # alguns contêineres não reportam a contagem; conta em streaming
        n = sum(1 for _ in _iter_frames(video_norm))
    if n <= 0:
        raise ValueError("Vídeo sem frames legíveis.")
    dt = 1.0 / fps
    logger.info("Processando %d frames (%dx%d @ %.2ffps) em streaming.", n, largura, altura, fps)
    _progresso(2)

    # --- Calibração do classificador de time (primeiros frames) ---
    # Modo de análise (velocidade/qualidade) define modelo, resolução e confiança.
    preset = _preset_modo(options.get("mode", "velocidade"))
    logger.info("Modo '%s': modelo=%s imgsz=%d conf=%.2f",
                options.get("mode", "velocidade"), preset["model"], preset["imgsz"], preset["conf"])
    detector = YOLODetector(model_name=preset["model"], confidence=preset["conf"], imgsz=preset["imgsz"])
    classifier = TeamClassifier(k=int(options.get("team_k", os.getenv("TEAM_K", "4"))))
    crops = []
    primeiro_frame = None
    for idx, fr in enumerate(_iter_frames(video_norm)):
        if idx == 0:
            primeiro_frame = fr.copy()  # guardado para a compensação de câmera
        if idx >= 10:
            break
        for det in detector.detect(fr):
            if det.class_name == "person":
                x1, y1, x2, y2 = det.bbox
                c = fr[y1:y2, x1:x2]
                if c.size > 0:
                    crops.append(c)
    classifier.fit(crops)
    _progresso(5)

    # --- Homografia (arquivo salvo > pontos marcados pelo usuário > fallback) ---
    # Dimensões do campo: "Campo oficial" define o tipo (futebol/futsal/society);
    # caso contrário, assume um campo de futebol padrão (105x68 m).
    field_size = FIELD_SIZES.get(options.get("field_type", ""), (105.0, 68.0))
    mapper = HomographyMapper(field_size=field_size)
    mapper.set_frame_size(largura, altura)
    nome = os.path.splitext(os.path.basename(video_path))[0]
    cal = os.path.join(os.getenv("MODELS_DIR", "data/models"), f"calibration_{nome}.json")
    calibrado_arquivo = os.path.exists(cal) and mapper.load_calibration(cal)

    # Calibração interativa: 4 cantos do campo marcados no 1º frame (px do vídeo).
    # Mapeamos para o retângulo do campo em metros; distâncias/velocidades são
    # invariantes à orientação, então basta uma correspondência consistente.
    calibrado_marcado = False
    pontos_img = options.get("field_points")
    if not calibrado_arquivo and isinstance(pontos_img, list) and len(pontos_img) == 4:
        cantos_campo = [
            (0.0, 0.0),
            (mapper.field_length, 0.0),
            (mapper.field_length, mapper.field_width),
            (0.0, mapper.field_width),
        ]
        try:
            pts = [(float(p[0]), float(p[1])) for p in pontos_img]
            calibrado_marcado = mapper.set_keypoints(pts, cantos_campo)
        except (TypeError, ValueError, IndexError):
            logger.warning("field_points inválidos — usando fallback de escala.")

    # Filtro de região: quando o usuário marca os 4 cantos, só analisamos quem
    # está DENTRO desse polígono (descarta torcida, banco de reservas e qualquer
    # pessoa fora da área marcada — o que sujava a análise).
    roi_poligono = None
    if options.get("area") == "regiao" and isinstance(pontos_img, list) and len(pontos_img) == 4:
        try:
            roi_poligono = np.array(
                [[float(p[0]), float(p[1])] for p in pontos_img], dtype=np.float32
            )
        except (TypeError, ValueError, IndexError):
            roi_poligono = None

    # Compensação de câmera: mantida quando NÃO há calibração de câmera fixa em
    # arquivo. Com a marcação no 1º frame, a compensação mapeia todos os frames
    # de volta a esse frame de referência (onde a homografia foi definida).
    comp = None if calibrado_arquivo else CameraMotionCompensator()
    if comp is not None and primeiro_frame is not None:
        comp.reset(primeiro_frame)

    # --- Passo 1: rastreamento de todos os frames ---
    use_reid = bool(options.get("use_reid", os.getenv("USE_REID", "0") == "1"))
    tracker = PlayerTracker(
        use_reid=use_reid, model_name=preset["model"],
        confidence=preset["conf"], imgsz=preset["imgsz"],
    )
    frames_tracks: List[list] = []
    pos_por_id: Dict[int, list] = {}
    team_por_id: Dict[int, str] = {}

    for i, fr in enumerate(_iter_frames(video_norm)):
        if i >= n:  # segurança: não ultrapassa o tamanho pré-alocado das séries
            break
        tracks = tracker.update(fr, team_classifier=classifier)
        frames_tracks.append(tracks)
        if comp is not None:
            comp.update(fr, exclude_boxes=[t.bbox for t in tracks])
        for t in tracks:
            x1, y1, x2, y2 = t.bbox
            pe_x, pe_y = (x1 + x2) / 2.0, float(y2)
            if comp is not None:
                pe_x, pe_y = comp.transform_point(pe_x, pe_y)
            # Fora da área marcada? Ignora este jogador neste frame.
            if roi_poligono is not None and cv2.pointPolygonTest(
                roi_poligono, (float(pe_x), float(pe_y)), False
            ) < 0:
                continue
            team_por_id[t.id] = t.team
            pos_por_id.setdefault(t.id, [None] * n)[i] = mapper.pixel_to_meters(pe_x, pe_y)

        # Rastreamento ocupa a maior parte do tempo: progresso de 5% a 80%.
        if i % 10 == 0:
            _progresso(5 + int(75 * i / max(1, n)))

    _progresso(80)

    # --- Passo 1.5: consolidação automática (costura + filtro de ruído) ---
    pos_consolidado, id_map = consolidar(
        pos_por_id, team_por_id, n,
        max_gap_frames=int(options.get("cons_max_gap", os.getenv("CONS_MAX_GAP", "45"))),
        max_dist_m=float(options.get("cons_max_dist", os.getenv("CONS_MAX_DIST", "5.0"))),
        min_frames=int(options.get("cons_min_frames", os.getenv("CONS_MIN_FRAMES", "15"))),
        min_distancia=float(options.get("cons_min_dist", os.getenv("CONS_MIN_DIST", "2.0"))),
    )

    # Time consolidado: voto majoritário por frames.
    votos = {}
    for orig, canon in id_map.items():
        if canon not in pos_consolidado:
            continue
        t = team_por_id.get(orig, "unknown")
        nf = sum(1 for p in pos_por_id[orig] if p is not None)
        votos.setdefault(canon, {})
        votos[canon][t] = votos[canon].get(t, 0) + nf
    team_final = {}
    for canon, v in votos.items():
        cand = {k: c for k, c in v.items() if k != "unknown"} or v
        team_final[canon] = max(cand, key=cand.get)

    pos_por_id = pos_consolidado
    team_por_id = team_final
    _progresso(85)

    # --- Passo 2: limpar trajetórias e calcular velocidades ---
    speed_por_id: Dict[int, list] = {}
    for pid, traj in pos_por_id.items():
        traj = reject_outliers(traj, dt, max_speed_kmh=TETO_KMH)
        traj = interpolate_gaps(traj, max_gap=45)
        traj = smooth_trajectory(traj, window=5)
        pos_por_id[pid] = traj

        speeds = [None] * n
        anterior = None
        for i, p in enumerate(traj):
            if p is not None and anterior is not None:
                v = physics.calculate_speed(anterior, p, dt)
                speeds[i] = v if v <= TETO_KMH else None
            anterior = p if p is not None else anterior
        speed_por_id[pid] = speeds
    _progresso(88)

    # --- Passo 3: renderizar o vídeo anotado (streaming) ---
    with AnnotatedVideoWriter(output_path, fps, (largura, altura)) as writer:
        for i, fr in enumerate(_iter_frames(video_norm)):
            if i >= len(frames_tracks):
                break
            anotacoes = []
            for t in frames_tracks[i]:
                final = id_map.get(t.id)
                if final is None:
                    continue
                v = speed_por_id.get(final, [None] * n)[i]
                anotacoes.append(
                    Anotacao(track_id=final, bbox=t.bbox,
                             team=team_por_id.get(final, t.team), speed=v)
                )
            writer.write_frame(fr, anotacoes, timestamp=i / fps)
            if i % 30 == 0:
                _progresso(88 + int(11 * i / max(1, n)))

    # Renderização concluída: remove o vídeo normalizado temporário.
    if video_norm != video_path and os.path.exists(video_norm):
        try:
            os.remove(video_norm)
        except OSError:
            pass

    # --- Monta o resultado estruturado ---
    players = []
    for pid in sorted(pos_por_id.keys()):
        traj = pos_por_id[pid]
        speeds = speed_por_id[pid]
        vels = [v for v in speeds if v is not None]
        # Série temporal (frame, x, y, speed) só nos frames com posição.
        trajetoria = []
        for i, p in enumerate(traj):
            if p is not None:
                trajetoria.append({
                    "frame": i,
                    "x": round(p[0], 2),
                    "y": round(p[1], 2),
                    "speed": round(speeds[i], 1) if speeds[i] is not None else None,
                })
        players.append({
            "player_id": int(pid),
            "team": team_por_id.get(pid, "unknown"),
            "frames": sum(1 for p in traj if p is not None),
            "total_distance": round(physics.calculate_total_distance(traj), 1),
            "max_speed": round(max(vels), 1) if vels else 0.0,
            "avg_speed": round(sum(vels) / len(vels), 1) if vels else 0.0,
            "sprints": physics.calculate_sprint_count(vels),
            "trajectory": trajetoria,
        })

    _progresso(100)
    logger.info("Pipeline concluído: %d jogadores, vídeo em %s.", len(players), output_path)
    return {"fps": fps, "n_frames": n, "players": players}
