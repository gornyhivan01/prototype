import { Link } from "react-router-dom";

import { useAuth } from "../auth";

export function Landing() {
  const { token } = useAuth();

  return (
    <main className="card">
      <h1>Prototype</h1>
      <p className="muted">
        Учебный FastAPI-сервис: PostgreSQL, Alembic, SSO через Keycloak.
      </p>

      <a className="btn" href="/auth/sso/start">
        Войти через SSO
      </a>

      {token ? (
        <p className="muted small">
          Вы уже вошли в этой вкладке — <Link to="/dashboard">открыть дашборд</Link>.
        </p>
      ) : null}

      <p className="muted small">
        Откроется форма Keycloak — введите логин и пароль учётной записи реалма{" "}
        <code>prototype</code>. После входа откроется дашборд: обычному
        пользователю — профиль, администратору — управление пользователями.
      </p>

      <details className="muted small">
        <summary>Техническим путём</summary>
        <p>
          API и Swagger: <a href="/docs">/docs</a>. Парольный вход:{" "}
          <code>POST /auth/login</code> — работает параллельно с SSO.
        </p>
      </details>
    </main>
  );
}
