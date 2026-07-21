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
from pipeline.homography import HomographyMapper
from pipeline import physics
from pipeline.interpolation import (
    interpolate_gaps,
    smooth_trajectory,
    reject_outliers,
    contar_gaps,
)
from pipeline.video_writer import AnnotatedVideoWriter, Anotacao
from pipeline.camera_motion import CameraMotionCompensator
from pipeline.consolidation import consolidar

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
    # n <= 0 significa "ler o vídeo inteiro".
    ler_tudo = n <= 0
    try:
        while ler_tudo or len(frames) < n:
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


def obter_fps(caminho: str) -> float:
    """Lê a taxa de quadros (fps) do vídeo. Usa 25.0 como padrão se falhar."""
    cap = cv2.VideoCapture(caminho)
    fps = cap.get(cv2.CAP_PROP_FPS) if cap.isOpened() else 0.0
    cap.release()
    return fps if fps and fps > 0 else 25.0


def testar_fisica(frames, classifier: TeamClassifier, fps: float):
    """Roda detecção + rastreamento + física e imprime velocidades/distâncias.

    Para cada jogador rastreado, usamos o ponto dos PÉS (centro inferior da
    caixa) como sua posição no campo, convertemos para metros (homografia em
    modo fallback, pois não há calibração no teste) e calculamos velocidade
    instantânea e distância total.

    Args:
        frames: lista de frames (BGR).
        classifier: TeamClassifier já calibrado.
        fps: quadros por segundo do vídeo (define o dt entre frames).
    """
    logger.info("==================================================")
    logger.info("FASE 4 — FÍSICA (velocidade/distância) em %d frames", len(frames))
    logger.info("==================================================")

    tracker = PlayerTracker(use_reid=False)
    mapper = HomographyMapper()
    if frames:
        h, w = frames[0].shape[:2]
        mapper.set_frame_size(w, h)

    # dt (segundos entre frames consecutivos) = 1 / fps.
    dt = 1.0 / fps
    logger.info("fps=%.2f -> dt=%.4fs entre frames.", fps, dt)

    # Estruturas por jogador (track_id).
    posicoes = {}        # {id: [(x_m, y_m), ...]} histórico de posições
    ultima_pos = {}      # {id: (x_m, y_m)} última posição conhecida
    velocidades = {}     # {id: [v_kmh, ...]} histórico de velocidades
    times = {}           # {id: "A"/"B"/...}

    for i, frame in enumerate(frames):
        tracks = tracker.update(frame, team_classifier=classifier)
        linha = []
        for t in tracks:
            x1, y1, x2, y2 = t.bbox
            # Posição dos pés: centro horizontal, base da caixa.
            pe_x = (x1 + x2) / 2.0
            pe_y = float(y2)
            pos_m = mapper.pixel_to_meters(pe_x, pe_y)

            times[t.id] = t.team
            posicoes.setdefault(t.id, []).append(pos_m)

            # Velocidade instantânea em relação ao frame anterior.
            v = 0.0
            if t.id in ultima_pos:
                v = physics.calculate_speed(ultima_pos[t.id], pos_m, dt)
            velocidades.setdefault(t.id, []).append(v)
            ultima_pos[t.id] = pos_m

            linha.append(f"#{t.id}={v:4.1f}")

        # Velocidade instantânea de cada jogador neste frame (km/h).
        logger.info("Frame %d | velocidades(km/h): %s", i, "  ".join(linha))

    # Resumo por jogador ao final
    logger.info("---------- RESUMO POR JOGADOR ----------")
    for pid in sorted(posicoes.keys()):
        dist = physics.calculate_total_distance(posicoes[pid])
        vmax = max(velocidades[pid]) if velocidades[pid] else 0.0
        vmed = (sum(velocidades[pid]) / len(velocidades[pid])) if velocidades[pid] else 0.0
        sprints = physics.calculate_sprint_count(velocidades[pid])
        logger.info(
            "Jogador #%d (time %s): distância=%.1fm | v_máx=%.1f km/h | v_méd=%.1f km/h | sprints=%d",
            pid,
            times.get(pid, "?"),
            dist,
            vmax,
            vmed,
            sprints,
        )

    # Demonstra a geração de heatmap para um jogador (o primeiro).
    if posicoes:
        primeiro = sorted(posicoes.keys())[0]
        hm = physics.generate_heatmap(posicoes[primeiro])
        logger.info(
            "Heatmap do jogador #%d gerado: matriz %s, densidade máx=%.2f.",
            primeiro,
            hm.shape,
            float(hm.max()),
        )


