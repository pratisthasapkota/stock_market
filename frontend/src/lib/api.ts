const BASE = (import.meta.env.VITE_API_BASE as string) || "";

export type Role = "viewer" | "analyst" | "admin";

export interface Session {
  access_token: string;
  role: Role;
  username: string;
}

const TOKEN_KEY = "nepse.token";
const USER_KEY = "nepse.user";

export function saveSession(s: Session) {
  localStorage.setItem(TOKEN_KEY, s.access_token);
  localStorage.setItem(
    USER_KEY,
    JSON.stringify({ role: s.role, username: s.username })
  );
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getUser(): { role: Role; username: string } | null {
  const raw = localStorage.getItem(USER_KEY);
  return raw ? JSON.parse(raw) : null;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (res.status === 401) {
    clearSession();
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* non-json error body */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  async login(username: string, password: string): Promise<Session> {
    const form = new URLSearchParams({ username, password });
    const res = await fetch(`${BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form,
    });
    if (!res.ok) throw new ApiError(res.status, "Login failed");
    const data = (await res.json()) as Session;
    saveSession(data);
    return data;
  },

  companies: () => request<any[]>("/api/companies"),
  addCompany: (payload: any) =>
    request("/api/companies", { method: "POST", body: JSON.stringify(payload) }),
  prices: (id: number, range = "30d") =>
    request<any[]>(`/api/companies/${id}/prices?range=${range}`),
  behavior: (id: number) => request<any>(`/api/companies/${id}/behavior-summary`),
  comparison: () => request<any>("/api/companies/comparison"),

  news: (params: { company_id?: number; q?: string; source?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.company_id) qs.set("company_id", String(params.company_id));
    if (params.q) qs.set("q", params.q);
    if (params.source) qs.set("source", params.source);
    return request<any[]>(`/api/news?${qs.toString()}`);
  },
  recategorize: (id: number, company_id: number, action: "add" | "remove") =>
    request(`/api/news/${id}/recategorize`, {
      method: "POST",
      body: JSON.stringify({ company_id, action }),
    }),

  crawlRuns: () => request<any[]>("/api/admin/crawl-runs"),
  triggerCrawl: (portal: string) =>
    request(`/api/admin/crawl-runs?portal=${portal}`, { method: "POST" }),
  retryRun: (id: number) =>
    request(`/api/admin/crawl-runs/${id}/retry`, { method: "POST" }),
  retag: () => request("/api/admin/retag", { method: "POST" }),
  users: () => request<any[]>("/api/admin/users"),
  setRole: (id: number, role: Role) =>
    request(`/api/admin/users/${id}/role?role=${role}`, { method: "POST" }),
};
