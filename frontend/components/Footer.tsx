import Link from "next/link";
import FieldLogo from "./FieldLogo";

// Rodapé do site com marca, links e contato de suporte.
export default function Footer() {
  return (
    <footer className="px-6 pt-8 pb-5 bg-foot border-t border-line">
      <div className="flex flex-wrap gap-6 justify-between">
        <div className="max-w-[250px]">
          <div className="flex items-center gap-2 text-fg font-medium text-[15px] mb-2">
            <FieldLogo size={28} />
            FieldEye
          </div>
          <p className="text-xs text-mut leading-relaxed">
            Análise inteligente de desempenho em futebol.
          </p>
        </div>
        <div>
          <div className="text-xs text-[#6b7280] mb-2.5 tracking-wide">Links</div>
          <Link href="/#sobre" className="nav-link block text-[13px] mb-1.5">Sobre</Link>
          <Link href="/#recursos" className="nav-link block text-[13px] mb-1.5">Recursos</Link>
          <Link href="/#contato" className="nav-link block text-[13px]">Contato</Link>
        </div>
        <div id="contato">
          <div className="text-xs text-[#6b7280] mb-2.5 tracking-wide">Suporte</div>
          <div className="text-[13px] text-mut mb-1.5">[seu email]</div>
          <div className="text-[13px] text-mut">[seu whatsapp]</div>
        </div>
      </div>
      <div className="border-t border-[#1c1c1c] mt-5 pt-3.5 text-[11px] text-[#6b7280]">
        © 2026 FieldEye. Todos os direitos reservados.
      </div>
    </footer>
  );
}
