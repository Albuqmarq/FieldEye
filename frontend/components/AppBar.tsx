"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { clearToken } from "@/lib/api";
import FieldLogo from "./FieldLogo";

// Barra superior das páginas logadas (painel/resultados).
export default function AppBar({ time = "Meu time" }: { time?: string }) {
  const router = useRouter();
  const iniciais = time.slice(0, 2).toUpperCase();

  function sair() {
    clearToken();
    router.push("/login");
  }

  return (
    <header className="flex items-center justify-between px-4 py-3 border-b border-line bg-ink">
      <Link href="/painel" className="flex items-center gap-2 text-fg font-medium text-[15px]">
        <FieldLogo size={28} /> FieldEye
      </Link>
      <div className="flex items-center gap-3 text-[13px] text-mut">
        <Link href="/" className="hover:text-fg hidden sm:inline">Início</Link>
        <Link href="/perfil" className="flex items-center gap-2 hover:text-fg" title="Meu perfil">
          <span>{time}</span>
          <span className="w-7 h-7 rounded-full inline-flex items-center justify-center text-white text-xs" style={{ background: "#1f8049" }}>
            {iniciais}
          </span>
        </Link>
        <button onClick={sair} className="text-mut hover:text-fg">Sair</button>
      </div>
    </header>
  );
}
