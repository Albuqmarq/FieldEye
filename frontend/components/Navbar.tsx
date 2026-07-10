import Link from "next/link";
import FieldLogo from "./FieldLogo";

// Barra de navegação do site (landing/sobre).
export default function Navbar() {
  return (
    <header className="flex items-center justify-between px-5 py-3.5 border-b border-line bg-ink">
      <Link href="/" className="flex items-center gap-2 text-fg font-medium text-base">
        <FieldLogo size={34} />
        FieldEye
      </Link>
      <nav className="flex items-center gap-4 text-[13px]">
        <Link href="/sobre" className="nav-link">Sobre</Link>
        <Link href="/#como-funciona" className="nav-link">Como funciona</Link>
        <Link href="/#recursos" className="nav-link">Recursos</Link>
        <Link href="/login" className="nav-link">Entrar</Link>
        <Link href="/register" className="btn-primary px-3.5 py-1.5 text-[13px]">
          Criar conta
        </Link>
      </nav>
    </header>
  );
}
