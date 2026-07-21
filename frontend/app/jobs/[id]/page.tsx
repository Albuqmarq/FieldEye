"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { FileSpreadsheet, FileText } from "lucide-react";
import AppBar from "@/components/AppBar";
import { videos, analytics } from "@/lib/api";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost";

type Player = {
  player_id: number; team: string;
  max_speed: number; avg_speed: number; total_distance: number;
};
type TL = { player_id: number; points: { timestamp: number; speed: number | null }[] };

// Cores por time.
const cor = (t: string) =>
  t === "A" ? { bg: "#3a1414", fg: "#fca5a5", label: "Time A" }
  : t === "B" ? { bg: "#14213a", fg: "#93c5fd", label: "Time B" }
  : t === "goalkeeper" ? { bg: "#3a2c0a", fg: "#fde68a", label: "Goleiro" }
  : t === "outro" ? { bg: "#1f1f1f", fg: "#9ca3af", label: "Outro (goleiro/juiz)" }
  : { bg: "#1f1f1f", fg: "#9ca3af", label: t };

export default function Resultados() {
  const { id } = useParams<{ id: string }>();
  const [status, setStatus] = useState("pending");
  const [progress, setProgress] = useState(0);
  const [players, setPlayers] = useState<Player[]>([]);
  const [timeline, setTimeline] = useState<TL[]>([]);
  const [nomeVideo, setNomeVideo] = useState<string>("");
  const [baixando, setBaixando] = useState<"csv" | "pdf" | null>(null);
  const [eta, setEta] = useState<number | null>(null); // segundos restantes estimados
  const baseEta = useRef<{ t: number; p: number } | null>(null);

  // Etapa atual (texto) a partir da faixa de progresso (bate com o worker).
  const etapa = (p: number) =>
    p < 5 ? "Preparando o vídeo"
    : p < 80 ? "Detectando e rastreando jogadores"
    : p < 88 ? "Calculando velocidades e distâncias"
    : "Renderizando o vídeo anotado";

  // Baixa CSV/PDF com autenticação (o endpoint exige o token JWT).
  async function baixar(kind: "csv" | "pdf") {
    setBaixando(kind);
    try {
      await analytics.download(id, kind);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Falha ao baixar o arquivo.");
    } finally {
      setBaixando(null);
    }
  }

  // Enquanto não terminar, consulta o status a cada 3s (polling).
  useEffect(() => {
    let ativo = true;
    async function tick() {
      try {
        const job = await videos.get(id);
        if (!ativo) return;
        setStatus(job.status);
        setProgress(job.progress);
        if (job.options?.filename) setNomeVideo(job.options.filename.replace(/\.[^.]+$/, ""));
        // Estima o tempo restante pela velocidade do progresso desde a 1ª leitura.
        if (job.status === "processing" && job.progress > 0 && job.progress < 100) {
          if (!baseEta.current) baseEta.current = { t: Date.now(), p: job.progress };
          else {
            const dt = (Date.now() - baseEta.current.t) / 1000;
            const dp = job.progress - baseEta.current.p;
            if (dp > 0 && dt > 1) setEta(Math.max(0, Math.round((dt / dp) * (100 - job.progress))));
          }
        }
        if (job.status === "done") {
          const r = await analytics.result(id);
          setPlayers(r.players || []);
          analytics.timeline(id).then((t) => ativo && setTimeline(t || [])).catch(() => {});
          return; // para de fazer polling
        }
      } catch {}
      if (ativo) setTimeout(tick, 3000);
    }
    tick();
    return () => { ativo = false; };
  }, [id]);

  // Estado de processamento.
  if (status !== "done") {
    return (
      <>
        <AppBar />
        <div className="flex-1 flex flex-col items-center justify-center px-6 text-center">
          <div className="text-fg text-lg font-medium mb-2">Processando {nomeVideo || "seu vídeo"}…</div>
          <p className="text-mut text-sm mb-5">{status === "failed" ? "Falhou" : etapa(progress)}</p>
          <div className="w-[260px] h-2 rounded bg-line overflow-hidden">
            <div className="h-full bg-grn transition-all" style={{ width: `${progress}%` }} />
          </div>
          <div className="text-mut text-xs mt-2">
            {progress}%
            {eta != null && status === "processing"
              ? ` · ~${eta >= 60 ? Math.ceil(eta / 60) + " min" : eta + " s"} restantes`
              : ""}
          </div>
          {status === "failed" && <p className="text-red-400 text-sm mt-4">A análise falhou. Tente novamente.</p>}
        </div>
      </>
    );
  }

  // Resumo agregado.
  const velMax = players.reduce((m, p) => Math.max(m, p.max_speed || 0), 0);
  const distTotal = players.reduce((s, p) => s + (p.total_distance || 0), 0);

  return (
    <>
      <AppBar />
      <div className="px-4 py-5 max-w-[760px] mx-auto w-full">
        <div className="flex items-center justify-between flex-wrap gap-2.5 mb-4">
          <div className="min-w-0">
            <h1 className="text-fg text-base font-medium truncate">{nomeVideo || "Resultados"}</h1>
            <div className="text-[11px] text-grnl">rastreado ✓</div>
          </div>
          <div className="flex gap-2">
            <button onClick={() => baixar("csv")} disabled={baixando !== null}
              className="btn-ghost text-[13px] px-3.5 py-2 inline-flex items-center gap-1.5 disabled:opacity-50">
              <FileSpreadsheet size={14} /> {baixando === "csv" ? "Gerando…" : "CSV"}
            </button>
            <button onClick={() => baixar("pdf")} disabled={baixando !== null}
              className="btn-ghost text-[13px] px-3.5 py-2 inline-flex items-center gap-1.5 disabled:opacity-50">
              <FileText size={14} /> {baixando === "pdf" ? "Gerando…" : "PDF"}
            </button>
          </div>
        </div>

        {/* Vídeo anotado */}
        <video src={`${API}/files/${id}.mp4`} controls
          className="w-full rounded-xl border border-line mb-4 bg-black" />

        {/* Métricas resumo */}
        <div className="grid gap-2.5 mb-4" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(120px,1fr))" }}>
          <Metric label="Jogadores" value={String(players.length)} />
          <Metric label="Vel. máxima" value={`${velMax.toFixed(0)} km/h`} accent />
          <Metric label="Distância total" value={`${distTotal.toFixed(0)} m`} />
        </div>

        {/* Gráfico de velocidade */}
        {timeline.length > 0 && <SpeedChart timeline={timeline} players={players} />}

        {/* Cards por jogador */}
        <div className="mt-4 mb-2.5">
          <div className="text-[13px] text-fg font-medium">Jogadores</div>
          <div className="text-[11px] text-mut">O número é o ID de rastreio (não o número da camisa) e a cor indica o time detectado.</div>
        </div>
        <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))" }}>
          {players.map((p) => {
            const c = cor(p.team);
            return (
              <div key={p.player_id} className="card card-hover p-3.5">
                <div className="flex items-center gap-2 mb-2">
                  <span className="w-[30px] h-[30px] rounded-full inline-flex items-center justify-center text-white text-xs" style={{ background: "#374151" }}>{p.player_id}</span>
                  <span className="text-[11px] px-2 py-0.5 rounded-full" style={{ background: c.bg, color: c.fg }}>{c.label}</span>
                </div>
                <Row k="Vel. máx" v={`${(p.max_speed || 0).toFixed(0)} km/h`} />
                <Row k="Vel. méd" v={`${(p.avg_speed || 0).toFixed(0)} km/h`} />
                <Row k="Distância" v={`${(p.total_distance || 0).toFixed(0)} m`} />
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}

function Metric({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="rounded-lg p-3" style={{ background: "#17181c" }}>
      <div className="text-xs text-mut">{label}</div>
      <div className={`text-[22px] font-medium ${accent ? "text-grn" : "text-fg"}`}>{value}</div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="text-xs text-mut flex justify-between my-0.5">{k} <span className="text-fg">{v}</span></div>
  );
}

// Gráfico de velocidade ao longo do tempo (top 4 jogadores por distância),
// com eixos rotulados (km/h e tempo) e legenda identificando cada linha.
function SpeedChart({ timeline, players }: { timeline: TL[]; players: Player[] }) {
  const cores = ["#34a05f", "#60a5fa", "#f97316", "#f43f5e"];
  const top = [...players].sort((a, b) => b.total_distance - a.total_distance).slice(0, 4);
  const topIds = top.map((p) => p.player_id);
  const series = timeline.filter((t) => topIds.includes(t.player_id));

  // Escala: eixo Y arredondado ao próximo múltiplo de 10 acima da vel. máxima.
  const vMaxReal = Math.max(10, ...series.flatMap((s) => s.points.map((p) => p.speed || 0)));
  const maxSpeed = Math.ceil(vMaxReal / 10) * 10;
  const maxT = Math.max(1, ...series.flatMap((s) => s.points.map((p) => p.timestamp || 0)));
  const X = (t: number) => 34 + (t / maxT) * 256;
  const Y = (v: number) => 100 - (v / maxSpeed) * 86;

  // Ticks do eixo Y (0, meio, máx) e do eixo X (0, meio, fim em segundos).
  const yTicks = [0, maxSpeed / 2, maxSpeed];
  const xTicks = [0, maxT / 2, maxT];
  const teamLabel = (id: number) => {
    const p = players.find((pl) => pl.player_id === id);
    return p ? cor(p.team).label : "";
  };

  return (
    <div className="card p-3.5 mb-2">
      <div className="text-[13px] text-fg font-medium mb-2.5">Velocidade ao longo do tempo (km/h)</div>
      <svg viewBox="0 0 300 122" width="100%">
        {/* Linhas de grade + rótulos do eixo Y (km/h) */}
        {yTicks.map((v) => (
          <g key={v}>
            <line x1="34" y1={Y(v)} x2="290" y2={Y(v)} stroke="#22252b" strokeWidth="0.5" />
            <text x="30" y={Y(v) + 3} fill="#6b7280" fontSize="7" textAnchor="end">{v.toFixed(0)}</text>
          </g>
        ))}
        {/* Rótulos do eixo X (tempo em s) */}
        {xTicks.map((t) => (
          <text key={t} x={X(t)} y="112" fill="#6b7280" fontSize="7" textAnchor="middle">{t.toFixed(0)}s</text>
        ))}
        {/* Séries por jogador */}
        {series.map((s, i) => (
          <polyline key={s.player_id} fill="none" stroke={cores[i % 4]} strokeWidth="1.4"
            points={s.points.filter((p) => p.speed != null).map((p) => `${X(p.timestamp)},${Y(p.speed as number)}`).join(" ")} />
        ))}
        <text x="162" y="120" fill="#6b7280" fontSize="7" textAnchor="middle">tempo (s)</text>
      </svg>
      {/* Legenda: qual cor é qual jogador */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
        {top.map((p, i) => (
          <div key={p.player_id} className="flex items-center gap-1.5 text-[11px] text-mut">
            <span className="inline-block w-3 h-[2px] rounded" style={{ background: cores[i % 4] }} />
            Jogador #{p.player_id} <span className="opacity-70">({teamLabel(p.player_id)})</span>
          </div>
        ))}
      </div>
    </div>
  );
}
