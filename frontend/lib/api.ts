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
export type UploadOpts = {
  mode?: string;
  area?: string;
  fieldType?: string; // "futebol" | "futsal" | "society" (campo oficial)
  fieldPoints?: { x: number; y: number }[]; // cantos do campo (px do vídeo)
};

export const videos = {
  upload: (file: File, opts: UploadOpts = {}) => {
    const form = new FormData();
    form.append("file", file);
    if (opts.mode) form.append("mode", opts.mode);
    if (opts.area) form.append("area", opts.area);
    if (opts.fieldType) form.append("field_type", opts.fieldType);
    // Os pontos vão como JSON; o backend converte para a homografia.
    if (opts.fieldPoints && opts.fieldPoints.length === 4) {
      form.append("field_points", JSON.stringify(opts.fieldPoints.map((p) => [p.x, p.y])));
    }
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
  // Download de CSV/PDF. Os endpoints exigem o token JWT, então NÃO dá para
  // usar um <a href> simples (não envia o Authorization). Buscamos com fetch
  // autenticado, viramos um blob e disparamos o download no navegador.
  download: async (id: string, kind: "csv" | "pdf") => {
    const token = getToken();
    const res = await fetch(`${API}/api/analytics/${id}/export/${kind}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(`Erro ao gerar ${kind.toUpperCase()} (${res.status})`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `fieldeye_${id}.${kind}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
};
