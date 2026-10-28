import { getToken } from "./token";

export type Role = "admin" | "user";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  created_at: string;
}

export interface UserCreate {
  email: string;
  full_name: string;
  password: string;
  role: Role;
}

export interface AuditEntry {
  id: number;
  action: string;
  actor_id: number | null;
  target_user_id: number | null;
  email: string | null;
  ip_address: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface AuditPage {
  total: number;
  limit: number;
  offset: number;
  items: AuditEntry[];
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Сообщение об ошибке, пригодное для показа пользователю. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Неизвестная ошибка";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(path, { ...init, headers });
  if (response.status === 204) {
    return undefined as T;
  }

  const body = (await response.json().catch(() => null)) as {
    detail?: string;
  } | null;
  if (!response.ok) {
    throw new ApiError(response.status, body?.detail ?? `HTTP ${response.status}`);
  }
  return body as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, payload: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(payload) }),
  delete: (path: string) => request<void>(path, { method: "DELETE" }),
};

export function roleLabel(role: Role): string {
  return role === "admin" ? "Администратор" : "Пользователь";
}
