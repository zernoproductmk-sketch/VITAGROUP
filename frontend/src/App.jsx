import { useEffect, useMemo, useState } from "react";
import { api } from "./api";

const menu = [
  ["dashboard", "Обзор"],
  ["production", "Производство"],
  ["downtime", "Простои"],
  ["quality", "ГП и брак"],
  ["reconciliation", "Сверка"],
  ["payroll", "Сдельная ЗП"]
];

const formatNumber = (value) => new Intl.NumberFormat("ru-RU").format(value ?? 0);
const formatMoney = (value) => new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", maximumFractionDigits: 0 }).format(value ?? 0);

function Metric({ label, value, suffix = "%", note }) {
  return (
    <div className="metric card">
      <span>{label}</span>
      <strong>{value}{suffix}</strong>
      {note && <small>{note}</small>}
    </div>
  );
}

function Status({ state }) {
  const down = state === "DOWNTIME";
  return <span className={`status ${down ? "danger" : "success"}`}>{down ? "ПРОСТОЙ" : "РАБОТАЕТ"}</span>;
}

function Dashboard({ data }) {
  const p = data.production;
  const completion = Math.min(100, Math.round((p.operator_output / p.plan) * 100));
  return (
    <>
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
          {data.equipment.map((item) => (
            <article className="equipment" key={item.code}>
              <div className="equipment-head"><div><small>{item.code}</small><h3>{item.name}</h3></div><Status state={item.state} /></div>
              <p>{item.product}</p>
              <div className="equipment-kpi">
                <div><span>OEE</span><b>{item.oee}%</b></div>
                <div><span>Выпуск</span><b>{formatNumber(item.output)}</b></div>
                <div><span>Простой</span><b>{item.downtime_minutes} мин</b></div>
              </div>
              {item.downtime_reason && <div className="alert">Причина: {item.downtime_reason}</div>}
            </article>
          ))}
        </div>
      </section>
    </>
  );
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

function Table({ title, columns, rows }) {
  return (
    <section className="card panel table-card">
      <div className="panel-head"><h2>{title}</h2><span>{rows.length} строк</span></div>
      <div className="table-wrap"><table><thead><tr>{columns.map(c => <th key={c}>{c}</th>)}</tr></thead><tbody>{rows.map((row, i) => <tr key={i}>{row.map((cell,j) => <td key={j}>{cell}</td>)}</tr>)}</tbody></table></div>
    </section>
  );
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

  return (
    <div className="app">
      <aside>
        <div className="brand"><div className="brand-mark">VG</div><div><b>VITAGROUP</b><span>Production & OEE</span></div></div>
        <nav>{menu.map(([key,label]) => <button key={key} className={section===key ? "active" : ""} onClick={() => setSection(key)}>{label}</button>)}</nav>
        <div className="side-foot"><span className="live-dot" /> Демо-режим</div>
      </aside>

      <main>
        <header>
          <div><p>ООО «ВИТА ГРУПП»</p><h1>{title}</h1></div>
          <div className="controls">
            <div className="shift-switch">
              <button className={shift==="DAY" ? "active" : ""} onClick={() => setShift("DAY")}>ДЕНЬ</button>
              <button className={shift==="NIGHT" ? "active" : ""} onClick={() => setShift("NIGHT")}>НОЧЬ</button>
            </div>
            <div className="date-box"><b>23.09.2026</b><span>{shift==="DAY" ? "09:00–21:00" : "21:00–09:00"}</span></div>
          </div>
        </header>

        <div className="content">
          {section === "dashboard" && <Dashboard data={data} />}
          {section === "production" && <Dashboard data={data} />}
          {section === "downtime" && <Downtime rows={downtime} />}
          {section === "quality" && <Reconciliation rows={recon} />}
          {section === "reconciliation" && <Reconciliation rows={recon} />}
          {section === "payroll" && <Payroll rows={payroll} />}
        </div>
      </main>
    </div>
  );
}
