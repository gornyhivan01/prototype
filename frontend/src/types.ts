export type Role = "USER" | "ADMIN";
export type TaskStatus = "pending" | "in_progress" | "done";
export type TaskPriority = "low" | "medium" | "high";

export interface User {
  id: number;
  email: string;
  name: string;
  role: Role;
  created_at: string;
}

export interface Task {
  id: number;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  deadline: string | null;
  user_id: number | null;
  archived_at: string | null;
  archived_owner_email: string | null;
  created_at: string;
  updated_at: string;
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

export interface Page<T> {
  total: number;
  limit: number;
  offset: number;
  items: T[];
}

export interface TaskPayload {
  title: string;
  description?: string | null;
  status?: TaskStatus;
  priority?: TaskPriority;
  deadline?: string | null;
}

export interface TaskQuery {
  status?: TaskStatus | "";
  priority?: TaskPriority | "";
  deadline_from?: string;
  deadline_to?: string;
  archived?: boolean;
  limit: number;
  offset: number;
}

export interface UserPayload {
  email: string;
  password: string;
  name: string;
  role: Role;
}
