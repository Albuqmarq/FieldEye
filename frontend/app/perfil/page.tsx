"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Home, FileVideo } from "lucide-react";
import AppBar from "@/components/AppBar";
import { auth, videos, analytics, getToken } from "@/lib/api";

type User = { id: number; email: string; team_name?: string; created_at: string };
type Job = { id: string; status: string; progress: number; created_at: string; options?: { filename?: string } };
type Resumo = { players: number; dist: number; vmax: number };

export default function Perfil() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [resumos, setResumos] = useState<Record<string, Resumo>>({});

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    auth.me().then(setUser).catch(() => {});
    videos.list().then(async (js: Job[]) => {
      setJobs(js);
      // Para cada job concluído, busca um resumo dos dados gerados (histórico).
      for (const j of js.filter((x) => x.status === "done")) {
        try {
          const r = await analytics.result(j.id);
          const ps = r.players || [];
          setResumos((old) => ({
            ...old,
            [j.id]: {
              players: ps.length,
              dist: ps.reduce((s: number, p: { total_distance?: number }) => s + (p.total_distance || 0), 0),
              vmax: ps.reduce((m: number, p: { max_speed?: number }) => Math.max(m, p.max_speed || 0), 0),
            },
          }));
        } catch { /* job sem resultados ainda — ignora */ }
      }
    }).catch(() => {});
  }, [router]);

  const fmtData = (s?: string) => (s ? new Date(s).toLocaleDateString("pt-BR") : "—");

  return (
    <>
      <AppBar time={user?.team_name || "Meu time"} />
      <div className="px-4 py-5 max-w-[760px] mx-auto w-full">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-fg text-lg font-medium">Meu perfil</h1>
          <Link href="/" className="btn-ghost text-[13px] px-3 py-1.5 inline-flex items-center gap-1.5">
            <Home size={14} /> Página inicial
          </Link>
        </div>

        {/* Informações da conta */}
        <div className="card p-4 mb-6">
          <Info k="E-mail" v={user?.email || "—"} />
          <Info k="Time" v={user?.team_name || "—"} />
          <Info k="Membro desde" v={fmtData(user?.created_at)} />
        </div>

        {/* Histórico de análises */}
        <div className="text-[13px] text-fg font-medium mb-1">Histórico de análises</div>
        <p className="text-xs text-mut mb-3">
          Nome do arquivo e os dados gerados. O vídeo em si não é re-armazenado aqui.
        </p>
        {jobs.length === 0 && <p className="text-mut text-xs">Nenhuma análise ainda.</p>}
        <div className="grid gap-2.5">
          {jobs.map((j) => {
            const nome = j.options?.filename || `análise ${j.id.slice(0, 8)}`;
            const r = resumos[j.id];
            return (
              <div key={j.id} className="card p-3.5">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="flex items-center gap-2 min-w-0">
                    <FileVideo size={16} className="text-grn shrink-0" />
                    <span className="text-fg text-[13px] truncate">{nome}</span>
                  </div>
                  <div className="flex items-center gap-2.5">
                    <span className="text-xs text-mut">{fmtData(j.created_at)}</span>
                    {j.status === "done" ? (
                      <Link href={`/jobs/${j.id}`} className="btn-primary text-xs px-3 py-1.5">Ver resultados</Link>
                    ) : j.status === "failed" ? (
                      <span className="text-[11px] text-red-400">Falhou</span>
                    ) : (
                      <span className="text-[11px] text-mut">{j.progress}%</span>
                    )}
                  </div>
                </div>
                {r && (
                  <div className="flex gap-4 mt-2 text-xs text-mut">
                    <span>{r.players} jogadores</span>
                    <span>{r.dist.toFixed(0)} m percorridos</span>
                    <span>vel. máx {r.vmax.toFixed(0)} km/h</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}

function Info({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between py-1.5 text-sm border-b border-line last:border-0">
      <span className="text-mut">{k}</span>
      <span className="text-fg">{v}</span>
    </div>
  );
}
