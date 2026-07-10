"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { CloudUpload, Zap, Gem, Crop, LayoutGrid, CheckCircle2, Video } from "lucide-react";
import AppBar from "@/components/AppBar";
import { auth, videos, getToken } from "@/lib/api";

type Job = { id: string; status: string; progress: number };

export default function Painel() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [time, setTime] = useState("Meu time");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [modo, setModo] = useState<"velocidade" | "qualidade">("velocidade");
  const [area, setArea] = useState<"regiao" | "oficial">("regiao");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");

  // Protege a rota: sem token, volta para o login.
  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    auth.me().then((u) => u?.team_name && setTime(u.team_name)).catch(() => {});
    carregarJobs();
    // Atualiza a lista a cada 4s (para ver o progresso subir).
    const id = setInterval(carregarJobs, 4000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function carregarJobs() {
    try {
      setJobs(await videos.list());
    } catch {}
  }

  async function enviar(file: File) {
    setErro("");
    setEnviando(true);
    try {
      await videos.upload(file);
      await carregarJobs();
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Falha no upload.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <>
      <AppBar time={time} />
      <div className="px-4 py-5 max-w-[760px] mx-auto w-full">
        <h1 className="text-fg text-lg font-medium mb-4">Nova análise</h1>

        {/* Upload */}
        <div
          onClick={() => inputRef.current?.click()}
          className="rounded-xl p-6 text-center cursor-pointer mb-6"
          style={{ border: "1.5px dashed #34a05f55", background: "#14161a" }}
        >
          <CloudUpload size={30} className="text-grn mx-auto" />
          <div className="text-fg text-sm font-medium mt-2">
            {enviando ? "Enviando..." : "Arraste um vídeo ou clique para enviar"}
          </div>
          <div className="text-mut text-xs mt-1">MP4, MOV, AVI ou MKV — até 500 MB</div>
          <input ref={inputRef} type="file" accept="video/*" hidden
            onChange={(e) => e.target.files?.[0] && enviar(e.target.files[0])} />
        </div>
        {erro && <p className="text-red-400 text-xs mb-4">{erro}</p>}

        {/* Modo de análise */}
        <div className="text-[13px] text-fg font-medium mb-1">Modo de análise</div>
        <p className="text-xs text-mut mb-3">Processar rápido ou com máxima precisão.</p>
        <div className="grid gap-3 mb-6" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))" }}>
          <OptCard sel={modo === "velocidade"} onClick={() => setModo("velocidade")}
            icon={Zap} titulo="Velocidade"
            desc="Processa em minutos e roda em qualquer computador. Ideal para testar e para vídeos com boa visão dos jogadores." />
          <OptCard sel={modo === "qualidade"} onClick={() => setModo("qualidade")}
            icon={Gem} titulo="Qualidade"
            desc="Detecta até jogadores pequenos e distantes. Mais lento — recomendado com GPU e câmera tática." />
        </div>

        {/* Área de análise */}
        <div className="text-[13px] text-fg font-medium mb-1">Área de análise</div>
        <p className="text-xs text-mut mb-3">Como o FieldEye deve medir as distâncias no seu vídeo.</p>
        <div className="grid gap-3 mb-6" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(230px,1fr))" }}>
          <OptCard sel={area === "regiao"} onClick={() => setArea("regiao")}
            icon={Crop} titulo="Marcar região no vídeo" tag="Recomendado"
            desc="Não sabe o tamanho do campo? Marque a área direto no vídeo e o FieldEye estima as velocidades." />
          <OptCard sel={area === "oficial"} onClick={() => setArea("oficial")}
            icon={LayoutGrid} titulo="Campo oficial"
            desc="Sabe as medidas? Escolha o tipo (futebol, futsal, society) e usamos as dimensões reais." />
        </div>

        {/* Lista de jobs */}
        <div className="text-[13px] text-mut mb-2.5">Seus jobs</div>
        {jobs.length === 0 && <p className="text-mut text-xs">Nenhuma análise ainda.</p>}
        {jobs.map((j) => (
          <div key={j.id} className="flex items-center justify-between card p-3 mb-2">
            <div className="flex items-center gap-2.5 min-w-0">
              <Video size={18} className="text-grn shrink-0" />
              <span className="text-fg text-[13px] truncate">análise {j.id.slice(0, 8)}</span>
            </div>
            {j.status === "done" ? (
              <div className="flex items-center gap-2.5">
                <span className="text-[11px] text-grnl px-2.5 py-0.5 rounded-full" style={{ background: "#132a1d" }}>Concluído</span>
                <Link href={`/jobs/${j.id}`} className="btn-primary text-xs px-3 py-1.5">Ver resultados</Link>
              </div>
            ) : j.status === "failed" ? (
              <span className="text-[11px] text-red-400">Falhou</span>
            ) : (
              <div className="flex items-center gap-2.5 flex-1 max-w-[240px] ml-4">
                <div className="flex-1 h-1.5 rounded bg-line overflow-hidden">
                  <div className="h-full bg-grn" style={{ width: `${j.progress}%` }} />
                </div>
                <span className="text-xs text-mut whitespace-nowrap">{j.progress}%</span>
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}

// Card de opção selecionável (modo/área).
function OptCard({ sel, onClick, icon: Icon, titulo, desc, tag }: {
  sel: boolean; onClick: () => void; icon: React.ElementType;
  titulo: string; desc: string; tag?: string;
}) {
  return (
    <div onClick={onClick} className="card p-4 cursor-pointer relative"
      style={{ borderColor: sel ? "#34a05f" : "#2a2d33", borderWidth: 2 }}>
      {sel && <CheckCircle2 size={18} className="text-grn absolute top-3 right-3" />}
      <div className="flex items-center gap-2 mb-1.5">
        <Icon size={20} className={sel ? "text-grn" : "text-mut"} />
        <span className="text-fg text-sm font-medium">{titulo}</span>
      </div>
      <p className="text-xs text-mut leading-relaxed mb-2">{desc}</p>
      {tag && <span className="text-[11px] text-grnl px-2.5 py-0.5 rounded-full" style={{ background: "#132a1d" }}>{tag}</span>}
    </div>
  );
}
