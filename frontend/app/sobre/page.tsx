import Link from "next/link";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";

export default function Sobre() {
  return (
    <>
      <Navbar />
      <section className="px-6 py-12 bg-ink flex-1">
        <div className="max-w-[640px] mx-auto">
          <h1 className="text-fg text-[26px] font-medium mb-5">Sobre o FieldEye</h1>
          <p className="text-[#a6adba] text-[15px] leading-relaxed mb-4">
            O FieldEye nasceu para tornar a análise de desempenho no futebol acessível a
            qualquer clube — não só aos grandes centros que têm equipamentos caros. Com
            inteligência artificial, ele detecta e acompanha cada jogador em vídeo,
            reconhece os times pela cor do uniforme e calcula velocidade, distância,
            sprints e o heatmap de posicionamento de cada atleta.
          </p>
          <p className="text-[#a6adba] text-[15px] leading-relaxed mb-4">
            No fim, você recebe um vídeo anotado com tudo marcado em campo e pode exportar
            os números em CSV ou PDF para acompanhar a evolução do time.
          </p>
          <p className="text-[#a6adba] text-[15px] leading-relaxed mb-4">
            Ele funciona com vídeos de jogo, mas entrega o máximo de precisão em{" "}
            <span className="text-grnl">treinos com câmera fixa</span>: ao marcar a área do
            campo uma vez, as medidas ficam reais. Em transmissões com cortes e zoom, o
            sistema compensa o movimento da câmera e entrega uma boa estimativa — ideal para
            escolinhas, times amadores e análise de treino.
          </p>
          <Link href="/register" className="btn-primary inline-block px-6 py-2.5 text-sm mt-2">
            Criar conta grátis
          </Link>
        </div>
      </section>
      <Footer />
    </>
  );
}
