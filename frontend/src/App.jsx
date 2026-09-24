import ShiftLifecyclePage from "./ShiftLifecyclePage";
import TestShiftPage from "./TestShiftPage";
import NormAdminPage from "./NormAdminPage";
import ReasonAdminPage from "./ReasonAdminPage";
import LaunchReadiness from "./LaunchReadiness";
import ProblemCenter from "./ProblemCenter";
import ManagementDashboard from "./ManagementDashboard";
import ProductionManagerDashboard from "./ProductionManagerDashboard";
import ShiftMasterDashboard from "./ShiftMasterDashboard";
import ReconciliationControl from "./ReconciliationControl";
import RoleWorkspace from "./RoleWorkspace";
import LoginPage from "./LoginPage";
import UserAdminPage from "./UserAdminPage";
import PayrollPage from "./PayrollPage";
import OEEPage from "./OEEPage";
import ERPPlan from "./ERPPlan";
import { useEffect, useMemo, useState } from "react";
import { api } from "./api";

const menu = [
  { key: "dashboard", label: "Обзор", roles: ["OPERATOR","QC","WAREHOUSE","ACCOUNTANT_PRODUCTION","SHIFT_MASTER","PRODUCTION_MANAGER","ECONOMIST","MANAGEMENT","ADMIN"] },
  { key: "shift-master", label: "Кабинет мастера", roles: ["SHIFT_MASTER","PRODUCTION_MANAGER","MANAGEMENT","ADMIN"] },
  { key: "production-manager", label: "Руководитель производства", roles: ["PRODUCTION_MANAGER","MANAGEMENT","ADMIN"] },
  { key: "management", label: "Руководство", roles: ["MANAGEMENT","ADMIN"] },
  { key: "problems", label: "Центр проблем", roles: ["SHIFT_MASTER","PRODUCTION_MANAGER","ACCOUNTANT_PRODUCTION","ECONOMIST","MANAGEMENT","ADMIN"] },
  { key: "operator-workspace", label: "Мое задание", roles: ["OPERATOR","ADMIN"] },
  { key: "qc-workspace", label: "Контроль качества", roles: ["QC","ADMIN"] },
  { key: "warehouse-workspace", label: "Приемка продукции", roles: ["WAREHOUSE","ADMIN"] },
  { key: "accountant-workspace", label: "Учет выпуска", roles: ["ACCOUNTANT_PRODUCTION","ADMIN"] },
  { key: "production", label: "Производство", roles: ["OPERATOR","ACCOUNTANT_PRODUCTION","SHIFT_MASTER","PRODUCTION_MANAGER","ADMIN"] },
  { key: "erp-plan", label: "План ERP", roles: ["ACCOUNTANT_PRODUCTION","PRODUCTION_MANAGER","ECONOMIST","MANAGEMENT","ADMIN"] },
  { key: "oee-detail", label: "OEE детально", roles: ["SHIFT_MASTER","PRODUCTION_MANAGER","ECONOMIST","MANAGEMENT","ADMIN"] },
  { key: "downtime", label: "Простои", roles: ["OPERATOR","SHIFT_MASTER","PRODUCTION_MANAGER","MANAGEMENT","ADMIN"] },
  { key: "quality", label: "ГП и брак", roles: ["QC","SHIFT_MASTER","PRODUCTION_MANAGER","MANAGEMENT","ADMIN"] },
  { key: "reconciliation", label: "Сверка", roles: ["QC","WAREHOUSE","ACCOUNTANT_PRODUCTION","SHIFT_MASTER","PRODUCTION_MANAGER","ECONOMIST","MANAGEMENT","ADMIN"] },
  { key: "shift-control", label: "Контроль смены", roles: ["SHIFT_MASTER","PRODUCTION_MANAGER","ACCOUNTANT_PRODUCTION","ECONOMIST","MANAGEMENT","ADMIN"] },
  { key: "payroll", label: "Сдельная ЗП", roles: ["ECONOMIST","MANAGEMENT","ADMIN"] },
  { key: "integrations", label: "Интеграции", roles: ["ACCOUNTANT_PRODUCTION","PRODUCTION_MANAGER","ADMIN"] },
  { key: "users", label: "Пользователи", roles: ["ADMIN"] },
  { key: "launch-readiness", label: "Готовность к запуску", roles: ["PRODUCTION_MANAGER","MANAGEMENT","ADMIN"] },
  { key: "reasons", label: "Причины простоев и брака", roles: ["PRODUCTION_MANAGER","ADMIN"] },
  { key: "norms", label: "Нормативы скорости", roles: ["PRODUCTION_MANAGER","ADMIN"] },
  { key: "test-shift", label: "Тестовая смена", roles: ["PRODUCTION_MANAGER","ADMIN"] },
  { key: "shift-lifecycle", label: "Сквозной тест смены", roles: ["PRODUCTION_MANAGER","MANAGEMENT","ADMIN"] }
];