def _carregar_calibracao(mapper: HomographyMapper, caminho_video: str) -> bool:
    """Tenta carregar uma calibração salva para este vídeo (modo misto).

    Se existir data/models/calibration_<nome>.json, usa o modo CALIBRADO
    (preciso). Caso contrário, o mapper fica em modo APROXIMADO (fallback).

    Returns:
        True se carregou calibração, False se ficará em fallback.
    """
    nome = os.path.splitext(os.path.basename(caminho_video))[0]
    cal = os.path.join("..", "..", "data", "models", f"calibration_{nome}.json")
    if os.path.exists(cal) and mapper.load_calibration(cal):
        logger.info("Modo CALIBRADO (preciso) — usando %s.", cal)
        return True
    logger.info("Modo APROXIMADO (fallback) — sem calibração para este vídeo.")
    return False


def testar_pipeline_completo(caminho: str, n_frames: int = 300):
    """Pipeline completo de ponta a ponta -> gera o vídeo anotado oficial.

    Etapas: detecção -> rastreamento -> classificação de time -> física ->
    interpolação de gaps -> renderização do vídeo anotado.

    Args:
        caminho: caminho do vídeo de entrada.
        n_frames: quantos frames processar (limite para manter o teste ágil).
    """
    logger.info("==================================================")
    logger.info("FASE 5 — PIPELINE COMPLETO (vídeo anotado)")
    logger.info("==================================================")

    fps = obter_fps(caminho)
    frames = ler_frames_para_lista(caminho, n_frames)
    if not frames:
        logger.error("Nenhum frame lido — abortando pipeline completo.")
        return
    altura, largura = frames[0].shape[:2]
    n = len(frames)
    logger.info("%d frames (%dx%d @ %.2ffps).", n, largura, altura, fps)

    # Calibração de time (usa os primeiros frames)
    detector = YOLODetector()
    # TEAM_K: nº de grupos de cor. 3 p/ futebol (A/B/goleiro); 2 p/ dois
    # corredores com roupas diferentes, etc.
    classifier = TeamClassifier(k=int(os.getenv("TEAM_K", "3")))
    crops = []
    for fr in frames[:10]:
        for det in detector.detect(fr):
            if det.class_name == "person":
                x1, y1, x2, y2 = det.bbox
                c = fr[y1:y2, x1:x2]
                if c.size > 0:
                    crops.append(c)
    classifier.fit(crops)

    # Homografia (modo misto: calibrado se houver arquivo, senão fallback)
    mapper = HomographyMapper()
    mapper.set_frame_size(largura, altura)
    calibrado = _carregar_calibracao(mapper, caminho)

    # Compensação de movimento de câmera: ligada no modo aproximado (câmera
    # móvel/ao vivo). No modo calibrado (câmera fixa) não é necessária.
    usar_comp = not calibrado
    comp = CameraMotionCompensator() if usar_comp else None
    if comp is not None:
        comp.reset(frames[0])
        logger.info("Compensação de movimento de câmera: LIGADA.")
    else:
        logger.info("Compensação de movimento de câmera: DESLIGADA (modo calibrado).")

    # Passo 1: rastrear todos os frames, guardando bbox/time/posição
    # USE_REID=1 liga a re-identificação por aparência (melhora oclusões, ex.:
    # duas pessoas se cruzando). Mais pesado, mas mantém os IDs corretos.
    usar_reid = os.getenv("USE_REID", "0") == "1"
    tracker = PlayerTracker(use_reid=usar_reid)
    frames_tracks = []            # frames_tracks[i] = lista de Track do frame i
    pos_por_id = {}               # {id: [pos_m ou None] por frame}
    team_por_id = {}              # {id: time}
    frames_vistos = {}            # {id: nº de frames em que apareceu}

    for i, fr in enumerate(frames):
        tracks = tracker.update(fr, team_classifier=classifier)
        frames_tracks.append(tracks)

        # Estima o movimento da câmera deste frame (ignorando os jogadores).
        if comp is not None:
            comp.update(fr, exclude_boxes=[t.bbox for t in tracks])

        for t in tracks:
            team_por_id[t.id] = t.team
            frames_vistos[t.id] = frames_vistos.get(t.id, 0) + 1
            x1, y1, x2, y2 = t.bbox
            pe_x, pe_y = (x1 + x2) / 2.0, float(y2)
            # Estabiliza o ponto dos pés para o frame de referência (descontando
            # o movimento da câmera), depois converte para metros.
            if comp is not None:
                pe_x, pe_y = comp.transform_point(pe_x, pe_y)
            pos_m = mapper.pixel_to_meters(pe_x, pe_y)
            pos_por_id.setdefault(t.id, [None] * n)
            pos_por_id[t.id][i] = pos_m

    logger.info("Rastreamento concluído: %d fragmentos (IDs locais).", len(pos_por_id))

    # Passo 1.5: consolidação automática (costura + filtro de ruído)
    # Transforma centenas de fragmentos em jogadores reais.
    # Parâmetros ajustáveis por ambiente (sem mexer no código):
    #   CONS_MIN_FRAMES, CONS_MIN_DIST, CONS_MAX_GAP, CONS_MAX_DIST
    pos_consolidado, id_map = consolidar(
        pos_por_id, team_por_id, n,
        max_gap_frames=int(os.getenv("CONS_MAX_GAP", "45")),
        max_dist_m=float(os.getenv("CONS_MAX_DIST", "5.0")),
        min_frames=int(os.getenv("CONS_MIN_FRAMES", "15")),
        min_distancia=float(os.getenv("CONS_MIN_DIST", "2.0")),
    )

    # Time de cada jogador consolidado: voto majoritário (ponderado por frames)
    # entre os fragmentos que o compõem.
    votos_time = {}
    for orig, canon in id_map.items():
        if canon not in pos_consolidado:
            continue
        t = team_por_id.get(orig, "unknown")
        nf = sum(1 for p in pos_por_id[orig] if p is not None)
        votos_time.setdefault(canon, {})
        votos_time[canon][t] = votos_time[canon].get(t, 0) + nf
    team_consolidado = {}
    for canon, votos in votos_time.items():
        # Ignora "unknown" quando há um time concreto.
        cand = {k: v for k, v in votos.items() if k != "unknown"} or votos
        team_consolidado[canon] = max(cand, key=cand.get)

    # Substitui as estruturas locais pelas consolidadas.
    pos_por_id = pos_consolidado
    team_por_id = team_consolidado
    frames_vistos = {
        pid: sum(1 for p in traj if p is not None) for pid, traj in pos_por_id.items()
    }

    # Passo 2: limpar trajetórias (outliers -> interpolar -> suavizar)
    dt = 1.0 / fps
    speed_por_id = {}  # {id: [v_kmh ou None] por frame}
    total_gaps = 0
    for pid, traj in pos_por_id.items():
        # 1) Remove saltos fisicamente impossíveis (cortes / trocas de ID).
        traj = reject_outliers(traj, dt, max_speed_kmh=40.0)
        # 2) Preenche gaps curtos por interpolação linear.
        ngaps, _ = contar_gaps(traj)
        total_gaps += ngaps
        traj = interpolate_gaps(traj, max_gap=45)
        # 3) Suaviza (média móvel) para reduzir tremor/ruído.
        traj = smooth_trajectory(traj, window=5)
        pos_por_id[pid] = traj

        # Velocidade por frame a partir da trajetória limpa.
        # Teto final de segurança: descarta velocidades acima do limite físico
        # (~40 km/h), eliminando qualquer salto residual que tenha escapado.
        TETO_KMH = 40.0
        speeds = [None] * n
        anterior = None
        for i, p in enumerate(traj):
            if p is not None and anterior is not None:
                v = physics.calculate_speed(anterior, p, dt)
                speeds[i] = v if v <= TETO_KMH else None
            anterior = p if p is not None else anterior
        speed_por_id[pid] = speeds
    logger.info("Limpeza concluída (%d gaps tratados no total).", total_gaps)

    # Passo 3: renderizar o vídeo anotado
    destino = os.path.join("..", "..", "data", "outputs", "test_output.mp4")
    with AnnotatedVideoWriter(destino, fps, (largura, altura)) as writer:
        for i, fr in enumerate(frames):
            anotacoes = []
            for t in frames_tracks[i]:
                # Mapeia o ID local para o jogador consolidado.
                final = id_map.get(t.id)
                if final is None:
                    # Fragmento descartado pelo filtro de ruído — não desenha.
                    continue
                v = speed_por_id.get(final, [None] * n)[i]
                anotacoes.append(
                    Anotacao(
                        track_id=final,
                        bbox=t.bbox,
                        team=team_por_id.get(final, t.team),
                        speed=v,
                    )
                )
            writer.write_frame(fr, anotacoes, timestamp=i / fps)

    # Resumo final: monta estatísticas, imprime tabela e salva CSV
    estatisticas = []  # lista de dicts por jogador
    for pid in sorted(pos_por_id.keys()):
        dist = physics.calculate_total_distance(pos_por_id[pid])
        vels = [v for v in speed_por_id[pid] if v is not None]
        vmax = max(vels) if vels else 0.0
        vmed = (sum(vels) / len(vels)) if vels else 0.0
        sprints = physics.calculate_sprint_count(vels)
        estatisticas.append({
            "id": pid,
            "time": team_por_id.get(pid, "?"),
            "frames": frames_vistos.get(pid, 0),
            "distancia_m": round(dist, 1),
            "v_max_kmh": round(vmax, 1),
            "v_med_kmh": round(vmed, 1),
            "sprints": sprints,
        })

    _imprimir_tabela(estatisticas)

    csv_path = os.path.join("..", "..", "data", "outputs", "stats.csv")
    _salvar_csv(estatisticas, csv_path)

    # Gráfico de velocidade ao longo do tempo (matplotlib).
    grafico_path = os.path.join("..", "..", "data", "outputs", "speed_chart.png")
    _gerar_grafico_velocidade(speed_por_id, estatisticas, fps, grafico_path)

    logger.info("Vídeo anotado salvo em: %s", destino)
    logger.info("Tabela CSV salva em: %s", csv_path)
    logger.info("Gráfico de velocidade salvo em: %s", grafico_path)
    logger.info("Jogadores detectados: %d", len(estatisticas))
    if estatisticas:
        logger.info(
            "Velocidade máxima global: %.1f km/h",
            max(e["v_max_kmh"] for e in estatisticas),
        )


