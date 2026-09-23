import { useEffect, useMemo, useState } from "react";
import { api } from "./api";

const menu = [
  ["dashboard", "Обзор"],
  ["production", "Производство"],
  ["downtime", "Простои"],
  ["quality", "ГП и брак"],
  ["reconciliation", "Сверка"],
  ["payroll", "Сдельная ЗП"],
  ["integrations", "Интеграции"]
];

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
  return <div className="metric card"><span>{label}</span><strong>{value}{suffix}</strong>{note && <small>{note}</small>}</div>;
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
  const completion = Math.min(100, Math.round((p.operator_output / p.plan) * 100));
  return <>
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

function Payroll({ rows }) {
  return <Table title="Сдельная заработная плата — предварительный расчет" columns={["Сотрудник","Смен","Подтвержденная выработка","Начислено"]} rows={rows.map(r => [r.employee,r.shifts,formatNumber(r.approved_quantity),formatMoney(r.amount)])} />;
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

export default function App() {
  const [section, setSection] = useState("dashboard");
  const [data, setData] = useState(null);
  const [downtime, setDowntime] = useState([]);
  const [recon, setRecon] = useState([]);
  const [payroll, setPayroll] = useState([]);
  const [shift, setShift] = useState("DAY");

  useEffect(() => {
    Promise.all([api.summary(), api.downtime(), api.reconciliation(), api.payroll()]).then(([a,b,c,d]) => {
      setData(a); setDowntime(b); setRecon(c); setPayroll(d);
    });
  }, []);

  const title = useMemo(() => menu.find(([key]) => key === section)?.[1] ?? "Обзор", [section]);
  if (!data) return <div className="loading">Загрузка VITAGROUP OEE…</div>;

  return <div className="app">
    <aside>
      <div className="brand"><div className="brand-mark">VG</div><div><b>VITAGROUP</b><span>Production & OEE</span></div></div>
      <nav>{menu.map(([key,label]) => <button key={key} className={section===key ? "active" : ""} onClick={() => setSection(key)}>{label}</button>)}</nav>
      <div className="side-foot"><span className="live-dot" /> Демо-режим</div>
    </aside>
    <main>
      <header>
        <div><p>ООО «ВИТА ГРУПП»</p><h1>{title}</h1></div>
        <div className="controls">
          {section !== "integrations" && <div className="shift-switch">
            <button className={shift==="DAY" ? "active" : ""} onClick={() => setShift("DAY")}>ДЕНЬ</button>
            <button className={shift==="NIGHT" ? "active" : ""} onClick={() => setShift("NIGHT")}>НОЧЬ</button>
          </div>}
          <div className="date-box"><b>23.09.2026</b><span>{section === "integrations" ? "Администрирование" : shift==="DAY" ? "09:00–21:00" : "21:00–09:00"}</span></div>
        </div>
      </header>
      <div className="content">
        {section === "dashboard" && <Dashboard data={data} />}
        {section === "production" && <Dashboard data={data} />}
        {section === "downtime" && <Downtime rows={downtime} />}
        {section === "quality" && <Reconciliation rows={recon} />}
        {section === "reconciliation" && <Reconciliation rows={recon} />}
        {section === "payroll" && <Payroll rows={payroll} />}
        {section === "integrations" && <Integrations />}
      </div>
    </main>
  </div>;
}