function defaultSectionForRoles(roles = []) {
  const priority = [
    ["ADMIN", "management"],
    ["MANAGEMENT", "management"],
    ["PRODUCTION_MANAGER", "production-manager"],
    ["SHIFT_MASTER", "shift-master"],
    ["ECONOMIST", "payroll"],
    ["ACCOUNTANT_PRODUCTION", "accountant-workspace"],
    ["WAREHOUSE", "warehouse-workspace"],
    ["QC", "qc-workspace"],
    ["OPERATOR", "operator-workspace"]
  ];
  return priority.find(([role]) => roles.includes(role))?.[1] || "dashboard";
}

const sourceNames = {
  downtime: "Простои",
  production_output: "Выпуск производства",
  qc_defects: "Брак ОТК",
  warehouse: "Кладовщик",
  accountant: "Учетчик",
  employees: "Сотрудники",
  equipment: "Оборудование",
  products: "Номенклатура",
  tariffs: "Тарифная сетка",
  production_norms: "Нормы выпуска"
};

const manualFieldConfig = {
  employee_id: { label: "Сотрудник", entityType: "EMPLOYEE", externalField: "personnel_number" },
  equipment_id: { label: "Оборудование", entityType: "EQUIPMENT", externalField: "equipment_code" },
  product_id: { label: "Номенклатура", entityType: "PRODUCT", externalField: "article_code" },
  production_order_id: { label: "Заказ ERP", entityType: "PRODUCTION_ORDER", externalField: "order_no" }
};

const formatNumber = (value) => new Intl.NumberFormat("ru-RU").format(value ?? 0);
const formatMoney = (value) => new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", maximumFractionDigits: 0 }).format(value ?? 0);

function Metric({ label, value, suffix = "%", note }) {
  const display = value === null || value === undefined ? "—" : `${value}${suffix}`;
  return <div className="metric card"><span>{label}</span><strong>{display}</strong>{note && <small>{note}</small>}</div>;
}

function Status({ state }) {
  const down = state === "DOWNTIME";
  return <span className={`status ${down ? "danger" : "success"}`}>{down ? "ПРОСТОЙ" : "РАБОТАЕТ"}</span>;
}

function IntegrationBadge({ status }) {
  const s = String(status || "").toUpperCase();
  const cls = s === "RESOLVED" || s === "COMPLETED" || s === "READY" ? "success" : s === "ERROR" || s === "FAILED" ? "danger" : "warning";
  return <span className={`status ${cls}`}>{status || "НЕ ЗАПУСКАЛОСЬ"}</span>;
}

