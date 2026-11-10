import { useCallback, useEffect, useState } from "react";

import { api, errorMessage } from "../api";
import { useAuth } from "../auth";
import type { AuditEntry, Page } from "../types";

const PAGE_SIZE = 20;

const ACTION_LABELS: Record<string, string> = {
  "user.created": "Создание пользователя",
  "user.deleted": "Удаление пользователя",
  "user.role_changed": "Смена роли",
  "auth.login.success": "Вход выполнен",
  "auth.login.failed": "Вход отклонён",
  "auth.logout": "Выход",
  "auth.token.reused": "Повторное использование токена",
  "task.created": "Создание задачи",
  "task.updated": "Изменение задачи",
  "task.deleted": "Удаление задачи",
};

function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action;
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "medium" });
}

function formatDetails(details: Record<string, unknown> | null): string {
  if (!details) {
    return "—";
  }
  return Object.entries(details)
    .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(", ") : String(value)}`)
    .join("; ");
}

export function AuditPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "ADMIN";

  const [page, setPage] = useState<Page<AuditEntry> | null>(null);
  const [offset, setOffset] = useState(0);
  const [action, setAction] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const filter = action || undefined;
      setPage(
        isAdmin
          ? await api.audit(PAGE_SIZE, offset, filter)
          : await api.myAudit(PAGE_SIZE, offset, filter),
      );
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [action, isAdmin, offset]);

  useEffect(() => {
    void load();
  }, [load]);

  function changeAction(value: string): void {
    setAction(value);
    setOffset(0);
  }

  const total = page?.total ?? 0;
  const shownFrom = total === 0 ? 0 : offset + 1;
  const shownTo = Math.min(offset + PAGE_SIZE, total);

  return (
    <section className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">{isAdmin ? "Журнал аудита" : "Мои действия"}</h1>
          <p className="page-subtitle">
            {isAdmin
              ? `События всех пользователей: ${total}`
              : `События вашей учётной записи: ${total}`}
          </p>
        </div>
      </div>

      <div className="card filters">
        <label className="field inline">
          <span>Действие</span>
          <select value={action} onChange={(event) => changeAction(event.target.value)}>
            <option value="">Все</option>
            {Object.keys(ACTION_LABELS).map((name) => (
              <option key={name} value={name}>
                {actionLabel(name)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <div className="alert error">{error}</div>}

      <div className="card">
        {loading ? (
          <p className="muted">Загрузка…</p>
        ) : page !== null && page.items.length === 0 ? (
          <div className="empty">
            <p>Событий нет</p>
            <p className="muted">Здесь появятся действия, подходящие под фильтр.</p>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Время</th>
                <th>Действие</th>
                <th>Кто</th>
                <th>Email</th>
                <th>Детали</th>
              </tr>
            </thead>
            <tbody>
              {page?.items.map((entry) => (
                <tr key={entry.id}>
                  <td>{formatDateTime(entry.created_at)}</td>
                  <td>
                    <div className="task-title">{actionLabel(entry.action)}</div>
                    <div className="task-description">{entry.action}</div>
                  </td>
                  <td>{entry.actor_id === null ? "—" : `#${entry.actor_id}`}</td>
                  <td>
                    {entry.email ?? "—"}
                    {entry.ip_address && (
                      <div className="task-description">IP: {entry.ip_address}</div>
                    )}
                  </td>
                  <td>
                    <span className="details-json">{formatDetails(entry.details)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="pagination">
        <span className="muted">
          {shownFrom}–{shownTo} из {total}
        </span>
        <div className="pagination-buttons">
          <button
            className="button small"
            type="button"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Назад
          </button>
          <button
            className="button small"
            type="button"
            disabled={shownTo >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Вперёд
          </button>
        </div>
      </div>
    </section>
  );
}
