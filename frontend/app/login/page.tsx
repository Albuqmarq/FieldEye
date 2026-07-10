"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { auth, setToken } from "@/lib/api";
import FieldLogo from "@/components/FieldLogo";

export default function Login() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);

  async function entrar(e: React.FormEvent) {
    e.preventDefault();
    setErro("");
    setCarregando(true);
    try {
      const r = await auth.login(email, senha);
      setToken(r.access_token);          // guarda o token no navegador
      router.push("/painel");            // vai para a área logada
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Falha ao entrar.");
    } finally {
      setCarregando(false);
    }
  }

  return (
    <div className="flex-1 flex items-center justify-center bg-ink px-4 py-12">
      <form onSubmit={entrar} className="card p-6 w-[320px]">
        <Link href="/" className="flex items-center gap-2 justify-center text-fg font-medium text-base mb-1.5">
          <FieldLogo size={30} /> FieldEye
        </Link>
        <p className="text-center text-mut text-[13px] mb-5">Entrar na sua conta</p>

        <label className="block text-xs text-mut mb-1.5">E-mail</label>
        <input className="input mb-3.5" type="email" value={email}
          onChange={(e) => setEmail(e.target.value)} placeholder="voce@email.com" required />

        <label className="block text-xs text-mut mb-1.5">Senha</label>
        <input className="input mb-5" type="password" value={senha}
          onChange={(e) => setSenha(e.target.value)} placeholder="••••••••" required />

        {erro && <p className="text-red-400 text-xs mb-3">{erro}</p>}

        <button type="submit" disabled={carregando}
          className="btn-primary w-full py-2.5 text-sm disabled:opacity-60">
          {carregando ? "Entrando..." : "Entrar"}
        </button>

        <p className="text-center text-xs text-mut mt-4">
          Não tem conta? <Link href="/register" className="text-grnl">Criar conta</Link>
        </p>
      </form>
    </div>
  );
}
