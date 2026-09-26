import { useState } from "react";
import { api } from "./api";

const normalizeLine = (value) => {
  const raw = String(value || "").trim().toUpperCase();
  if (!raw) return "";
  return raw.startsWith("L-") ? raw : `L-${raw}`;
};

export default function LoginPage({ onLogin, onDemo, allowDemo, tabletLine, onTabletLineChange }) {
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [setupOpen, setSetupOpen] = useState(!tabletLine);
  const [lineDraft, setLineDraft] = useState(tabletLine || "");

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.login(login, password);
      const current = await api.authMe();
      if (!current) {
        throw new Error("Не удалось подтвердить учетную запись после входа");
      }
      onLogin(current);
    } catch (err) {
      setError(err.message || "Не удалось выполнить вход");
    } finally {
      setBusy(false);
    }
  };

  const saveTabletLine = () => {
    const normalized = normalizeLine(lineDraft);
    if (!normalized) {
      setError("Укажите линию планшета, например 14/1");
      return;
    }
    onTabletLineChange?.(normalized);
    setLineDraft(normalized);
    setSetupOpen(false);
    setError("");
  };

  return <div className="login-shell">
    <div className="login-brand">
      <div className="brand-mark login-mark">VG</div>
      <div>
        <b>VITAGROUP</b>
        <span>Production · OEE · Payroll</span>
      </div>
    </div>

    <form className="login-card operator-tablet-login" onSubmit={submit}>
      <div>
        <span className="login-eyebrow">Рабочее место оператора</span>
        <h1>{tabletLine ? `Линия ${tabletLine.replace(/^L-/, "")}` : "Настройте линию планшета"}</h1>
        <p>{tabletLine ? "Введите табельный номер и пароль. После входа откроются задания текущей смены только для этой линии." : "Линия задается на планшете один раз и сохраняется на этом устройстве."}</p>
      </div>

      {setupOpen ? <div className="tablet-line-setup">
        <label>
          <span>Линия планшета</span>
          <input
            className="form-control"
            value={lineDraft}
            onChange={e=>setLineDraft(e.target.value)}
            placeholder="Например, 14/1"
            autoFocus
          />
        </label>
        <button type="button" className="btn primary" onClick={saveTabletLine}>Сохранить линию</button>
        {tabletLine && <button type="button" className="btn ghost" onClick={()=>{setLineDraft(tabletLine);setSetupOpen(false);}}>Отмена</button>}
      </div> : <>
        <div className="tablet-line-badge">
          <span>Этот планшет</span>
          <b>{tabletLine}</b>
          <button type="button" onClick={()=>setSetupOpen(true)}>Изменить</button>
        </div>

        <label>
          <span>Табельный номер</span>
          <input
            className="form-control"
            type="text"
            inputMode="numeric"
            value={login}
            onChange={e => setLogin(e.target.value)}
            autoComplete="username"
            placeholder="Например, 00452"
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

        {allowDemo && <button type="button" className="btn ghost login-button" onClick={onDemo}>
          Открыть демонстрационный режим
        </button>}
      </>}

      {!setupOpen && !error && <small className="login-hint">
        После входа оператор увидит все задания текущей смены на линии {tabletLine}.
      </small>}
    </form>
  </div>;
}
