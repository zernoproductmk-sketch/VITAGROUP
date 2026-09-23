import { useState } from "react";
import { api } from "./api";

export default function LoginPage({ onLogin, onDemo, allowDemo }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api.login(email, password);
      onLogin(result.user);
    } catch (err) {
      setError(err.message || "Не удалось выполнить вход");
    } finally {
      setBusy(false);
    }
  };

  return <div className="login-shell">
    <div className="login-brand">
      <div className="brand-mark login-mark">VG</div>
      <div>
        <b>VITAGROUP</b>
        <span>Production · OEE · Payroll</span>
      </div>
    </div>

    <form className="login-card" onSubmit={submit}>
      <div>
        <span className="login-eyebrow">Личный кабинет</span>
        <h1>Вход в систему</h1>
        <p>Производство, OEE, склад, ОТК и сдельная заработная плата.</p>
      </div>

      <label>
        <span>Email</span>
        <input
          className="form-control"
          type="email"
          value={email}
          onChange={e => setEmail(e.target.value)}
          autoComplete="username"
          required
        />
      </label>

      <label>
        <span>Пароль</span>
        <input
          className="form-control"
          type="password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          autoComplete="current-password"
          required
        />
      </label>

      {error && <div className="login-error">{error}</div>}

      <button className="btn primary login-button" disabled={busy}>
        {busy ? "Вход…" : "Войти"}
      </button>

      {allowDemo && <button
        type="button"
        className="btn ghost login-button"
        onClick={onDemo}
      >
        Открыть демонстрационный режим
      </button>}

      <small className="login-hint">
        Доступ к разделам определяется ролью пользователя.
      </small>
    </form>
  </div>;
}
