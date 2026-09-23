import { useEffect, useState } from "react";
import { api } from "./api";

export default function UserAdminPage() {
  const [users, setUsers] = useState([]);
  const [meta, setMeta] = useState({ roles: [], employees: [] });
  const [form, setForm] = useState({
    email: "",
    password: "",
    employee_id: "",
    roles: []
  });
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    const [u, m] = await Promise.all([api.adminUsers(), api.adminMeta()]);
    setUsers(u.rows || []);
    setMeta(m);
  };

  useEffect(() => { refresh(); }, []);

  const toggleFormRole = (code) => {
    setForm(current => ({
      ...current,
      roles: current.roles.includes(code)
        ? current.roles.filter(item => item !== code)
        : [...current.roles, code]
    }));
  };

  const createUser = async () => {
    setBusy(true);
    setNotice("");
    try {
      await api.adminCreateUser({
        email: form.email,
        password: form.password,
        employee_id: form.employee_id || null,
        roles: form.roles
      });
      setForm({ email: "", password: "", employee_id: "", roles: [] });
      setNotice("Пользователь создан. При первом входе потребуется сменить пароль.");
      await refresh();
    } catch (error) {
      setNotice(error.message || "Не удалось создать пользователя");
    } finally {
      setBusy(false);
    }
  };

  const updateRoles = async (user, code) => {
    const next = user.roles.includes(code)
      ? user.roles.filter(item => item !== code)
      : [...user.roles, code];
    await api.adminSetRoles(user.id, next);
    await refresh();
  };

  const toggleActive = async (user) => {
    await api.adminSetActive(user.id, !user.is_active);
    await refresh();
  };

  const resetPassword = async (user) => {
    const value = window.prompt(
      `Введите временный пароль для ${user.email}. Минимум 12 символов.`
    );
    if (!value) return;
    try {
      await api.adminResetPassword(user.id, value);
      setNotice("Временный пароль установлен. При следующем входе пользователь сменит его.");
      await refresh();
    } catch (error) {
      setNotice(error.message || "Не удалось сбросить пароль");
    }
  };

  return <>
    <section className="card panel">
      <div className="panel-head">
        <div><h2>Новый пользователь</h2><span>Учетные записи и роли</span></div>
      </div>

      <div className="user-create-grid">
        <label><span>Email</span><input className="form-control" value={form.email} onChange={e => setForm({...form,email:e.target.value})} /></label>
        <label><span>Временный пароль</span><input className="form-control" type="password" value={form.password} onChange={e => setForm({...form,password:e.target.value})} /></label>
        <label><span>Сотрудник</span>
          <select className="form-control" value={form.employee_id} onChange={e => setForm({...form,employee_id:e.target.value})}>
            <option value="">Без привязки</option>
            {meta.employees.map(employee => <option key={employee.id} value={employee.id} disabled={Boolean(employee.user_id)}>
              {employee.full_name} · {employee.personnel_number}
            </option>)}
          </select>
        </label>
      </div>

      <div className="role-picker">
        {meta.roles.map(role => <label key={role.code}>
          <input type="checkbox" checked={form.roles.includes(role.code)} onChange={() => toggleFormRole(role.code)} />
          <span><b>{role.name}</b><small>{role.code}</small></span>
        </label>)}
      </div>

      <div className="action-row user-create-actions">
        <button className="btn primary" disabled={busy || !form.email || form.password.length < 12 || form.roles.length === 0} onClick={createUser}>Создать пользователя</button>
      </div>

      {notice && <div className="notice">{notice}</div>}
    </section>

    <section className="card panel">
      <div className="panel-head"><h2>Пользователи</h2><span>{users.length} учетных записей</span></div>
      <div className="user-admin-list">
        {users.map(user => <article className="user-admin-row" key={user.id}>
          <div className="user-admin-main">
            <b>{user.full_name || user.email}</b>
            <span>{user.email}</span>
            <small>{user.position_name || "Без должности"}{user.personnel_number ? ` · таб. № ${user.personnel_number}` : ""}</small>
          </div>
          <div className="user-role-chips">
            {meta.roles.map(role => <button
              key={role.code}
              className={`role-chip ${user.roles.includes(role.code) ? "selected" : ""}`}
              onClick={() => updateRoles(user, role.code)}
            >{role.name}</button>)}
          </div>
          <div className="user-admin-actions">
            <span className={`status ${user.is_active ? "success" : "danger"}`}>{user.is_active ? "АКТИВЕН" : "ОТКЛЮЧЕН"}</span>
            <button className="btn ghost" onClick={() => resetPassword(user)}>Сбросить пароль</button>
            <button className="btn secondary" onClick={() => toggleActive(user)}>{user.is_active ? "Отключить" : "Включить"}</button>
          </div>
        </article>)}
      </div>
    </section>
  </>;
}
