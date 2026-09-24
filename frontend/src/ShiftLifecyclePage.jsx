import { useEffect, useState } from "react";
import { api } from "./api";

const today = () => new Date().toISOString().slice(0,10);

const meta = {
  READY: { label: "ГОТОВО", cls: "success" },
  PENDING: { label: "ОЖИДАЕТ", cls: "warning" },
  BLOCKED: { label: "БЛОКИРУЕТ", cls: "danger" }
};

export default function ShiftLifecyclePage({ onNavigate }) {
  const [businessDate,setBusinessDate]=useState(today());
  const [shiftCode,setShiftCode]=useState("DAY");
  const [data,setData]=useState(null);

  const refresh=async()=>{
    setData(await api.shiftLifecycle(businessDate,shiftCode));
  };

  useEffect(()=>{refresh();},[businessDate,shiftCode]);

  if(!data) return <div className="card panel">Загрузка сквозного теста смены…</div>;

  const progress = data.summary.total_steps
    ? Math.round(data.summary.completed_steps/data.summary.total_steps*100)
    : 0;

  return <>
    <div className="integration-toolbar card">
      <div>
        <h2>Сквозной тест смены</h2>
        <p>От ERP-плана до VERIFIED и готовности данных для расчета</p>
      </div>
      <div className="test-shift-controls">
        <input className="form-control" type="date" value={businessDate} onChange={e=>setBusinessDate(e.target.value)}/>
        <div className="shift-switch">
          <button className={shiftCode==="DAY"?"active":""} onClick={()=>setShiftCode("DAY")}>ДЕНЬ</button>
          <button className={shiftCode==="NIGHT"?"active":""} onClick={()=>setShiftCode("NIGHT")}>НОЧЬ</button>
        </div>
        <button className="btn ghost" onClick={refresh}>Обновить</button>
      </div>
    </div>

    <section className="card lifecycle-progress-card">
      <div className="lifecycle-progress-head">
        <div>
          <span>Пройдено этапов</span>
          <b>{data.summary.completed_steps} / {data.summary.total_steps}</b>
        </div>
        <strong>{progress}%</strong>
      </div>
      <div className="progress"><i style={{width:`${progress}%`}} /></div>
      <small>
        Статус смены: {data.shift.status || "—"}
        {data.summary.verified ? " · Смена полностью подтверждена" : ""}
      </small>
    </section>

    <section className="lifecycle-grid">
      {data.stages.map((stage,index)=>{
        const m=meta[stage.status]||meta.PENDING;
        return <article className={`lifecycle-card ${stage.status.toLowerCase()}`} key={stage.key}>
          <div className="lifecycle-number">{index+1}</div>
          <div className="lifecycle-body">
            <div className="lifecycle-title">
              <h3>{stage.title}</h3>
              <span className={`status ${m.cls}`}>{m.label}</span>
            </div>
            <p>{stage.message}</p>
            <button className="btn ghost" onClick={()=>onNavigate(stage.target_section,shiftCode)}>
              Открыть этап
            </button>
          </div>
        </article>;
      })}
    </section>
  </>;
}
