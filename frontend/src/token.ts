/** Работа с access-токеном сервиса в браузере.
 *
 * После SSO токен приходит во фрагменте URL (`/dashboard#access_token=…`):
 * фрагмент не уходит на сервер и не попадает в access-логи. Сразу после
 * чтения убираем его из адресной строки, а токен держим в sessionStorage:
 * он живёт до закрытия вкладки и не шарится между вкладками.
 */

export const TOKEN_KEY = "prototype_access_token";

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

/** Забирает токен из `#access_token=…`, сохраняет и чистит URL. */
export function consumeTokenFromHash(): string | null {
  const params = new URLSearchParams(window.location.hash.slice(1));
  const token = params.get("access_token");
  if (!token) {
    return null;
  }
  setToken(token);
  window.history.replaceState(
    null,
    "",
    window.location.pathname + window.location.search,
  );
  return token;
}