function Dashboard({ data }) {
  const p = data.production;
  const completion = p.plan > 0 ? Math.min(100, Math.round((p.operator_output / p.plan) * 100)) : 0;
  const missingNormRuns = data.data_quality?.missing_norm_runs || 0;
  return <>
    {missingNormRuns > 0 && <div className="data-warning">
      <b>OEE пока неполный.</b> Для {missingNormRuns} производственных запусков не найден норматив скорости. Availability и Quality рассчитаны, Performance и итоговый OEE будут доступны после сопоставления нормы.
    </div>}
    <div className="metric-grid">
      <Metric label="OEE" value={data.kpi.oee} note="предварительно" />
      <Metric label="Availability" value={data.kpi.availability} />
      <Metric label="Performance" value={data.kpi.performance} />
      <Metric label="Quality" value={data.kpi.quality} />
    </div>
    <div className="two-col">
      <section className="card panel">
        <div className="panel-head"><h2>Выполнение плана</h2><b>{completion}%</b></div>
        <div className="progress"><i style={{ width: `${completion}%` }} /></div>
        <div className="stat-grid">
          <div><span>План</span><b>{formatNumber(p.plan)}</b></div>
          <div><span>Выпуск оператора</span><b>{formatNumber(p.operator_output)}</b></div>
          <div><span>ГП</span><b>{formatNumber(p.good_product)}</b></div>
          <div><span>Брак ОТК</span><b>{formatNumber(p.qc_defect)}</b></div>
          <div><span>Принято складом</span><b>{formatNumber(p.warehouse_received)}</b></div>
          <div><span>ERP</span><b>{formatNumber(p.erp_fact)}</b></div>
        </div>
      </section>
      <section className="card panel">
        <div className="panel-head"><h2>Контроль цепочки</h2><span className="status warning">ЕСТЬ ОТКЛОНЕНИЯ</span></div>
        <div className="flow">
          <div><b>{formatNumber(p.operator_output)}</b><span>Оператор</span></div><i>→</i>
          <div><b>{formatNumber(p.operator_output - p.qc_defect)}</b><span>После ОТК</span></div><i>→</i>
          <div><b>{formatNumber(p.warehouse_received)}</b><span>Склад</span></div><i>→</i>
          <div><b>{formatNumber(p.erp_fact)}</b><span>1С:ERP</span></div>
        </div>
      </section>
    </div>
    <section className="card panel">
      <div className="panel-head"><h2>Оборудование онлайн</h2><span>4 единицы</span></div>
      <div className="equipment-grid">
        {data.equipment.map(item => <article className="equipment" key={item.code}>
          <div className="equipment-head"><div><small>{item.code}</small><h3>{item.name}</h3></div><Status state={item.state} /></div>
          <p>{item.product}</p>
          <div className="equipment-kpi">
            <div><span>OEE</span><b>{item.oee}%</b></div>
            <div><span>Выпуск</span><b>{formatNumber(item.output)}</b></div>
            <div><span>Простой</span><b>{item.downtime_minutes} мин</b></div>
          </div>
          {item.downtime_reason && <div className="alert">Причина: {item.downtime_reason}</div>}
        </article>)}
      </div>
    </section>
  </>;
}

function Downtime({ rows }) {
  return <Table title="Простои оборудования" columns={["Оборудование","Начало","Окончание","Минут","Причина","Тип"]} rows={rows.map(r => [r.equipment,r.start,r.end || "идет сейчас",r.minutes,r.reason,r.planned ? "Плановый" : "Неплановый"])} />;
}

function Reconciliation({ rows }) {
  return <Table title="Сверка Производство → ОТК → Склад → ERP" columns={["Номенклатура","Оператор","После ОТК","Склад","ERP","Отклонение склад/ERP"]} rows={rows.map(r => [r.product,formatNumber(r.operator),formatNumber(r.qc_good),formatNumber(r.warehouse),formatNumber(r.erp),formatNumber(r.warehouse-r.erp)])} />;
}

