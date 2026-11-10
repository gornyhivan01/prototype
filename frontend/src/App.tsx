import { HashRouter, Link, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";

import { AuthProvider, useAuth } from "./auth";
import { AdminPage } from "./pages/AdminPage";
import { AuditPage } from "./pages/AuditPage";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { TasksPage } from "./pages/TasksPage";

export function App() {
  return (
    <AuthProvider>
      <HashRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route element={<Layout />}>
            <Route path="/" element={<TasksPage />} />
            <Route path="/audit" element={<AuditPage />} />
            <Route path="/admin" element={<AdminPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </HashRouter>
    </AuthProvider>
  );
}

function Layout() {
  const { user, loading, logout } = useAuth();
  const location = useLocation();

  if (loading) {
    return <div className="screen-center">Загрузка…</div>;
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">PROTO</span>
          <span className="brand-title">Prototype</span>
        </div>
        <nav className="nav">
          <Link className={location.pathname === "/" ? "nav-link active" : "nav-link"} to="/">
            Задачи
          </Link>
          <Link
            className={location.pathname === "/audit" ? "nav-link active" : "nav-link"}
            to="/audit"
          >
            {user.role === "ADMIN" ? "Аудит" : "Мои действия"}
          </Link>
          {user.role === "ADMIN" && (
            <Link
              className={location.pathname === "/admin" ? "nav-link active" : "nav-link"}
              to="/admin"
            >
              Пользователи
            </Link>
          )}
        </nav>
        <div className="userbox">
          <span className="user-name">{user.name}</span>
          <span className={user.role === "ADMIN" ? "badge role-admin" : "badge role-user"}>
            {user.role}
          </span>
          <button className="button ghost" onClick={logout} type="button">
            Выйти
          </button>
        </div>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
