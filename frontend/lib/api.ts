// ============================================================
// api.ts — cliente central da API do FieldEye.
// Todas as chamadas passam pelo gateway (NEXT_PUBLIC_API_URL) e enviam
// o token JWT (guardado no navegador) no cabeçalho Authorization.
// ============================================================

// URL base do gateway. Em dev/local aponta para o Traefik na porta 80.
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost";

// ---- Token de autenticação (guardado no localStorage do navegador) ----
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("fieldeye_token");
}
export function setToken(token: string) {
  localStorage.setItem("fieldeye_token", token);
}
export function clearToken() {
  localStorage.removeItem("fieldeye_token");
}

// Função base: monta a requisição, adiciona o token e trata erros.
async function req(path: string, options: RequestInit = {}) {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  // Não forçamos Content-Type em uploads (FormData define sozinho).
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API}${path}`, { ...options, headers });
  if (!res.ok) {
    // Tenta extrair a mensagem de erro do backend (campo "detail").
    let msg = `Erro ${res.status}`;
    try {
      const data = await res.json();
      if (data.detail) msg = data.detail;
    } catch {}
    throw new Error(msg);
  }
  // Alguns endpoints (ex.: delete) podem não devolver JSON.
  const texto = await res.text();
  return texto ? JSON.parse(texto) : null;
}

// ---- Autenticação ----
export const auth = {
  register: (email: string, password: string, team_name?: string) =>
    req("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, team_name }),
    }),
  login: (email: string, password: string) =>
    req("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => req("/api/auth/me"),
};

// ---- Vídeos / jobs ----
export const videos = {
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req("/api/videos/upload", { method: "POST", body: form });
  },
  list: () => req("/api/videos/jobs"),
  get: (id: string) => req(`/api/videos/jobs/${id}`),
  remove: (id: string) => req(`/api/videos/jobs/${id}`, { method: "DELETE" }),
};

// ---- Resultados / analytics ----
export const analytics = {
  result: (id: string) => req(`/api/analytics/${id}`),
  players: (id: string) => req(`/api/analytics/${id}/players`),
  timeline: (id: string) => req(`/api/analytics/${id}/timeline`),
  heatmap: (id: string, playerId: number) =>
    req(`/api/analytics/${id}/heatmap/${playerId}`),
  // URLs de download (abertas direto no navegador).
  csvUrl: (id: string) => `${API}/api/analytics/${id}/export/csv`,
  pdfUrl: (id: string) => `${API}/api/analytics/${id}/export/pdf`,
};
