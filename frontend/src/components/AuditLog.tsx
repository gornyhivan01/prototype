import { useCallback, useEffect, useState, type FormEvent } from "react";

import {
  api,
  errorMessage,
  type AuditEntry,
  type AuditPage,
} from "../api";

const PAGE_SIZE = 20;

const ACTION_OPTIONS = [
  { value: "", label: "Все действия" },
  { value: "user.created", label: "Создание пользователя" },
  { value: "user.deleted", label: "Удаление пользователя" },
  { value: "auth.login.success", label: "Успешный вход" },
  { value: "auth.login.failed", label: "Неудачный вход" },
];

const ACTION_LABELS: Record<string, string> = Object.fromEntries(
  ACTION_OPTIONS.filter((option) => option.value).map((option) => [
    option.value,
    option.label,
  ]),
);

export function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action;
}

function formatDetails(details: Record<string, unknown> | null): string {
  if (!details || Object.keys(details).length === 0) {
    return "—";
  }
  return JSON.stringify(details);
}

interface Props {
  /** all — полный журнал (админ), me — только свои события. */
  mode: "all" | "me";
}

export function AuditLog({ mode }: Props) {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [action, setAction] = useState("");
  const [emailInput, setEmailInput] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const endpoint = mode === "all" ? "/audit" : "/audit/me";

  const load = useCallback(
    async (offset: number, append: boolean) => {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams({
          limit: String(PAGE_SIZE),
          offset: String(offset),
        });
        if (action) {
          params.set("action", action);
        }
        if (mode === "all" && email) {
          params.set("email", email);
        }
        const page = await api.get<AuditPage>(`${endpoint}?${params.toString()}`);
        setTotal(page.total);
        setEntries((previous) => (append ? [...previous, ...page.items] : page.items));
      } catch (err) {
        setError(errorMessage(err));
      } finally {
        setLoading(false);
      }
    },
    [action, email, endpoint, mode],
  );

  useEffect(() => {
    void load(0, false);
  }, [load]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setEmail(emailInput.trim());
  }

  return (
    <section>
      <div className="topline">
        <h2>{mode === "all" ? "Журнал аудита" : "Мои действия"}</h2>
        <button
          className="btn ghost small"
          type="button"
          disabled={loading}
          onClick={() => void load(0, false)}
        >
          Обновить
        </button>
      </div>
      <p className="muted small">
        {mode === "all"
          ? "Все события сервиса, новые сверху. Пароли и токены в журнал не попадают."
          : "Ваши входы и события, касающиеся вашей учётной записи."}
      </p>

      <form className="filters" onSubmit={applyFilters}>
        <label>
          Действие
          <select value={action} onChange={(event) => setAction(event.target.value)}>
            {ACTION_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        {mode === "all" ? (
          <label>
            Email содержит
            <input
              type="text"
              value={emailInput}
              placeholder="например, example.com"
              onChange={(event) => setEmailInput(event.target.value)}
            />
          </label>
        ) : null}
        <button className="btn small" type="submit" disabled={loading}>
          Применить
        </button>
      </form>

      {error ? <p className="error small">{error}</p> : null}

      <div className="table-wrap">
        <table className="table audit">
          <thead>
            <tr>
              <th>Время</th>
              <th>Действие</th>
              {mode === "all" ? (
                <>
                  <th>Кто</th>
                  <th>Объект</th>
                </>
              ) : null}
              <th>Email</th>
              <th>IP</th>
              <th>Детали</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.id}>
                <td>{new Date(entry.created_at).toLocaleString("ru-RU")}</td>
                <td title={entry.action}>{actionLabel(entry.action)}</td>
                {mode === "all" ? (
                  <>
                    <td>{entry.actor_id ?? "—"}</td>
                    <td>{entry.target_user_id ?? "—"}</td>
                  </>
                ) : null}
                <td>{entry.email ?? "—"}</td>
                <td>{entry.ip_address ?? "—"}</td>
                <td className="details">{formatDetails(entry.details)}</td>
              </tr>
            ))}
            {!loading && entries.length === 0 ? (
              <tr>
                <td colSpan={mode === "all" ? 7 : 5} className="muted">
                  Записей нет
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <div className="audit-footer">
        {loading && entries.length === 0 ? (
          <span className="muted small">Загрузка…</span>
        ) : (
          <span className="muted small">
            Показано {entries.length} из {total}
          </span>
        )}
        {!loading && entries.length < total ? (
          <button
            className="btn ghost small"
            type="button"
            disabled={loading}
            onClick={() => void load(entries.length, true)}
          >
            Показать ещё
          </button>
        ) : null}
      </div>
    </section>
  );
}
