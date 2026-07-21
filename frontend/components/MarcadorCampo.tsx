"use client";

// MarcadorCampo — calibração interativa da homografia.
// Extrai o 1º frame do vídeo SELECIONADO (ainda no navegador, sem subir
// para o servidor) e deixa o usuário clicar nos 4 cantos do campo. Esses
// pontos (em pixels NATIVOS do vídeo) são enviados no upload e o worker
// os usa para converter pixels -> metros com precisão (homografia).

import { useEffect, useRef, useState } from "react";

export type Ponto = { x: number; y: number };

const LABELS = [
  "canto superior-esquerdo",
  "canto superior-direito",
  "canto inferior-direito",
  "canto inferior-esquerdo",
];

export default function MarcadorCampo({
  file,
  onConfirm,
  onClose,
}: {
  file: File;
  onConfirm: (pts: Ponto[]) => void;
  onClose: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [pts, setPts] = useState<Ponto[]>([]); // pixels NATIVOS do vídeo
  const [dim, setDim] = useState({ w: 0, h: 0 });
  const [pronto, setPronto] = useState(false);
  const [erro, setErro] = useState("");

  // Extrai um frame do vídeo local e o desenha no canvas.
  useEffect(() => {
    const url = URL.createObjectURL(file);
    const v = document.createElement("video");
    v.preload = "auto";
    v.muted = true;
    v.src = url;

    const desenhar = () => {
      const w = v.videoWidth;
      const h = v.videoHeight;
      const c = canvasRef.current;
      if (c && w && h) {
        c.width = w;
        c.height = h;
        c.getContext("2d")?.drawImage(v, 0, 0, w, h);
        setDim({ w, h });
        setPronto(true);
      }
    };
    // Ao carregar, pula um pouco à frente para evitar frame preto inicial.
    const onLoaded = () => {
      try {
        v.currentTime = Math.min(0.1, (v.duration || 2) / 2);
      } catch {
        desenhar();
      }
    };
    const onErr = () =>
      setErro("Não consegui ler um frame deste vídeo no navegador. Você ainda pode executar sem marcar (estimativa aproximada).");

    v.addEventListener("loadeddata", onLoaded);
    v.addEventListener("seeked", desenhar);
    v.addEventListener("error", onErr);
    return () => {
      v.removeEventListener("loadeddata", onLoaded);
      v.removeEventListener("seeked", desenhar);
      v.removeEventListener("error", onErr);
      URL.revokeObjectURL(url);
    };
  }, [file]);

  // Converte o clique (coords de tela) para pixels NATIVOS do vídeo.
  function clicar(e: React.MouseEvent<HTMLDivElement>) {
    if (!pronto || pts.length >= 4) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * dim.w;
    const y = ((e.clientY - rect.top) / rect.height) * dim.h;
    setPts([...pts, { x, y }]);
  }

  // Posição de um ponto no overlay, em porcentagem (responsivo).
  const pct = (p: Ponto) => ({
    left: `${(p.x / dim.w) * 100}%`,
    top: `${(p.y / dim.h) * 100}%`,
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.8)" }}
      onClick={onClose}
    >
      <div className="card p-4 w-full max-w-[820px]" onClick={(e) => e.stopPropagation()}>
        <div className="text-fg text-sm font-medium mb-1">Marcar o campo no vídeo</div>
        <p className="text-mut text-xs mb-3">
          Clique nos <b>4 cantos do campo</b>, nesta ordem: {LABELS.join(" → ")}. Isso
          calibra a conversão de pixels para metros (velocidades mais precisas).
        </p>
        {erro && <p className="text-red-400 text-xs mb-2">{erro}</p>}

        <div className="relative w-full rounded-lg overflow-hidden border border-line" style={{ background: "#000" }}>
          <canvas ref={canvasRef} className="w-full block" style={{ height: "auto" }} />
          {/* Camada de clique + marcadores sobre o frame */}
          <div className="absolute inset-0 cursor-crosshair" onClick={clicar}>
            <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 100 100" preserveAspectRatio="none">
              {pts.length > 1 && (
                <polyline
                  fill="rgba(52,160,95,0.18)"
                  stroke="#34a05f"
                  strokeWidth="0.5"
                  points={[...pts, ...(pts.length === 4 ? [pts[0]] : [])]
                    .map((p) => `${(p.x / dim.w) * 100},${(p.y / dim.h) * 100}`)
                    .join(" ")}
                />
              )}
            </svg>
            {pts.map((p, i) => (
              <div
                key={i}
                className="absolute w-5 h-5 rounded-full text-black text-[10px] font-bold flex items-center justify-center border-2 border-white"
                style={{ ...pct(p), transform: "translate(-50%,-50%)", background: "#34a05f" }}
              >
                {i + 1}
              </div>
            ))}
          </div>
        </div>

        <div className="text-mut text-xs mt-2">
          {pts.length}/4 pontos{pts.length < 4 ? ` — próximo: ${LABELS[pts.length]}` : " — campo marcado ✓"}
        </div>

        <div className="flex justify-end gap-2 mt-3">
          <button onClick={() => setPts([])} className="btn-ghost text-[13px] px-3 py-1.5">Refazer</button>
          <button onClick={onClose} className="btn-ghost text-[13px] px-3 py-1.5">Cancelar</button>
          <button
            onClick={() => onConfirm(pts)}
            disabled={pts.length !== 4}
            className="btn-primary text-[13px] px-3 py-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Confirmar campo
          </button>
        </div>
      </div>
    </div>
  );
}