def _imprimir_tabela(estatisticas):
    """Imprime as estatísticas por jogador como tabela alinhada no log."""
    logger.info("==================== TABELA DE ESTATÍSTICAS ====================")
    cab = f"{'ID':>4} | {'Time':>10} | {'Frames':>6} | {'Dist(m)':>8} | {'Vmax':>6} | {'Vmed':>6} | {'Sprints':>7}"
    logger.info(cab)
    logger.info("-" * len(cab))
    # Ordena por distância percorrida (mais ativos primeiro).
    for e in sorted(estatisticas, key=lambda x: x["distancia_m"], reverse=True):
        logger.info(
            "%4d | %10s | %6d | %8.1f | %6.1f | %6.1f | %7d",
            e["id"], e["time"], e["frames"], e["distancia_m"],
            e["v_max_kmh"], e["v_med_kmh"], e["sprints"],
        )


def _gerar_grafico_velocidade(speed_por_id, estatisticas, fps, caminho, top=8):
    """Gera um gráfico (matplotlib) da velocidade ao longo do tempo.

    Plota uma linha por jogador (os `top` mais ativos por distância) com a
    velocidade instantânea (km/h) em função do tempo (s).

    Args:
        speed_por_id: {id: [v_kmh ou None] por frame}.
        estatisticas: lista de dicts por jogador (para escolher os mais ativos).
        fps: quadros por segundo (converte índice de frame em segundos).
        caminho: arquivo PNG de saída.
        top: quantos jogadores plotar.
    """
    # Backend não-interativo (sem janela) — salva direto em arquivo.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Escolhe os jogadores mais ativos (mais distância) para não poluir.
    mais_ativos = sorted(estatisticas, key=lambda e: e["distancia_m"], reverse=True)[:top]

    fig, ax = plt.subplots(figsize=(14, 7))
    for e in mais_ativos:
        pid = e["id"]
        speeds = speed_por_id.get(pid, [])
        # Eixo X (tempo) e Y (velocidade), ignorando frames sem velocidade.
        xs = [i / fps for i, v in enumerate(speeds) if v is not None]
        ys = [v for v in speeds if v is not None]
        if xs:
            ax.plot(xs, ys, label=f"#{pid} ({e['time']})", linewidth=1.5)

    ax.set_title("Velocidade dos jogadores ao longo do tempo")
    ax.set_xlabel("Tempo (s)")
    ax.set_ylabel("Velocidade (km/h)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right", fontsize=9, ncol=2)
    fig.tight_layout()

    try:
        fig.savefig(caminho, dpi=110)
        logger.info("Gráfico gerado com %d jogadores.", len(mais_ativos))
    except Exception as exc:
        logger.error("Falha ao salvar gráfico: %s", exc)
    finally:
        plt.close(fig)


