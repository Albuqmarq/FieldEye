"use client";

import { useEffect, useState } from "react";
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
  : { bg: "#1f1f1f", fg: "#9ca3af", label: t };

export default function Resultados() {
  const { id } = useParams<{ id: string }>();
  const [status, setStatus] = useState("pending");
  const [progress, setProgress] = useState(0);
  const [players, setPlayers] = useState<Player[]>([]);
  const [timeline, setTimeline] = useState<TL[]>([]);

  // Enquanto não terminar, consulta o status a cada 3s (polling).
  useEffect(() => {
    let ativo = true;
    async function tick() {
      try {
        const job = await videos.get(id);
        if (!ativo) return;
        setStatus(job.status);
        setProgress(job.progress);
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
          <div className="text-fg text-lg font-medium mb-2">Processando seu vídeo…</div>
          <p className="text-mut text-sm mb-5">Isto pode levar alguns minutos.</p>
          <div className="w-[260px] h-2 rounded bg-line overflow-hidden">
            <div className="h-full bg-grn transition-all" style={{ width: `${progress}%` }} />
          </div>
          <div className="text-mut text-xs mt-2">{progress}%</div>
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
          <h1 className="text-fg text-base font-medium">Resultados</h1>
          <div className="flex gap-2">
            <a href={analytics.csvUrl(id)} className="btn-ghost text-[13px] px-3.5 py-2 inline-flex items-center gap-1.5">
              <FileSpreadsheet size={14} /> CSV
            </a>
            <a href={analytics.pdfUrl(id)} className="btn-ghost text-[13px] px-3.5 py-2 inline-flex items-center gap-1.5">
              <FileText size={14} /> PDF
            </a>
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
        <div className="text-[13px] text-mut mb-2.5 mt-4">Jogadores</div>
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

// Gráfico simples de velocidade ao longo do tempo (top 4 jogadores).
function SpeedChart({ timeline, players }: { timeline: TL[]; players: Player[] }) {
  const cores = ["#34a05f", "#60a5fa", "#f97316", "#f43f5e"];
  const top = [...players].sort((a, b) => b.total_distance - a.total_distance).slice(0, 4).map((p) => p.player_id);
  const series = timeline.filter((t) => top.includes(t.player_id));
  const maxSpeed = 40, maxT = Math.max(1, ...series.flatMap((s) => s.points.map((p) => p.timestamp || 0)));
  const X = (t: number) => 30 + (t / maxT) * 260;
  const Y = (v: number) => 100 - (v / maxSpeed) * 88;
  return (
    <div className="card p-3.5 mb-2">
      <div className="text-[13px] text-fg font-medium mb-2.5">Velocidade ao longo do tempo</div>
      <svg viewBox="0 0 300 120" width="100%">
        <line x1="30" y1="100" x2="290" y2="100" stroke="#2a2d33" />
        <line x1="30" y1="12" x2="30" y2="100" stroke="#2a2d33" />
        {series.map((s, i) => (
          <polyline key={s.player_id} fill="none" stroke={cores[i % 4]} strokeWidth="1.6"
            points={s.points.filter((p) => p.speed != null).map((p) => `${X(p.timestamp)},${Y(p.speed as number)}`).join(" ")} />
        ))}
        <text x="150" y="116" fill="#6b7280" fontSize="9" textAnchor="middle">tempo (s)</text>
      </svg>
    </div>
  );
}
