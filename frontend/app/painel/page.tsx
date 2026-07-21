"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { CloudUpload, Zap, Gem, Crop, LayoutGrid, CheckCircle2, Video, MapPin } from "lucide-react";
import AppBar from "@/components/AppBar";
import MarcadorCampo, { Ponto } from "@/components/MarcadorCampo";
import { auth, videos, getToken } from "@/lib/api";

type Job = { id: string; status: string; progress: number; options?: { filename?: string } };

// Nome amigável: o arquivo enviado (sem extensão) ou "Vídeo N" como fallback.
function nomeAmigavel(job: Job, indice: number, total: number): string {
  const f = job.options?.filename;
  if (f) return f.replace(/\.[^.]+$/, "");
  return `Vídeo ${total - indice}`;
}

export default function Painel() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [time, setTime] = useState("Meu time");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [modo, setModo] = useState<"velocidade" | "qualidade">("velocidade");
  const [device, setDevice] = useState<"gpu" | "cpu">("gpu");
  const [area, setArea] = useState<"regiao" | "oficial">("regiao");
  const [tipoCampo, setTipoCampo] = useState<"futebol" | "futsal" | "society">("futebol");
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [pontos, setPontos] = useState<Ponto[] | null>(null); // cantos do campo marcados
  const [marcando, setMarcando] = useState(false);
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

  // Só envia para a IA quando o usuário clica em "Executar análise",
  // já com o arquivo escolhido E as opções (modo/área) selecionadas.
  async function executar() {
    if (!arquivo) return;
    setErro("");
    setEnviando(true);
    try {
      // Só envia os pontos do campo quando o modo de área é "marcar região".
      const fieldPoints = area === "regiao" && pontos ? pontos : undefined;
      const fieldType = area === "oficial" ? tipoCampo : undefined;
      // A escolha de GPU/CPU só se aplica ao modo Qualidade (o pesado).
      const dev = modo === "qualidade" ? device : undefined;
      await videos.upload(arquivo, { mode: modo, area, fieldType, device: dev, fieldPoints });
      setArquivo(null);
      setPontos(null);
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
          {arquivo ? (
            <>
              <Video size={28} className="text-grn mx-auto" />
              <div className="text-fg text-sm font-medium mt-2 truncate">{arquivo.name}</div>
              <div className="text-mut text-xs mt-1">
                {(arquivo.size / (1024 * 1024)).toFixed(1)} MB · clique para trocar de vídeo
              </div>
            </>
          ) : (
            <>
              <CloudUpload size={30} className="text-grn mx-auto" />
              <div className="text-fg text-sm font-medium mt-2">Arraste um vídeo ou clique para selecionar</div>
              <div className="text-mut text-xs mt-1">MP4, MOV, AVI ou MKV — até 500 MB</div>
            </>
          )}
          <input ref={inputRef} type="file" accept="video/*" hidden
            onChange={(e) => {
              if (e.target.files?.[0]) { setArquivo(e.target.files[0]); setPontos(null); setErro(""); }
              e.target.value = ""; // permite re-selecionar o mesmo arquivo
            }} />
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

        {/* Processamento (GPU x CPU) — só faz diferença no modo Qualidade */}
        {modo === "qualidade" && (
          <div className="card p-3.5 mb-6">
            <div className="text-[13px] text-fg font-medium mb-1">Processamento</div>
            <p className="text-xs text-mut mb-3">
              A GPU (NVIDIA/CUDA) é bem mais rápida. Sem uma GPU NVIDIA, use CPU —
              funciona em qualquer máquina, porém mais devagar.
            </p>
            <div className="flex gap-2">
              <button onClick={() => setDevice("gpu")}
                className="flex-1 text-[13px] py-2 rounded-lg border-2 transition-colors"
                style={{ borderColor: device === "gpu" ? "#34a05f" : "#2a2d33", color: device === "gpu" ? "#f5f5f5" : "#9ca3af" }}>
                GPU (NVIDIA / CUDA)
              </button>
              <button onClick={() => setDevice("cpu")}
                className="flex-1 text-[13px] py-2 rounded-lg border-2 transition-colors"
                style={{ borderColor: device === "cpu" ? "#34a05f" : "#2a2d33", color: device === "cpu" ? "#f5f5f5" : "#9ca3af" }}>
                CPU
              </button>
            </div>
          </div>
        )}

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

        {/* Seletor de tipo de campo: aparece com "Campo oficial". */}
        {area === "oficial" && (
          <div className="card p-3.5 mb-6 flex items-center justify-between gap-3 flex-wrap">
            <div className="min-w-0">
              <div className="text-fg text-[13px] font-medium">Tipo de campo</div>
              <div className="text-mut text-xs">Usamos as dimensões oficiais para medir as distâncias.</div>
            </div>
            <select
              value={tipoCampo}
              onChange={(e) => setTipoCampo(e.target.value as "futebol" | "futsal" | "society")}
              className="bg-ink border border-line rounded-lg text-fg text-[13px] px-3 py-2 shrink-0"
            >
              <option value="futebol">Futebol de campo (105 × 68 m)</option>
              <option value="futsal">Futsal (40 × 20 m)</option>
              <option value="society">Society (50 × 30 m)</option>
            </select>
          </div>
        )}

        {/* Calibração interativa: só faz sentido com "marcar região" + vídeo escolhido. */}
        {area === "regiao" && (
          <div className="card p-3.5 mb-6 flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-2.5 min-w-0">
              <MapPin size={18} className={pontos ? "text-grn shrink-0" : "text-mut shrink-0"} />
              <div className="min-w-0">
                <div className="text-fg text-[13px] font-medium">Calibração do campo</div>
                <div className="text-mut text-xs">
                  {!arquivo
                    ? "Selecione um vídeo para marcar os cantos do campo."
                    : pontos
                    ? "Campo marcado ✓ — velocidades serão calibradas em metros."
                    : "Sem marcar, o cálculo usa uma estimativa aproximada."}
                </div>
              </div>
            </div>
            <button
              onClick={() => setMarcando(true)}
              disabled={!arquivo}
              className="btn-ghost text-[13px] px-3 py-1.5 shrink-0 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {pontos ? "Remarcar campo" : "Marcar campo"}
            </button>
          </div>
        )}

        {/* Modal do marcador de campo (calibração interativa da homografia). */}
        {marcando && arquivo && (
          <MarcadorCampo
            file={arquivo}
            onConfirm={(p) => { setPontos(p); setMarcando(false); }}
            onClose={() => setMarcando(false)}
          />
        )}

        {/* Botão de execução: só AQUI o vídeo é enviado para a IA. */}
        <button onClick={executar} disabled={!arquivo || enviando}
          className="btn-primary w-full py-2.5 mb-2 inline-flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed">
          <Zap size={16} />
          {enviando ? "Enviando para a IA…" : "Executar análise"}
        </button>
        <p className="text-mut text-xs text-center mb-8">
          {arquivo ? "Confira as opções acima e execute quando quiser." : "Selecione um vídeo para habilitar."}
        </p>

        {/* Lista de jobs */}
        <div className="text-[13px] text-mut mb-2.5">Seus jobs</div>
        {jobs.length === 0 && <p className="text-mut text-xs">Nenhuma análise ainda.</p>}
        {jobs.map((j, idx) => (
          <div key={j.id} className="flex items-center justify-between card p-3 mb-2">
            <div className="flex items-center gap-2.5 min-w-0">
              <Video size={18} className="text-grn shrink-0" />
              <span className="text-fg text-[13px] truncate">{nomeAmigavel(j, idx, jobs.length)}</span>
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