function ManualMappingModal({ row, onClose, onSaved }) {
  const missing = row?.resolution_details?.missing || [];
  const availableFields = missing.filter(field => {
    const cfg = manualFieldConfig[field];
    return cfg && row[cfg.externalField];
  });

  const [fieldName, setFieldName] = useState(availableFields[0] || "");
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState([]);
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const cfg = manualFieldConfig[fieldName];

  const search = async () => {
    if (!cfg) return;
    setBusy(true);
    setSelected(null);
    const result = await api.candidates(cfg.entityType, query || row[cfg.externalField] || "");
    setCandidates(result.rows || []);
    setBusy(false);
  };

  useEffect(() => {
    setQuery(cfg ? String(row[cfg.externalField] || "") : "");
    setCandidates([]);
    setSelected(null);
    setMessage("");
  }, [fieldName]);

  useEffect(() => {
    if (cfg) search();
  }, [fieldName]);

  const save = async () => {
    if (!cfg || !selected) return;
    setBusy(true);
    const result = await api.manualMap({
      staging_event_id: row.id,
      field_name: fieldName,
      entity_id: selected.id,
      canonical_label: selected.label
    });
    setMessage(result?.status === "ok" ? "Сопоставление сохранено. Строка повторно проверена." : "Сопоставление сохранено в демо-режиме.");
    await onSaved();
    setBusy(false);
  };

  return <div className="modal-backdrop" onMouseDown={onClose}>
    <div className="modal-card" onMouseDown={e => e.stopPropagation()}>
      <div className="modal-head">
        <div><small>{sourceNames[row.event_type] || row.event_type}</small><h2>Ручное сопоставление</h2></div>
        <button className="modal-close" onClick={onClose}>×</button>
      </div>

      <div className="event-summary">
        <div><span>Дата / смена</span><b>{row.business_date || "—"} · {row.shift_code || "—"}</b></div>
        <div><span>Таб. №</span><b>{row.personnel_number || "—"}</b></div>
        <div><span>Линия</span><b>{row.equipment_code || "—"}</b></div>
        <div><span>Заказ</span><b>{row.order_no || "—"}</b></div>
        <div><span>Артикул / код</span><b>{row.article_code || "—"}</b></div>
        <div><span>Талон</span><b>{row.ticket_no || "—"}</b></div>
      </div>

      {availableFields.length ? <>
        <label className="form-label">Что сопоставляем</label>
        <select className="form-control" value={fieldName} onChange={e => setFieldName(e.target.value)}>
          {availableFields.map(field => <option key={field} value={field}>{manualFieldConfig[field].label}</option>)}
        </select>

        <div className="external-code-box">
          <span>Внешний код Coverse</span>
          <b>{cfg ? row[cfg.externalField] : "—"}</b>
        </div>

        <label className="form-label">Поиск в справочнике</label>
        <div className="search-row">
          <input className="form-control" value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => e.key === "Enter" && search()} placeholder="Введите код или наименование" />
          <button className="btn secondary" onClick={search} disabled={busy}>Найти</button>
        </div>

        <div className="candidate-list">
          {candidates.length === 0 && !busy && <div className="empty-state">Кандидаты не найдены.</div>}
          {candidates.map(item => <button key={item.id} className={`candidate ${selected?.id === item.id ? "selected" : ""}`} onClick={() => setSelected(item)}>
            <div><b>{item.code}</b><span>{item.label}</span></div>
            <small>{item.secondary || ""}</small>
          </button>)}
        </div>

        {message && <div className="notice">{message}</div>}

        <div className="modal-actions">
          <button className="btn ghost" onClick={onClose}>Закрыть</button>
          <button className="btn primary" disabled={!selected || busy} onClick={save}>Сохранить соответствие</button>
        </div>
      </> : <div className="mapping-blocked">
        <b>В этой строке нет поля, которое можно сопоставить вручную безопасно.</b>
        <p>Остались системные связи: смена или производственный запуск. Они должны определяться из даты/смены и плана ERP, а не назначаться вручную.</p>
        <div className="modal-actions"><button className="btn ghost" onClick={onClose}>Закрыть</button></div>
      </div>}
    </div>
  </div>;
}

