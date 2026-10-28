import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api, ApiError, errorMessage, type User } from "../api";
import { useAuth } from "../auth";
import { CreateUserForm, UsersTable } from "../components/AdminPanel";
import { ProfileCard } from "../components/ProfileCard";

export function Dashboard() {
  const { token, signOut } = useAuth();
  const [me, setMe] = useState<User | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!token) {
      setMe(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get<User>("/users/me")
      .then((user) => {
        if (!cancelled) {
          setMe(user);
        }
      })
      .catch((err: unknown) => {
        if (cancelled) {
          return;
        }
        if (err instanceof ApiError && err.status === 401) {
          signOut();
          setError("Сессия истекла. Войдите ещё раз.");
        } else {
          setError(errorMessage(err));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token, signOut]);

  const loadUsers = useCallback(async () => {
    const list = await api.get<User[]>("/users");
    setUsers(list);
  }, []);

  useEffect(() => {
    if (me?.role === "admin") {
      void loadUsers().catch((err: unknown) => setError(errorMessage(err)));
    }
  }, [me, loadUsers]);

  function handleLogout() {
    // Чистим локальный токен и завершаем SSO-сессию в Keycloak (single logout).
    signOut();
    window.location.href = "/auth/sso/logout";
  }

  if (!token) {
    return (
      <main className="card">
        <h1>Дашборд</h1>
        <p className="muted">
          Вы не вошли. <Link to="/">Вернитесь на главную</Link> и нажмите
          «Войти через SSO».
        </p>
      </main>
    );
  }

  return (
    <main className="card">
      <div className="topline">
        <h1>Дашборд</h1>
        <button className="btn ghost" type="button" onClick={handleLogout}>
          Выйти
        </button>
      </div>

      {loading ? <p className="muted">Загрузка…</p> : null}

      {error ? (
        <p className="error">
          {error}{" "}
          {!me ? <a href="/auth/sso/start">Войти через SSO</a> : null}
        </p>
      ) : null}

      {me ? (
        <>
          <p className="muted">Добро пожаловать, {me.full_name}!</p>
          <ProfileCard user={me} />

          {me.role === "admin" ? (
            <section>
              <h2>Управление пользователями</h2>
              <CreateUserForm onCreated={() => loadUsers()} />
              <UsersTable
                currentUserId={me.id}
                users={users}
                onDelete={async (user) => {
                  await api.delete(`/users/${user.id}`);
                  await loadUsers();
                }}
              />
            </section>
          ) : null}
        </>
      ) : null}
    </main>
  );
}
