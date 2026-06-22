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
from typing import Callable, Dict, List, Optional, Tuple

import cv2

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


def _ler_video(caminho: str) -> Tuple[float, list]:
    """Lê todos os frames de um vídeo para memória.

    Returns:
        (fps, lista_de_frames).
    """
    cap = cv2.VideoCapture(caminho)
    if not cap.isOpened():
        raise IOError(f"Não foi possível abrir o vídeo: {caminho}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frames = []
    try:
        while True:
            ok, fr = cap.read()
            if not ok:
                break
            frames.append(fr)
    finally:
        cap.release()
    return (fps if fps > 0 else 25.0), frames


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

    # --- Leitura do vídeo ---
    fps, frames = _ler_video(video_path)
    if not frames:
        raise ValueError("Vídeo sem frames legíveis.")
    n = len(frames)
    altura, largura = frames[0].shape[:2]
    dt = 1.0 / fps
    logger.info("Processando %d frames (%dx%d @ %.2ffps).", n, largura, altura, fps)
    _progresso(2)

    # --- Calibração do classificador de time (primeiros frames) ---
    detector = YOLODetector()
    classifier = TeamClassifier(k=int(options.get("team_k", os.getenv("TEAM_K", "3"))))
    crops = []
    for fr in frames[:10]:
        for det in detector.detect(fr):
            if det.class_name == "person":
                x1, y1, x2, y2 = det.bbox
                c = fr[y1:y2, x1:x2]
                if c.size > 0:
                    crops.append(c)
    classifier.fit(crops)
    _progresso(5)

    # --- Homografia (calibrada se houver arquivo, senão fallback) ---
    mapper = HomographyMapper()
    mapper.set_frame_size(largura, altura)
    nome = os.path.splitext(os.path.basename(video_path))[0]
    cal = os.path.join(os.getenv("MODELS_DIR", "data/models"), f"calibration_{nome}.json")
    calibrado = os.path.exists(cal) and mapper.load_calibration(cal)

    # Compensação de câmera (ligada quando não há calibração de câmera fixa).
    comp = None if calibrado else CameraMotionCompensator()
    if comp is not None:
        comp.reset(frames[0])

    # --- Passo 1: rastreamento de todos os frames ---
    use_reid = bool(options.get("use_reid", os.getenv("USE_REID", "0") == "1"))
    tracker = PlayerTracker(use_reid=use_reid)
    frames_tracks: List[list] = []
    pos_por_id: Dict[int, list] = {}
    team_por_id: Dict[int, str] = {}

    for i, fr in enumerate(frames):
        tracks = tracker.update(fr, team_classifier=classifier)
        frames_tracks.append(tracks)
        if comp is not None:
            comp.update(fr, exclude_boxes=[t.bbox for t in tracks])
        for t in tracks:
            team_por_id[t.id] = t.team
            x1, y1, x2, y2 = t.bbox
            pe_x, pe_y = (x1 + x2) / 2.0, float(y2)
            if comp is not None:
                pe_x, pe_y = comp.transform_point(pe_x, pe_y)
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

    # --- Passo 3: renderizar o vídeo anotado ---
    with AnnotatedVideoWriter(output_path, fps, (largura, altura)) as writer:
        for i, fr in enumerate(frames):
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
