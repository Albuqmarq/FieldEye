"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { auth, setToken } from "@/lib/api";
import FieldLogo from "@/components/FieldLogo";

export default function Register() {
  const router = useRouter();
  const [time, setTime] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);

  async function cadastrar(e: React.FormEvent) {
    e.preventDefault();
    setErro("");
    setCarregando(true);
    try {
      // Cria a conta e já faz login para entrar direto.
      await auth.register(email, senha, time || undefined);
      const r = await auth.login(email, senha);
      setToken(r.access_token);
      router.push("/painel");
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Falha ao criar conta.");
    } finally {
      setCarregando(false);
    }
  }

  return (
    <div className="flex-1 flex items-center justify-center bg-ink px-4 py-12">
      <form onSubmit={cadastrar} className="card p-6 w-[320px]">
        <Link href="/" className="flex items-center gap-2 justify-center text-fg font-medium text-base mb-1.5">
          <FieldLogo size={30} /> FieldEye
        </Link>
        <p className="text-center text-mut text-[13px] mb-5">Criar sua conta grátis</p>

        <label className="block text-xs text-mut mb-1.5">
          Nome do time <span className="text-[#6b7280]">(opcional)</span>
        </label>
        <input className="input mb-3.5" type="text" value={time}
          onChange={(e) => setTime(e.target.value)} placeholder="Meu time FC" />

        <label className="block text-xs text-mut mb-1.5">E-mail</label>
        <input className="input mb-3.5" type="email" value={email}
          onChange={(e) => setEmail(e.target.value)} placeholder="voce@email.com" required />

        <label className="block text-xs text-mut mb-1.5">Senha</label>
        <input className="input mb-5" type="password" value={senha}
          onChange={(e) => setSenha(e.target.value)} placeholder="mínimo 8 caracteres" required />

        {erro && <p className="text-red-400 text-xs mb-3">{erro}</p>}

        <button type="submit" disabled={carregando}
          className="btn-primary w-full py-2.5 text-sm disabled:opacity-60">
          {carregando ? "Criando..." : "Criar conta"}
        </button>

        <p className="text-center text-xs text-mut mt-4">
          Já tem conta? <Link href="/login" className="text-grnl">Entrar</Link>
        </p>
      </form>
    </div>
  );
}
