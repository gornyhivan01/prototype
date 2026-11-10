import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api } from "./api";
import type { User } from "./types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function restore(): Promise<void> {
      try {
        // Если сессии нет, /auth/profile ответит 401 и refresh-токен тоже
        // отсутствует — тихо переходим на экран входа.
        const profile = await api.profile();
        if (!cancelled) {
          setUser(profile);
        }
      } catch {
        // Сессия не восстановилась — интерфейс показывает экран входа.
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void restore();
    return () => {
      cancelled = true;
    };
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      // Сервер мог уже отозвать сессию — cookie чистим локально.
    }
    setUser(null);
  }, []);

  useEffect(() => {
    window.addEventListener("prototype:unauthorized", logout);
    return () => window.removeEventListener("prototype:unauthorized", logout);
  }, [logout]);

  const login = useCallback(async (email: string, password: string) => {
    const profile = await api.login(email, password);
    setUser(profile);
  }, []);

  const register = useCallback(async (email: string, password: string, name: string) => {
    await api.register(email, password, name);
    const profile = await api.login(email, password);
    setUser(profile);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth должен вызываться внутри AuthProvider");
  }
  return context;
}
