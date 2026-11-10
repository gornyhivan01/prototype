import { useCallback, useEffect, useState, type FormEvent } from "react";

import { api, errorMessage } from "../api";
import { useAuth } from "../auth";
import type { Page, Task, TaskPriority, TaskStatus } from "../types";

const STATUS_LABELS: Record<TaskStatus, string> = {
  pending: "Ожидает",
  in_progress: "В работе",
  done: "Готово",
};

const PRIORITY_LABELS: Record<TaskPriority, string> = {
  low: "Низкий",
  medium: "Средний",
  high: "Высокий",
};

const PAGE_SIZE = 10;

interface Filters {
  status: TaskStatus | "";
  priority: TaskPriority | "";
  deadlineFrom: string;
  deadlineTo: string;
}

interface FormValues {
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  deadline: string;
}

const EMPTY_FILTERS: Filters = { status: "", priority: "", deadlineFrom: "", deadlineTo: "" };

const EMPTY_FORM: FormValues = {
  title: "",
  description: "",
  status: "pending",
  priority: "medium",
  deadline: "",
};

function toLocalInput(iso: string | null): string {
  if (!iso) {
    return "";
  }
  const date = new Date(iso);
  const pad = (value: number): string => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function toIso(local: string): string | undefined {
  return local ? new Date(local).toISOString() : undefined;
}

function formatDateTime(iso: string | null): string {
  if (!iso) {
    return "—";
  }
  return new Date(iso).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" });
}

export function TasksPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "ADMIN";
  const [showArchive, setShowArchive] = useState(false);
  const [page, setPage] = useState<Page<Task> | null>(null);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState<FormValues | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.tasks({
        status: filters.status,
        priority: filters.priority,
        deadline_from: toIso(filters.deadlineFrom),
        deadline_to: toIso(filters.deadlineTo),
        archived: isAdmin && showArchive,
        limit: PAGE_SIZE,
        offset,
      });
      setPage(data);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [filters, offset, isAdmin, showArchive]);

  useEffect(() => {
    void load();
  }, [load]);

  function updateFilter(patch: Partial<Filters>): void {
    setFilters((current) => ({ ...current, ...patch }));
    setOffset(0);
  }

  function resetFilters(): void {
    setFilters(EMPTY_FILTERS);
    setOffset(0);
  }

  function openCreate(): void {
    setEditingId(null);
    setFormError(null);
    setForm({ ...EMPTY_FORM });
  }

  function openEdit(task: Task): void {
    setEditingId(task.id);
    setFormError(null);
    setForm({
      title: task.title,
      description: task.description ?? "",
      status: task.status,
      priority: task.priority,
      deadline: toLocalInput(task.deadline),
    });
  }

  function closeForm(): void {
    setForm(null);
    setEditingId(null);
    setFormError(null);
  }

  async function submitForm(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!form) {
      return;
    }
    setSaving(true);
    setFormError(null);
    const description = form.description.trim();
    const payload = {
      title: form.title.trim(),
      description: description.length > 0 ? description : null,
      status: form.status,
      priority: form.priority,
      deadline: form.deadline ? new Date(form.deadline).toISOString() : null,
    };
    try {
      if (editingId === null) {
        await api.createTask(payload);
      } else {
        await api.updateTask(editingId, payload);
      }
      closeForm();
      await load();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function removeTask(task: Task): Promise<void> {
    if (!window.confirm(`Удалить задачу «${task.title}»?`)) {
      return;
    }
    try {
      await api.deleteTask(task.id);
      if (offset > 0 && page !== null && page.items.length === 1) {
        setOffset(Math.max(0, offset - PAGE_SIZE));
      } else {
        await load();
      }
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  const total = page?.total ?? 0;
  const shownFrom = total === 0 ? 0 : offset + 1;
  const shownTo = Math.min(offset + PAGE_SIZE, total);

  return (
    <section className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">{showArchive ? "Архив задач" : "Задачи"}</h1>
          <p className="page-subtitle">
            {showArchive
              ? `Задачи удалённых пользователей: ${total}`
              : `Всего задач: ${total}`}
          </p>
        </div>
        <div className="page-actions">
          {isAdmin && (
            <button
              className={showArchive ? "button" : "button ghost"}
              type="button"
              onClick={() => {
                setShowArchive((current) => !current);
                setOffset(0);
              }}
            >
              {showArchive ? "Активные задачи" : "Архив"}
            </button>
          )}
          {!showArchive && (
            <button className="button primary" onClick={openCreate} type="button">
              Новая задача
            </button>
          )}
        </div>
      </div>

      <div className="card filters">
        <label className="field inline">
          <span>Статус</span>
          <select
            value={filters.status}
            onChange={(event) => updateFilter({ status: event.target.value as Filters["status"] })}
          >
            <option value="">Все</option>
            {(Object.keys(STATUS_LABELS) as TaskStatus[]).map((status) => (
              <option key={status} value={status}>
                {STATUS_LABELS[status]}
              </option>
            ))}
          </select>
        </label>
        <label className="field inline">
          <span>Приоритет</span>
          <select
            value={filters.priority}
            onChange={(event) =>
              updateFilter({ priority: event.target.value as Filters["priority"] })
            }
          >
            <option value="">Все</option>
            {(Object.keys(PRIORITY_LABELS) as TaskPriority[]).map((priority) => (
              <option key={priority} value={priority}>
                {PRIORITY_LABELS[priority]}
              </option>
            ))}
          </select>
        </label>
        <label className="field inline">
          <span>Дедлайн с</span>
          <input
            type="date"
            value={filters.deadlineFrom}
            onChange={(event) => updateFilter({ deadlineFrom: event.target.value })}
          />
        </label>
        <label className="field inline">
          <span>по</span>
          <input
            type="date"
            value={filters.deadlineTo}
            onChange={(event) => updateFilter({ deadlineTo: event.target.value })}
          />
        </label>
        <button className="button ghost" onClick={resetFilters} type="button">
          Сбросить
        </button>
      </div>

      {error && <div className="alert error">{error}</div>}

      <div className="card">
        {loading ? (
          <p className="muted">Загрузка…</p>
        ) : page !== null && page.items.length === 0 ? (
          <div className="empty">
            <p>{showArchive ? "Архив пуст" : "Задач нет"}</p>
            <p className="muted">
              {showArchive
                ? "Сюда попадают задачи пользователей после удаления их учётных записей."
                : "Создайте первую задачу — она появится здесь."}
            </p>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Задача</th>
                <th>Статус</th>
                <th>Приоритет</th>
                <th>{showArchive ? "Владелец" : "Дедлайн"}</th>
                <th>Обновлена</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {page?.items.map((task) => (
                <tr key={task.id}>
                  <td>
                    <div className="task-title">{task.title}</div>
                    {task.description && <div className="task-description">{task.description}</div>}
                  </td>
                  <td>
                    <span className={`badge status-${task.status}`}>{STATUS_LABELS[task.status]}</span>
                  </td>
                  <td>
                    <span className={`badge priority-${task.priority}`}>
                      {PRIORITY_LABELS[task.priority]}
                    </span>
                  </td>
                  <td>
                    {showArchive
                      ? (task.archived_owner_email ?? "—")
                      : formatDateTime(task.deadline)}
                  </td>
                  <td>{formatDateTime(task.updated_at)}</td>
                  <td className="row-actions">
                    {showArchive ? (
                      <span className="muted">в архиве с {formatDateTime(task.archived_at)}</span>
                    ) : (
                      <>
                        <button
                          className="button small"
                          type="button"
                          onClick={() => openEdit(task)}
                        >
                          Изменить
                        </button>
                        <button
                          className="button small danger"
                          type="button"
                          onClick={() => void removeTask(task)}
                        >
                          Удалить
                        </button>
                      </>
                    )}
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

      {form && (
        <TaskModal
          values={form}
          editing={editingId !== null}
          saving={saving}
          error={formError}
          onChange={(patch) => setForm({ ...form, ...patch })}
          onClose={closeForm}
          onSubmit={submitForm}
        />
      )}
    </section>
  );
}

interface TaskModalProps {
  values: FormValues;
  editing: boolean;
  saving: boolean;
  error: string | null;
  onChange: (patch: Partial<FormValues>) => void;
  onClose: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}

function TaskModal({ values, editing, saving, error, onChange, onClose, onSubmit }: TaskModalProps) {
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <form className="card modal" onSubmit={onSubmit}>
        <h2 className="modal-title">{editing ? "Изменить задачу" : "Новая задача"}</h2>
        {error && <div className="alert error">{error}</div>}
        <label className="field">
          <span>Заголовок</span>
          <input
            value={values.title}
            onChange={(event) => onChange({ title: event.target.value })}
            maxLength={200}
            required
            autoFocus
          />
        </label>
        <label className="field">
          <span>Описание</span>
          <textarea
            rows={3}
            value={values.description}
            onChange={(event) => onChange({ description: event.target.value })}
          />
        </label>
        <div className="modal-grid">
          <label className="field">
            <span>Статус</span>
            <select
              value={values.status}
              onChange={(event) => onChange({ status: event.target.value as TaskStatus })}
            >
              {(Object.keys(STATUS_LABELS) as TaskStatus[]).map((status) => (
                <option key={status} value={status}>
                  {STATUS_LABELS[status]}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Приоритет</span>
            <select
              value={values.priority}
              onChange={(event) => onChange({ priority: event.target.value as TaskPriority })}
            >
              {(Object.keys(PRIORITY_LABELS) as TaskPriority[]).map((priority) => (
                <option key={priority} value={priority}>
                  {PRIORITY_LABELS[priority]}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="field">
          <span>Дедлайн</span>
          <input
            type="datetime-local"
            value={values.deadline}
            onChange={(event) => onChange({ deadline: event.target.value })}
          />
        </label>
        <div className="modal-actions">
          <button className="button ghost" type="button" onClick={onClose}>
            Отмена
          </button>
          <button className="button primary" type="submit" disabled={saving}>
            {saving ? "Сохраняем…" : "Сохранить"}
          </button>
        </div>
      </form>
    </div>
  );
}