function Integrations() {
  const [dashboard, setDashboard] = useState(null);
  const [unresolved, setUnresolved] = useState([]);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [mappingRow, setMappingRow] = useState(null);
  const [masterPreview, setMasterPreview] = useState({});

  const refresh = async () => {
    const [d, u] = await Promise.all([api.integrationDashboard(), api.unresolved()]);
    setDashboard(d);
    setUnresolved(u.rows || []);
  };

  useEffect(() => { refresh(); }, []);

  const run = async (key, action) => {
    setBusy(key);
    setNotice("");
    const result = await action();
    setNotice(result?.message || `Операция «${key}» выполнена`);
    await refresh();
    setBusy("");
  };

  const previewMaster = async (key) => {
    setBusy(`preview:${key}`);
    setNotice("");
    try {
      const result = await api.previewMasterSource(key);
      setMasterPreview(current => ({ ...current, [key]: result }));
    } catch (error) {
      setNotice(error.message || "Не удалось проверить источник");
    } finally {
      setBusy("");
    }
  };

  if (!dashboard) return <div className="card panel">Загрузка состояния интеграций…</div>;

  const events = Object.entries(dashboard.event_sources || {});
  const masters = Object.entries(dashboard.master_sources || {});

  return <>
    <div className="integration-toolbar card">
      <div><h2>Контур интеграций</h2><p>Coverse → staging → сопоставление → рабочие факты</p></div>
      <div className="action-row">
        <button className="btn secondary" disabled={!!busy} onClick={() => run("Справочники", api.syncMasterData)}>Синхронизировать справочники</button>
        <button className="btn secondary" disabled={!!busy} onClick={() => run("Сопоставление", api.resolveReferences)}>Разрешить связи</button>
        <button className="btn primary" disabled={!!busy} onClick={() => run("Перенос", api.promoteResolved)}>Перенести RESOLVED</button>
      </div>
    </div>

    {notice && <div className="notice">{notice}</div>}

    <div className="integration-kpis">
      <div className="card mini-kpi"><span>Неразрешенных событий</span><b>{formatNumber(dashboard.totals?.unresolved)}</b></div>
      <div className="card mini-kpi"><span>Проблем сопоставления</span><b>{formatNumber(dashboard.totals?.open_resolution_issues)}</b></div>
      <div className="card mini-kpi"><span>Проблем справочников</span><b>{formatNumber(dashboard.totals?.open_master_issues)}</b></div>
    </div>

    <section className="card panel">
      <div className="panel-head">
        <div>
          <h2>Пилотная загрузка справочников</h2>
          <span>Фактическое наполнение PostgreSQL после синхронизации</span>
        </div>
        <IntegrationBadge status={dashboard.pilot_master_readiness?.ready ? "READY" : "BLOCKED"} />
      </div>
      <div className="pilot-master-grid">
        {Object.entries(dashboard.pilot_master_readiness?.sources || {}).map(([key,item]) => {
          const preview = masterPreview[key];
          return <article className="pilot-master-card" key={key}>
            <div className="pilot-master-head">
              <b>{sourceNames[key] || key}</b>
              <IntegrationBadge status={preview?.status || item.status} />
            </div>
            <strong>{formatNumber(item.count)}</strong>
            <p>{preview?.message || item.message}</p>
            {preview && <div className="pilot-preview-stats">
              <span>Прочитано <b>{formatNumber(preview.rows_read)}</b></span>
              <span>Готово <b>{formatNumber(preview.rows_ready)}</b></span>
              <span>Пропущено <b>{formatNumber(preview.rows_skipped)}</b></span>
              <span>Ошибок <b>{formatNumber(preview.rows_error)}</b></span>
            </div>}
            <div className="pilot-master-actions">
              <button className="btn ghost" disabled={!!busy} onClick={() => previewMaster(key)}>
                Проверить источник
              </button>
              <button className="btn secondary" disabled={!!busy || preview?.status === "BLOCKED"} onClick={() => run(sourceNames[key] || key, () => api.syncMasterSource(key))}>
                Синхронизировать
              </button>
            </div>
          </article>;
        })}
      </div>
      <div className="admin-note">
        Нормы выпуска могут быть заполнены вручную в разделе «Нормативы скорости», если исходный справочник Coverse остается некорректным.
      </div>
    </section>

    <section className="card panel">
      <div className="panel-head"><h2>Справочники</h2><span>{masters.length} источников</span></div>
      <div className="source-list">
        {masters.map(([key, item]) => <div className="source-row" key={key}>
          <div className="source-main"><b>{sourceNames[key] || key}</b><span>{item.message || `Прочитано: ${formatNumber(item.rows_read || 0)} · применено: ${formatNumber(item.rows_applied || 0)}`}</span></div>
          <IntegrationBadge status={item.status} />
          <button className="btn ghost" disabled={!!busy} onClick={() => run(sourceNames[key] || key, () => api.syncMasterSource(key))}>Повторить</button>
        </div>)}
      </div>
    </section>

    <section className="card panel">
      <div className="panel-head"><h2>Оперативные формы Coverse</h2><span>{events.length} источников</span></div>
      <div className="source-list">
        {events.map(([key, item]) => <div className="source-row event-source" key={key}>
          <div className="source-main"><b>{sourceNames[key] || key}</b><span>Всего: {formatNumber(item.total)} · RESOLVED: {formatNumber(item.resolved)} · PARTIAL: {formatNumber(item.partial)} · ошибок: {formatNumber(item.errors)}</span></div>
          <div className="event-progress"><i style={{width: `${item.total ? Math.round((item.resolved / item.total) * 100) : 0}%`}} /></div>
          <button className="btn ghost" disabled={!!busy} onClick={() => run(sourceNames[key] || key, () => api.syncCoverseSource(key))}>Синхронизировать</button>
        </div>)}
      </div>
    </section>

    <section className="card panel">
      <div className="panel-head"><h2>Требуют сопоставления</h2><span>{unresolved.length} строк</span></div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Источник</th><th>Дата</th><th>Смена</th><th>Таб. №</th><th>Линия</th><th>Заказ</th><th>Артикул/код</th><th>Талон</th><th>Статус</th><th></th></tr></thead>
          <tbody>{unresolved.map((r, i) => <tr key={r.id || i}>
            <td>{sourceNames[r.event_type] || r.event_type}</td>
            <td>{r.business_date || "—"}</td>
            <td>{r.shift_code || "—"}</td>
            <td>{r.personnel_number || "—"}</td>
            <td>{r.equipment_code || "—"}</td>
            <td>{r.order_no || "—"}</td>
            <td>{r.article_code || "—"}</td>
            <td>{r.ticket_no || "—"}</td>
            <td><IntegrationBadge status={r.resolution_status} /></td>
            <td><button className="btn secondary" onClick={() => setMappingRow(r)}>Сопоставить</button></td>
          </tr>)}</tbody>
        </table>
      </div>
      <div className="admin-note">После сохранения соответствия внешний код запоминается. При следующих загрузках строки с тем же кодом будут разрешаться автоматически.</div>
    </section>

    {mappingRow && <ManualMappingModal row={mappingRow} onClose={() => setMappingRow(null)} onSaved={refresh} />}
  </>;
}

