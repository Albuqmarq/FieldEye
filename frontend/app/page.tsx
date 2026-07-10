import Link from "next/link";
import {
  Activity, UserPlus, Upload, Cpu, BarChart3, Download,
  Target, Gauge, Map, SlidersHorizontal, Ruler, Video,
} from "lucide-react";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import PitchHero from "@/components/PitchHero";

// Passos do "Como funciona".
const passos = [
  { icon: UserPlus, t: "1. Crie a conta", s: "Cadastro rápido" },
  { icon: Upload, t: "2. Envie o vídeo", s: "Arraste e solte" },
  { icon: Cpu, t: "3. A IA processa", s: "Acompanhe o %" },
  { icon: BarChart3, t: "4. Veja o painel", s: "Stats e heatmap" },
  { icon: Download, t: "5. Exporte", s: "CSV ou PDF" },
];

// Cards de recursos.
const recursos = [
  { icon: Target, t: "Rastreamento com IA", s: "Cada jogador com ID próprio ao longo do jogo." },
  { icon: Gauge, t: "Velocidade e distância", s: "Métricas físicas reais por jogador." },
  { icon: Map, t: "Heatmap", s: "Onde cada jogador mais atuou em campo." },
  { icon: SlidersHorizontal, t: "Modo leve ou preciso", s: "Escolha rapidez ou máxima precisão." },
  { icon: Ruler, t: "Calibração do campo", s: "Marque a área para medidas exatas." },
  { icon: Video, t: "Vídeo anotado", s: "Baixe o jogo com as caixas e dados." },
];

export default function Home() {
  return (
    <>
      <Navbar />

      {/* Hero */}
      <section className="flex flex-wrap items-center gap-6 px-6 py-10 bg-ink">
        <div className="flex-1 min-w-[230px]">
          <div className="inline-flex items-center gap-1.5 bg-ink2 text-[#d1d5db] text-xs px-3 py-1.5 rounded border border-line mb-4">
            <Activity size={14} className="text-grn" /> Análise de futebol por vídeo
          </div>
          <h1 className="text-fg text-[29px] font-medium leading-tight mb-3.5">
            Transforme qualquer vídeo de jogo em dados de desempenho
          </h1>
          <p className="text-mut text-[15px] leading-relaxed mb-6">
            Obtenha velocidade, distância, heatmaps e estatísticas completas usando
            apenas um vídeo da partida. Sem GPS, drones ou equipamentos caros.
          </p>
          <Link href="/register" className="btn-primary inline-block px-6 py-2.5 text-sm">
            Criar conta grátis
          </Link>
        </div>
        <div className="flex-1 min-w-[260px]">
          <PitchHero />
        </div>
      </section>

      {/* Sobre */}
      <section id="sobre" className="px-6 py-8 bg-panel border-t border-line">
        <h2 className="text-center text-fg text-lg font-medium mb-3.5">Sobre o FieldEye</h2>
        <div className="max-w-[600px] mx-auto">
          <p className="text-[#a6adba] text-sm leading-relaxed mb-3">
            O FieldEye usa inteligência artificial para detectar e acompanhar cada jogador
            em vídeo. Ele reconhece os times pela cor do uniforme, dá a cada atleta um
            identificador próprio e calcula velocidade, distância percorrida, sprints e o
            heatmap de posicionamento. No final, você recebe um vídeo anotado com tudo em
            campo e pode exportar os números em CSV ou PDF.
          </p>
          <p className="text-[#a6adba] text-sm leading-relaxed">
            Funciona tanto em jogos quanto em treinos. Em gravações de{" "}
            <span className="text-grnl">câmera fixa</span>, com a calibração do campo, as
            medidas ficam mais precisas; em vídeos com muito corte ou zoom, o sistema
            compensa o movimento da câmera e entrega uma boa estimativa. Foi pensado para
            escolinhas, times amadores e análise de treino.
          </p>
        </div>
      </section>

      {/* Como funciona */}
      <section id="como-funciona" className="px-6 py-10 bg-ink3">
        <h2 className="text-center text-fg text-lg font-medium mb-1">Como funciona</h2>
        <p className="text-center text-mut text-[13px] mb-6">Do upload ao relatório em 5 passos</p>
        <div className="grid gap-3 max-w-[620px] mx-auto" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(110px,1fr))" }}>
          {passos.map((p) => (
            <div key={p.t} className="card card-hover text-center px-2 py-4" style={{ background: "#262a31", borderColor: "#363b44" }}>
              <p.icon size={24} className="text-grn mx-auto" />
              <div className="text-[13px] font-medium text-fg mt-2">{p.t}</div>
              <div className="text-[11px] text-mut mt-0.5">{p.s}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Recursos */}
      <section id="recursos" className="px-6 py-8 bg-ink">
        <h2 className="text-center text-fg text-lg font-medium mb-6">Recursos</h2>
        <div className="grid gap-3 max-w-[720px] mx-auto" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))" }}>
          {recursos.map((r) => (
            <div key={r.t} className="card card-hover p-4">
              <r.icon size={20} className="text-grn" />
              <div className="text-sm font-medium text-fg mt-2 mb-1">{r.t}</div>
              <div className="text-xs text-mut leading-relaxed">{r.s}</div>
            </div>
          ))}
        </div>
      </section>

      {/* CTA final */}
      <section className="px-6 py-11 text-center border-t" style={{ background: "#132a1d", borderColor: "#1c3a28" }}>
        <div className="text-fg text-[22px] font-medium mb-2">Comece gratuitamente</div>
        <p className="text-[#a6adba] text-sm mb-5">Analise seu primeiro vídeo em poucos minutos.</p>
        <Link href="/register" className="btn-primary inline-block px-7 py-3 text-[15px]">
          Criar conta grátis
        </Link>
      </section>

      <Footer />
    </>
  );
}
