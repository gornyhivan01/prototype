import { useState, type FormEvent } from "react";

import {
  api,
  errorMessage,
  roleLabel,
  type Role,
  type User,
  type UserCreate,
} from "../api";

const EMPTY_FORM: UserCreate = {
  email: "",
  full_name: "",
  password: "",
  role: "user",
};

export function CreateUserForm({
  onCreated,
}: {
  onCreated: (user: User) => Promise<void> | void;
}) {
  const [form, setForm] = useState<UserCreate>(EMPTY_FORM);
  const [created, setCreated] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setCreated(null);
    try {
      const user = await api.post<User>("/users", form);
      setCreated(`Создан ${user.email} (${roleLabel(user.role)}).`);
      setForm(EMPTY_FORM);
      await onCreated(user);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h3>Создать пользователя</h3>
      <form className="form" onSubmit={handleSubmit}>
        <label>
          Email
          <input
            type="email"
            value={form.email}
            autoComplete="off"
            required
            placeholder="user@example.com"
            onChange={(event) =>
              setForm({ ...form, email: event.target.value })
            }
          />
        </label>
        <label>
          Имя
          <input
            type="text"
            value={form.full_name}
            autoComplete="off"
            required
            placeholder="Иван Петров"
            onChange={(event) =>
              setForm({ ...form, full_name: event.target.value })
            }
          />
        </label>
        <label>
          Пароль
          <input
            type="password"
            value={form.password}
            minLength={8}
            autoComplete="new-password"
            required
            placeholder="не короче 8 символов"
            onChange={(event) =>
              setForm({ ...form, password: event.target.value })
            }
          />
        </label>
        <label>
          Роль
          <select
            value={form.role}
            onChange={(event) =>
              setForm({ ...form, role: event.target.value as Role })
            }
          >
            <option value="user">user — обычный пользователь</option>
            <option value="admin">admin — администратор</option>
          </select>
        </label>
        <button className="btn" type="submit" disabled={busy}>
          {busy ? "Создание…" : "Создать"}
        </button>
      </form>
      {created ? <p className="ok small">{created}</p> : null}
      {error ? <p className="error small">Ошибка: {error}</p> : null}
    </div>
  );
}

interface UsersTableProps {
  currentUserId: number;
  users: User[];
  onDelete: (user: User) => Promise<void>;
}

export function UsersTable({ currentUserId, users, onDelete }: UsersTableProps) {
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete(user: User) {
    if (!window.confirm(`Удалить пользователя ${user.email}?`)) {
      return;
    }
    setDeletingId(user.id);
    setError(null);
    try {
      await onDelete(user);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div>
      <h3>Пользователи</h3>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>id</th>
              <th>Email</th>
              <th>Имя</th>
              <th>Роль</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>{user.id}</td>
                <td>{user.email}</td>
                <td>{user.full_name}</td>
                <td>{roleLabel(user.role)}</td>
                <td>
                  {user.id === currentUserId ? (
                    <span className="muted small">это вы</span>
                  ) : (
                    <button
                      className="btn ghost small"
                      type="button"
                      disabled={deletingId === user.id}
                      onClick={() => void handleDelete(user)}
                    >
                      {deletingId === user.id ? "Удаление…" : "Удалить"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {error ? (
        <p className="error small">Ошибка при удалении: {error}</p>
      ) : null}
    </div>
  );
}
