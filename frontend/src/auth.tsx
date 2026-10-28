import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  clearToken,
  consumeTokenFromHash,
  getToken,
  setToken as storeToken,
} from "./token";

interface AuthState {
  token: string | null;
  signIn: (token: string) => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  // При первом рендере забираем токен из фрагмента (после SSO-callback)
  // либо из sessionStorage (переход между страницами/перезагрузка).
  const [token, setTokenState] = useState<string | null>(
    () => consumeTokenFromHash() ?? getToken(),
  );

  const signIn = useCallback((next: string) => {
    storeToken(next);
    setTokenState(next);
  }, []);

  const signOut = useCallback(() => {
    clearToken();
    setTokenState(null);
  }, []);

  const value = useMemo(
    () => ({ token, signIn, signOut }),
    [token, signIn, signOut],
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
