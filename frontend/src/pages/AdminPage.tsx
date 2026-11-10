import { useCallback, useEffect, useState, type FormEvent } from "react";

import { api, errorMessage } from "../api";
import { useAuth } from "../auth";
import type { Page, Role, User } from "../types";

const PAGE_SIZE = 20;

interface UserForm {
  email: string;
  password: string;
  name: string;
  role: Role;
}

const EMPTY_FORM: UserForm = { email: "", password: "", name: "", role: "USER" };

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("ru-RU");
}

export function AdminPage() {
  const { user: currentUser } = useAuth();
  const [page, setPage] = useState<Page<User> | null>(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);

  const [form, setForm] = useState<UserForm | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      setPage(await api.users(PAGE_SIZE, offset));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [offset]);

  useEffect(() => {
    void load();
  }, [load]);

  async function changeRole(user: User, role: Role): Promise<void> {
    setSavingId(user.id);
    setError(null);
    try {
      await api.setRole(user.id, role);
      await load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSavingId(null);
    }
  }

  async function removeUser(user: User): Promise<void> {
    const confirmation = window.confirm(
      `Удалить пользователя ${user.email}?\n\nЕго задачи не пропадут: они перейдут в архив и останутся доступны администратору.`,
    );
    if (!confirmation) {
      return;
    }
    setSavingId(user.id);
    setError(null);
    try {
      await api.deleteUser(user.id);
      if (offset > 0 && page !== null && page.items.length === 1) {
        setOffset(Math.max(0, offset - PAGE_SIZE));
      } else {
        await load();
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSavingId(null);
    }
  }

  async function submitForm(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!form) {
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      await api.createUser({
        email: form.email.trim(),
        password: form.password,
        name: form.name.trim(),
        role: form.role,
      });
      setForm(null);
      await load();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  const total = page?.total ?? 0;
  const shownFrom = total === 0 ? 0 : offset + 1;
  const shownTo = Math.min(offset + PAGE_SIZE, total);

  return (
    <section className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Пользователи</h1>
          <p className="page-subtitle">Всего пользователей: {total}</p>
        </div>
        <button className="button primary" type="button" onClick={() => setForm({ ...EMPTY_FORM })}>
          Создать пользователя
        </button>
      </div>

      {error && <div className="alert error">{error}</div>}

      <div className="card">
        {loading ? (
          <p className="muted">Загрузка…</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Пользователь</th>
                <th>Email</th>
                <th>Роль</th>
                <th>Создан</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {page?.items.map((user) => {
                const isSelf = currentUser?.id === user.id;
                return (
                  <tr key={user.id}>
                    <td>
                      <div className="task-title">{user.name}</div>
                      <div className="task-description">#{user.id}</div>
                    </td>
                    <td>{user.email}</td>
                    <td>
                      <select
                        className="role-select"
                        value={user.role}
                        disabled={savingId === user.id}
                        onChange={(event) => void changeRole(user, event.target.value as Role)}
                      >
                        <option value="USER">USER</option>
                        <option value="ADMIN">ADMIN</option>
                      </select>
                    </td>
                    <td>{formatDate(user.created_at)}</td>
                    <td className="row-actions">
                      <button
                        className="button small danger"
                        type="button"
                        disabled={isSelf || savingId === user.id}
                        title={isSelf ? "Нельзя удалить собственную учётную запись" : undefined}
                        onClick={() => void removeUser(user)}
                      >
                        Удалить
                      </button>
                    </td>
                  </tr>
                );
              })}
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
        <div className="modal-backdrop" role="dialog" aria-modal="true">
          <form className="card modal" onSubmit={submitForm}>
            <h2 className="modal-title">Новый пользователь</h2>
            {formError && <div className="alert error">{formError}</div>}
            <label className="field">
              <span>Имя</span>
              <input
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                maxLength={200}
                required
                autoFocus
              />
            </label>
            <label className="field">
              <span>Email</span>
              <input
                type="email"
                value={form.email}
                onChange={(event) => setForm({ ...form, email: event.target.value })}
                required
              />
            </label>
            <div className="modal-grid">
              <label className="field">
                <span>Пароль</span>
                <input
                  type="password"
                  value={form.password}
                  onChange={(event) => setForm({ ...form, password: event.target.value })}
                  minLength={8}
                  maxLength={72}
                  required
                />
              </label>
              <label className="field">
                <span>Роль</span>
                <select
                  value={form.role}
                  onChange={(event) => setForm({ ...form, role: event.target.value as Role })}
                >
                  <option value="USER">USER</option>
                  <option value="ADMIN">ADMIN</option>
                </select>
              </label>
            </div>
            <div className="modal-actions">
              <button className="button ghost" type="button" onClick={() => setForm(null)}>
                Отмена
              </button>
              <button className="button primary" type="submit" disabled={saving}>
                {saving ? "Создаём…" : "Создать"}
              </button>
            </div>
          </form>
        </div>
      )}
    </section>
  );
}
