import { createContext, useContext, useMemo, useState, ReactNode } from "react";
import { api, clearSession, getUser, Role } from "./api";

interface AuthState {
  role: Role | null;
  username: string | null;
  signIn: (u: string, p: string) => Promise<void>;
  signOut: () => void;
}

const Ctx = createContext<AuthState>(null as any);

const RANK: Record<Role, number> = { viewer: 1, analyst: 2, admin: 3 };

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState(getUser());

  const value = useMemo<AuthState>(
    () => ({
      role: user?.role ?? null,
      username: user?.username ?? null,
      async signIn(username, password) {
        const session = await api.login(username, password);
        setUser({ role: session.role, username: session.username });
      },
      signOut() {
        clearSession();
        setUser(null);
      },
    }),
    [user]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  return useContext(Ctx);
}

/** Client-side convenience only. The real gate is on the API. */
export function can(role: Role | null, required: Role) {
  if (!role) return false;
  return RANK[role] >= RANK[required];
}