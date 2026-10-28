/* Дашборд Prototype: токен во фрагменте URL (#access_token=…), хранение в
 * sessionStorage, вызовы API того же порта. Роль admin -> панель управления.
 */

const TOKEN_KEY = "prototype_access_token";
const API = "";

const $ = (id) => document.getElementById(id);
const roleLabel = (role) => (role === "admin" ? "Администратор" : "Пользователь");

function status(message, kind) {
  const el = $("status");
  el.textContent = message;
  el.style.color = kind === "error" ? "var(--danger)" : "var(--muted)";
}

function authHeaders() {
  return { Authorization: "Bearer " + sessionStorage.getItem(TOKEN_KEY) };
}

async function api(path, options = {}) {
  const response = await fetch(API + path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}), ...authHeaders() },
  });
  if (response.status === 401) throw new Error("unauthorized");
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || ("HTTP " + response.status));
  }
  return response.json();
}

// --- Первичная загрузка ---
window.addEventListener("DOMContentLoaded", async () => {
  // Токен пришёл из callback во фрагменте URL
  const hash = new URLSearchParams(window.location.hash.slice(1));
  const token = hash.get("access_token");
  if (token) {
    sessionStorage.setItem(TOKEN_KEY, token);
    history.replaceState(null, "", "/dashboard"); // не оставляем токен в адресной строке
  }

  if (!sessionStorage.getItem(TOKEN_KEY)) {
    status("Вы не вошли. Вернитесь на главную и нажмите «Войти через SSO».", "error");
    $("logout").hidden = true;
    return;
  }

  $("logout").onclick = () => {
    sessionStorage.removeItem(TOKEN_KEY);
    window.location.href = "/";
  };

  try {
    const me = await api("/users/me");
    renderProfile(me);
    if (me.role === "admin") {
      $("admin-panel").hidden = false;
      await refreshUsers();
      bindCreateForm();
    }
    status(`Добро пожаловать, ${me.full_name}!`, "ok");
  } catch (error) {
    if (error.message === "unauthorized") {
      sessionStorage.removeItem(TOKEN_KEY);
      status("Сессия истекла. Попробуйте войти ещё раз.");
      const link = document.createElement("a");
      link.href = "/auth/sso/start";
      link.textContent = " Войти через SSO";
      $("status").appendChild(link);
    } else {
      status("Ошибка: " + error.message);
    }
  }
});

// --- Профиль (все роли) ---
function renderProfile(user) {
  $("profile").hidden = false;
  $("profile-fields").innerHTML = [
    ["Email", user.email],
    ["Полное имя", user.full_name],
    ["Роль", roleLabel(user.role)],
    ["Создан", new Date(user.created_at).toLocaleString("ru-RU")],
  ]
    .map(([k, v]) => `<dt>${k}</dt><dd>${escapeHtml(v)}</dd>`)
    .join("");
}

// --- Панель администратора ---
async function refreshUsers() {
  const users = await api("/users");
  $("users-list").innerHTML = users
    .map(
      (u) =>
        `<tr><td>${u.id}</td><td>${escapeHtml(u.email)}</td>` +
        `<td>${escapeHtml(u.full_name)}</td><td>${roleLabel(u.role)}</td>` +
        `<td><button class="btn ghost small del-btn" data-id="${u.id}" ` +
        `data-email="${escapeHtml(u.email)}">Удалить</button></td></tr>`
    )
    .join("");

  for (const button of document.querySelectorAll(".del-btn")) {
    button.onclick = async () => {
      if (!confirm(`Удалить пользователя ${button.dataset.email}?`)) {
        return;
      }
      try {
        await api(`/users/${button.dataset.id}`, { method: "DELETE" });
        await refreshUsers();
      } catch (error) {
        status("Ошибка при удалении: " + error.message, "error");
      }
    };
  }
}

function bindCreateForm() {
  $("create-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    const data = Object.fromEntries(new FormData(form).entries());
    $("create-msg").textContent = "Создание…";
    try {
      const created = await api("/users", { method: "POST", body: JSON.stringify(data) });
      $("create-msg").textContent = `Создан ${created.email} (${roleLabel(created.role)}).`;
      form.reset();
      await refreshUsers();
    } catch (error) {
      $("create-msg").textContent = "Ошибка: " + error.message;
    }
  });
}

function escapeHtml(raw) {
  return String(raw).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
