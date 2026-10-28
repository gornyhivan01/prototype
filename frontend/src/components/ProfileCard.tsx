import type { User } from "../api";
import { roleLabel } from "../api";

export function ProfileCard({ user }: { user: User }) {
  const fields: Array<[string, string]> = [
    ["Email", user.email],
    ["Полное имя", user.full_name],
    ["Роль", roleLabel(user.role)],
    ["Создан", new Date(user.created_at).toLocaleString("ru-RU")],
  ];

  return (
    <section>
      <h2>Мой профиль</h2>
      <dl>
        {fields.map(([label, value]) => (
          <div className="dl-row" key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
