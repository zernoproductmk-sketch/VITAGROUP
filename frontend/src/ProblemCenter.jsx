import { useEffect, useMemo, useState } from "react";
import { api } from "./api";

const severityLabel = {
  CRITICAL: "КРИТИЧНО",
  WARNING: "ВНИМАНИЕ",
  INFO: "ИНФО"
};

const ownerLabel = {
  SHIFT_MASTER: "Сменный мастер",
  PRODUCTION_MANAGER: "Руководитель производства",
  ACCOUNTANT_PRODUCTION: "Учетчик",
  ECONOMIST: "Экономист",
  MANAGEMENT: "Руководство",
  ADMIN: "Администратор"
};

function ProblemCard({ item, onOpen }) {
  return <article className={`problem-card ${item.severity.toLowerCase()}`}>
    <div className="problem-card-head">
      <span className={`status ${item.severity === "CRITICAL" ? "danger" : item.severity === "WARNING" ? "warning" : "success"}`}>
        {severityLabel[item.severity] || item.severity}
      </span>
      <small>{item.source}</small>
    </div>
    <h3>{item.title}</h3>
    <p>{item.message}</p>
    <div className="problem-meta">
      <span><b>Ответственный:</b> {ownerLabel[item.owner_role] || item.owner_role}</span>
      {item.business_date && <span><b>Дата:</b> {item.business_date}</span>}
      {item.shift_code && <span><b>Смена:</b> {item.shift_code === "DAY" ? "ДЕНЬ" : "НОЧЬ"}</span>}
      {item.equipment_code && <span><b>Линия:</b> {item.equipment_code}</span>}
    </div>
    <button className="btn secondary problem-open" onClick={() => onOpen(item)}>
      Перейти к решению
    </button>
  </article>;
}

export default function ProblemCenter({ businessDate, shiftCode, onNavigate }) {
  const [data, setData] = useState(null);
  const [filter, setFilter] = useState("ALL");

  const refresh = async () => {
    setData(await api.problemCenter(businessDate, shiftCode));
  };

  useEffect(() => { refresh(); }, [businessDate, shiftCode]);

  const rows = useMemo(() => {
    if (!data) return [];
    if (filter === "ALL") return data.items;
    return data.items.filter(item => item.severity === filter);
  }, [data, filter]);

  if (!data) return <div className="card panel">Загрузка центра проблем…</div>;

  return <>
    <div className="integration-toolbar card">
      <div>
        <h2>Центр уведомлений и проблем</h2>
        <p>Единая очередь производственных, сменных и интеграционных проблем</p>
      </div>
      <button className="btn ghost" onClick={refresh}>Обновить</button>
    </div>

    <div className="problem-kpis">
      <div className="card mini-kpi"><span>Всего</span><b>{data.summary.total}</b></div>
      <div className="card mini-kpi"><span>Критично</span><b>{data.summary.critical}</b></div>
      <div className="card mini-kpi"><span>Предупреждения</span><b>{data.summary.warning}</b></div>
      <div className="card mini-kpi"><span>Производство</span><b>{data.summary.production}</b></div>
      <div className="card mini-kpi"><span>Интеграции</span><b>{data.summary.integration}</b></div>
    </div>

    <div className="problem-filters">
      {[
        ["ALL","Все"],
        ["CRITICAL","Критичные"],
        ["WARNING","Предупреждения"]
      ].map(([key,label])=><button key={key} className={filter===key?"active":""} onClick={()=>setFilter(key)}>{label}</button>)}
    </div>

    <section className="problem-grid">
      {rows.map(item => <ProblemCard key={item.key} item={item} onOpen={onNavigate} />)}
      {rows.length === 0 && <div className="card panel"><div className="empty-state">Активных проблем по выбранному фильтру нет.</div></div>}
    </section>
  </>;
}
