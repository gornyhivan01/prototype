import type {
  AuditEntry,
  Page,
  Role,
  Task,
  TaskPayload,
  TaskQuery,
  User,
  UserPayload,
} from "./types";

// Токены сессии лежат в HttpOnly-cookie: JavaScript их не видит. Единственное,
// что доступно фронтенду, — CSRF-токен: он читается из cookie и повторяется
// в заголовке при unsafe-запросах (схема double-submit cookie).
const CSRF_COOKIE = "csrf_token";
const CSRF_HEADER = "X-CSRF-Token";
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

// Эти ручки не пытаются обновить сессию: 401 здесь означает неверные данные
// или отсутствие refresh-токена, а не истёкший access-токен.
const NO_REFRESH_PATHS = new Set(["/auth/login", "/auth/register", "/auth/token", "/auth/refresh"]);

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Что-то пошло не так";
}

function readCookie(name: string): string | null {
  const prefix = `${name}=`;
  for (const part of document.cookie.split(";")) {
    const item = part.trim();
    if (item.startsWith(prefix)) {
      return decodeURIComponent(item.slice(prefix.length));
    }
  }
  return null;
}

function formatDetail(detail: unknown): string {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const entry = item as { loc?: (string | number)[]; msg?: string };
        const field = entry.loc?.filter((part) => part !== "body").join(".");
        return field ? `${field}: ${entry.msg ?? ""}` : String(entry.msg ?? "");
      })
      .join("; ");
  }
  return "Ошибка запроса";
}

function buildQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

function csrfHeaders(): Headers {
  const headers = new Headers();
  const token = readCookie(CSRF_COOKIE);
  if (token) {
    headers.set(CSRF_HEADER, token);
  }
  return headers;
}

// Один общий запрос на обновление: параллельные 401 не должны ротировать
// refresh-токен несколько раз (второй запрос выглядел бы как кража).
let refreshPromise: Promise<boolean> | null = null;

function refreshSession(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = fetch("/auth/refresh", {
      method: "POST",
      credentials: "same-origin",
      headers: csrfHeaders(),
    })
      .then((response) => response.ok)
      .catch(() => false)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

interface RequestOptions {
  /** Пробовать ли тихо обновить сессию при 401. */
  retryOnUnauthorized?: boolean;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  options: RequestOptions = {},
): Promise<T> {
  const { retryOnUnauthorized = true } = options;
  const method = (init.method ?? "GET").toUpperCase();

  const headers = new Headers(init.headers);
  if (init.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (UNSAFE_METHODS.has(method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) {
      headers.set(CSRF_HEADER, csrf);
    }
  }

  const response = await fetch(path, { ...init, headers, credentials: "same-origin" });

  if (response.status === 401 && retryOnUnauthorized && !NO_REFRESH_PATHS.has(path)) {
    if (await refreshSession()) {
      return request<T>(path, init, { retryOnUnauthorized: false });
    }
    // Сессия не восстановилась: разлогиниваем интерфейс.
    window.dispatchEvent(new Event("prototype:unauthorized"));
    throw new ApiError(401, "Сессия истекла, войдите заново");
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  const data: unknown = text ? JSON.parse(text) : null;

  if (!response.ok) {
    if (response.status === 401) {
      window.dispatchEvent(new Event("prototype:unauthorized"));
    }
    const detail = data && typeof data === "object" ? (data as { detail?: unknown }).detail : undefined;
    throw new ApiError(response.status, formatDetail(detail));
  }
  return data as T;
}

export const api = {
  register(email: string, password: string, name: string): Promise<User> {
    return request<User>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, name }),
    });
  },

  login(email: string, password: string): Promise<User> {
    return request<User>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },

  logout(): Promise<void> {
    return request<void>("/auth/logout", { method: "POST" }, { retryOnUnauthorized: false });
  },

  profile(): Promise<User> {
    return request<User>("/auth/profile");
  },

  tasks(query: TaskQuery): Promise<Page<Task>> {
    return request<Page<Task>>(
      `/tasks${buildQuery({
        status: query.status,
        priority: query.priority,
        deadline_from: query.deadline_from,
        deadline_to: query.deadline_to,
        archived: query.archived ? "true" : undefined,
        limit: query.limit,
        offset: query.offset,
      })}`,
    );
  },

  createTask(payload: TaskPayload): Promise<Task> {
    return request<Task>("/tasks", { method: "POST", body: JSON.stringify(payload) });
  },

  updateTask(id: number, payload: Partial<TaskPayload>): Promise<Task> {
    return request<Task>(`/tasks/${id}`, { method: "PUT", body: JSON.stringify(payload) });
  },

  deleteTask(id: number): Promise<void> {
    return request<void>(`/tasks/${id}`, { method: "DELETE" });
  },

  users(limit: number, offset: number): Promise<Page<User>> {
    return request<Page<User>>(`/admin/users${buildQuery({ limit, offset })}`);
  },

  createUser(payload: UserPayload): Promise<User> {
    return request<User>("/admin/users", { method: "POST", body: JSON.stringify(payload) });
  },

  deleteUser(id: number): Promise<void> {
    return request<void>(`/admin/users/${id}`, { method: "DELETE" });
  },

  setRole(id: number, role: Role): Promise<User> {
    return request<User>(`/admin/users/${id}/role`, {
      method: "PUT",
      body: JSON.stringify({ role }),
    });
  },

  audit(limit: number, offset: number, action?: string): Promise<Page<AuditEntry>> {
    return request<Page<AuditEntry>>(
      `/audit${buildQuery({ action, limit, offset })}`,
    );
  },

  myAudit(limit: number, offset: number, action?: string): Promise<Page<AuditEntry>> {
    return request<Page<AuditEntry>>(
      `/audit/me${buildQuery({ action, limit, offset })}`,
    );
  },
};