function Table({ title, columns, rows }) {
  return <section className="card panel table-card"><div className="panel-head"><h2>{title}</h2><span>{rows.length} строк</span></div><div className="table-wrap"><table><thead><tr>{columns.map(c => <th key={c}>{c}</th>)}</tr></thead><tbody>{rows.map((row,i) => <tr key={i}>{row.map((cell,j) => <td key={j}>{cell}</td>)}</tr>)}</tbody></table></div></section>;
}

function PasswordChangeScreen({ user, onChanged, onLogout }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState("");

  const save = async () => {
    if (newPassword !== repeat) {
      setError("Новые пароли не совпадают");
      return;
    }
    try {
      await api.changePassword(currentPassword, newPassword);
      onChanged({ ...user, must_change_password: false });
    } catch (err) {
      setError(err.message || "Не удалось изменить пароль");
    }
  };

  return <div className="login-shell">
    <div className="login-card">
      <span className="login-eyebrow">Безопасность</span>
      <h1>Смените временный пароль</h1>
      <p>Перед началом работы задайте собственный пароль длиной не менее 12 символов.</p>
      <label><span>Текущий пароль</span><input className="form-control" type="password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} /></label>
      <label><span>Новый пароль</span><input className="form-control" type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} /></label>
      <label><span>Повторите новый пароль</span><input className="form-control" type="password" value={repeat} onChange={e => setRepeat(e.target.value)} /></label>
      {error && <div className="login-error">{error}</div>}
      <button className="btn primary login-button" disabled={newPassword.length < 12 || newPassword !== repeat} onClick={save}>Сохранить новый пароль</button>
      <button className="btn ghost login-button" onClick={onLogout}>Выйти</button>
    </div>
  </div>;
}