def _salvar_csv(estatisticas, caminho):
    """Salva as estatísticas em CSV (prévia do export oficial da Fase 8)."""
    import csv

    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    try:
        with open(caminho, "w", newline="", encoding="utf-8") as f:
            campos = ["id", "time", "frames", "distancia_m", "v_max_kmh", "v_med_kmh", "sprints"]
            writer = csv.DictWriter(f, fieldnames=campos)
            writer.writeheader()
            writer.writerows(estatisticas)
    except OSError as exc:
        logger.error("Falha ao salvar CSV: %s", exc)


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

    # FASE 3: rastreamento em 60 frames, com e sem ReID
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

    # FASE 4: física (velocidade, distância, sprints, heatmap)
    fps = obter_fps(caminho)
    testar_fisica(frames, classifier, fps)


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
    """Ponto de entrada do teste.

    Variáveis de ambiente úteis:
        PIPELINE_ONLY=1  -> roda apenas a Fase 5 (pipeline completo + vídeo),
                            pulando os testes detalhados das Fases 2-4.
        TEST_FRAMES=N    -> número de frames a processar no pipeline (padrão 300).
    """
    caminho = None
    if len(sys.argv) > 1:
        caminho = sys.argv[1]
    elif os.getenv("TEST_VIDEO"):
        caminho = os.getenv("TEST_VIDEO")

    if caminho and os.path.exists(caminho):
        if os.getenv("PIPELINE_ONLY") == "1":
            # Modo rápido para iterar no vídeo final.
            n = int(os.getenv("TEST_FRAMES", "0"))
            testar_pipeline_completo(caminho, n_frames=n)
        else:
            # Roda Fases 2-4 (detalhado) e depois o pipeline completo (Fase 5).
            testar_com_video(caminho)
            n = int(os.getenv("TEST_FRAMES", "0"))
            testar_pipeline_completo(caminho, n_frames=n)
    else:
        if caminho:
            logger.error("Vídeo não encontrado: %s — caindo no modo sintético.", caminho)
        testar_sintetico()


if __name__ == "__main__":
    main()