export default function App() {
  const [user, setUser] = useState(undefined);
  const [section, setSection] = useState("dashboard");
  const [data, setData] = useState(null);
  const [downtime, setDowntime] = useState([]);
  const [recon, setRecon] = useState([]);
  const [shift, setShift] = useState("DAY");
  const [demoMode, setDemoMode] = useState(false);
  const [problemCount, setProblemCount] = useState(0);

  const allowDemo = typeof window !== "undefined" && window.location.hostname !== "corpvitagroup.ru";

  useEffect(() => {
    api.authMe().then(current => {
      setUser(current);
      if (current) setSection(defaultSectionForRoles(current.roles || []));
    });
    const expired = () => {
      setUser(null);
      setDemoMode(false);
    };
    window.addEventListener("vitagroup-auth-expired", expired);
    return () => window.removeEventListener("vitagroup-auth-expired", expired);
  }, []);

  const roles = user?.roles || [];
  const visibleMenu = useMemo(
    () => menu.filter(item => item.roles.some(role => roles.includes(role))),
    [roles.join("|")]
  );

  useEffect(() => {
    if (user && visibleMenu.length && !visibleMenu.some(item => item.key === section)) {
      setSection(visibleMenu[0].key);
    }
  }, [user, visibleMenu, section]);

  useEffect(() => {
    if (!user) return;
    const businessDate = data?.shift?.business_date || null;
    Promise.all([
      api.summary(businessDate, shift),
      api.downtime(businessDate, shift),
      api.reconciliation(businessDate, shift)
    ]).then(([a,b,c]) => {
      setData(a);
      setDowntime(b);
      setRecon(c);
    });
  }, [shift, user?.id]);

  useEffect(() => {
    if (!user || !data?.shift?.business_date) return;
    const allowed = roles.some(role => ["SHIFT_MASTER","PRODUCTION_MANAGER","ACCOUNTANT_PRODUCTION","ECONOMIST","MANAGEMENT","ADMIN"].includes(role));
    if (!allowed) {
      setProblemCount(0);
      return;
    }
    api.problemCenter(data.shift.business_date, shift).then(result => {
      setProblemCount(result?.summary?.critical || 0);
    });
  }, [user?.id, data?.shift?.business_date, shift, roles.join("|")]);

  const logout = () => {
    api.setDemoMode(false);
    api.logout();
    setUser(null);
    setDemoMode(false);
    setData(null);
  };

  if (user === undefined) return <div className="loading">Проверка сессии…</div>;

  if (!user) {
    return <LoginPage
      allowDemo={allowDemo}
      onLogin={current => {
        api.setDemoMode(false);
        setUser(current);
        setSection(defaultSectionForRoles(current.roles || []));
        setDemoMode(false);
      }}
      onDemo={() => {
        const demoUser = {
          id: "demo",
          email: "demo@vitagroup.local",
          full_name: "Демонстрационный пользователь",
          roles: ["ADMIN"],
          must_change_password: false
        };
        api.setDemoMode(true);
        setUser(demoUser);
        setSection(defaultSectionForRoles(demoUser.roles));
        setDemoMode(true);
      }}
    />;
  }

  if (user.must_change_password && !demoMode) {
    return <PasswordChangeScreen user={user} onChanged={setUser} onLogout={logout} />;
  }

  if (!data) return <div className="loading">Загрузка VITAGROUP OEE…</div>;

  const title = visibleMenu.find(item => item.key === section)?.label ?? "Обзор";
  const canEditPayroll = roles.includes("ECONOMIST") || roles.includes("ADMIN");
  const canEditReconciliation = roles.includes("SHIFT_MASTER") || roles.includes("PRODUCTION_MANAGER") || roles.includes("ACCOUNTANT_PRODUCTION") || roles.includes("ADMIN");
  const canCloseShift = roles.includes("SHIFT_MASTER") || roles.includes("PRODUCTION_MANAGER") || roles.includes("ADMIN");
  const canVerifyShift = roles.includes("PRODUCTION_MANAGER") || roles.includes("ADMIN");

  return <div className="app">
    <aside>
      <div className="brand"><div className="brand-mark">VG</div><div><b>VITAGROUP</b><span>Production & OEE</span></div></div>
      <nav>{visibleMenu.map(item => <button key={item.key} className={section===item.key ? "active" : ""} onClick={() => setSection(item.key)}>
        <span>{item.label}</span>
        {item.key === "problems" && problemCount > 0 && <b className="nav-badge">{problemCount}</b>}
      </button>)}</nav>
      <div className="side-user">
        <b>{user.full_name || user.email}</b>
        <span>{demoMode ? "Демонстрационный режим" : roles.join(" · ")}</span>
        <button onClick={logout}>Выйти</button>
      </div>
    </aside>
    <main>
      <header>
        <div><p>ООО «ВИТА ГРУПП»</p><h1>{title}</h1></div>
        <div className="controls">
          {section !== "integrations" && section !== "erp-plan" && section !== "users" && section !== "launch-readiness" && section !== "reasons" && section !== "norms" && section !== "test-shift" && section !== "shift-lifecycle" && <div className="shift-switch">
            <button className={shift==="DAY" ? "active" : ""} onClick={() => setShift("DAY")}>ДЕНЬ</button>
            <button className={shift==="NIGHT" ? "active" : ""} onClick={() => setShift("NIGHT")}>НОЧЬ</button>
          </div>}
          <div className="date-box"><b>{data?.shift?.business_date || "—"}</b><span>{section === "integrations" ? "Администрирование" : section === "users" ? "Управление доступом" : section === "launch-readiness" ? "Контроль подготовки" : section === "erp-plan" ? "План 1С / ERP" : data?.shift?.time || (shift==="DAY" ? "09:00–21:00" : "21:00–09:00")}</span></div>
        </div>
      </header>
      <div className="content">
        {section === "dashboard" && <Dashboard data={data} />}
        {section === "shift-master" && <ShiftMasterDashboard businessDate={data?.shift?.business_date} shiftCode={shift} canClose={canCloseShift} onOpenControl={() => setSection("shift-control")} />}
        {section === "production-manager" && <ProductionManagerDashboard
          businessDate={data?.shift?.business_date}
          canVerify={canVerifyShift}
          onOpenMaster={(shiftCode)=>{setShift(shiftCode);setSection("shift-master");}}
          onOpenControl={(shiftCode)=>{setShift(shiftCode);setSection("shift-control");}}
        />}
        {section === "management" && <ManagementDashboard
          businessDate={data?.shift?.business_date}
          onOpenProductionManager={()=>setSection("production-manager")}
          onOpenControl={()=>setSection("shift-control")}
        />}
        {section === "problems" && <ProblemCenter
          businessDate={data?.shift?.business_date}
          shiftCode={shift}
          onNavigate={(item)=>{
            if (item.shift_code) setShift(item.shift_code);
            setSection(item.target_section || "problems");
          }}
        />}
        {section === "operator-workspace" && <RoleWorkspace kind="operator" businessDate={data?.shift?.business_date} shiftCode={shift} />}
        {section === "qc-workspace" && <RoleWorkspace kind="qc" businessDate={data?.shift?.business_date} shiftCode={shift} />}
        {section === "warehouse-workspace" && <RoleWorkspace kind="warehouse" businessDate={data?.shift?.business_date} shiftCode={shift} />}
        {section === "accountant-workspace" && <RoleWorkspace kind="accountant" businessDate={data?.shift?.business_date} shiftCode={shift} />}
        {section === "production" && <Dashboard data={data} />}
        {section === "erp-plan" && <ERPPlan />}
        {section === "oee-detail" && <OEEPage businessDate={data?.shift?.business_date} shiftCode={shift} />}
        {section === "downtime" && <Downtime rows={downtime} />}
        {section === "quality" && <Reconciliation rows={recon} />}
        {section === "reconciliation" && <Reconciliation rows={recon} />}
        {section === "shift-control" && <ReconciliationControl businessDate={data?.shift?.business_date} shiftCode={shift} canEdit={canEditReconciliation} />}
        {section === "payroll" && <PayrollPage readOnly={!canEditPayroll} />}
        {section === "integrations" && <Integrations />}
        {section === "users" && <UserAdminPage />}
        {section === "launch-readiness" && <LaunchReadiness onNavigate={(target)=>setSection(target === "launch-readiness" ? "reasons" : (target || "launch-readiness"))} />}
        {section === "reasons" && <ReasonAdminPage />}
        {section === "norms" && <NormAdminPage />}
        {section === "test-shift" && <TestShiftPage
          onOpenERP={()=>setSection("erp-plan")}
          onOpenNorms={()=>setSection("norms")}
          onOpenMaster={(shiftCode)=>{setShift(shiftCode);setSection("shift-master");}}
        />}
        {section === "shift-lifecycle" && <ShiftLifecyclePage
          onNavigate={(target,shiftCode)=>{
            if (shiftCode) setShift(shiftCode);
            setSection(target || "shift-lifecycle");
          }}
        />}
      </div>
    </main>
  </div>;
}
