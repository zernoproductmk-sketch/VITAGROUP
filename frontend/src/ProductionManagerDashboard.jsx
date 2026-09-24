import { useEffect, useState } from "react";
import { api } from "./api";

const nf = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 });

function Kpi({ label, value, suffix="" }) {
  return <div className="card mini-kpi"><span>{label}</span><b>{value==null?"—":`${nf.format(value)}${suffix}`}</b></div>;
}

function ShiftBlock({ title, block, onOpenMaster, onOpenControl, canVerify, onVerify }) {
  if (!block) return null;
  return <section className="card panel manager-shift-block">
    <div className="panel-head">
      <div><h2>{title}</h2><span>{block.shift.time}</span></div>
      <span className="status success">{block.status}</span>
    </div>
    <div className="manager-shift-kpis">
      <div><span>План</span><b>{nf.format(block.production.plan||0)}</b></div>
      <div><span>Выпуск</span><b>{nf.format(block.production.operator_output||0)}</b></div>
      <div><span>OEE</span><b>{block.kpi.oee==null?"—":`${nf.format(block.kpi.oee)}%`}</b></div>
      <div><span>Простой</span><b>{nf.format(block.time.downtime_minutes||0)} мин</b></div>
      <div><span>Открытые расхождения</span><b>{block.reconciliation.open_cases}</b></div>
    </div>
    <div className="action-row">
      <button className="btn secondary" onClick={()=>onOpenMaster(block.shift.type)}>Открыть кабинет мастера</button>
      <button className="btn ghost" onClick={()=>onOpenControl(block.shift.type)}>Открыть контроль смены</button>
      {canVerify && block.status === "CLOSED" && <button className="btn primary" onClick={()=>onVerify(block.shift.type)}>Подтвердить смену</button>}
      {block.status === "VERIFIED" && <span className="status success">VERIFIED</span>}
    </div>
  </section>;
}

export default function ProductionManagerDashboard({ businessDate, onOpenMaster, onOpenControl, canVerify }) {
  const [data,setData]=useState(null);
  const [message,setMessage]=useState("");
  const refresh=async()=>setData(await api.productionManagerDay(businessDate));
  useEffect(()=>{ setData(null); setMessage(""); refresh(); },[businessDate]);
  if(!data) return <div className="card panel">Загрузка кабинета руководителя производства…</div>;

  return <>
    <div className="integration-toolbar card">
      <div><h2>Кабинет руководителя производства</h2><p>Итоги и проблемы по дневной и ночной сменам</p></div>
    </div>

    <div className="manager-kpis">
      <Kpi label="План за день" value={data.summary.plan} />
      <Kpi label="Выпуск" value={data.summary.output} />
      <Kpi label="Выполнение" value={data.summary.completion_percent} suffix="%" />
      <Kpi label="OEE" value={data.summary.oee} suffix="%" />
      <Kpi label="Простой" value={data.summary.downtime_minutes} suffix=" мин" />
      <Kpi label="Открытых кейсов" value={data.summary.open_cases} />
    </div>

    {message && <div className="notice">{message}</div>}

    <div className="two-col manager-shifts">
      <ShiftBlock
        title="Дневная смена"
        block={data.day}
        onOpenMaster={onOpenMaster}
        onOpenControl={onOpenControl}
        canVerify={canVerify}
        onVerify={async(shiftCode)=>{
          try {
            const result=await api.verifyShift(businessDate,shiftCode);
            setMessage(result.already_verified ? "Смена уже была подтверждена." : "Смена подтверждена. Производственные запуски переведены в VERIFIED.");
            await refresh();
          } catch(error) {
            setMessage(error.message || "Не удалось подтвердить смену");
          }
        }}
      />
      <ShiftBlock
        title="Ночная смена"
        block={data.night}
        onOpenMaster={onOpenMaster}
        onOpenControl={onOpenControl}
        canVerify={canVerify}
        onVerify={async(shiftCode)=>{
          try {
            const result=await api.verifyShift(businessDate,shiftCode);
            setMessage(result.already_verified ? "Смена уже была подтверждена." : "Смена подтверждена. Производственные запуски переведены в VERIFIED.");
            await refresh();
          } catch(error) {
            setMessage(error.message || "Не удалось подтвердить смену");
          }
        }}
      />
    </div>

    <section className="card panel">
      <div className="panel-head"><h2>Линии — день / ночь</h2><span>{data.equipment.length} линий</span></div>
      <div className="table-wrap">
        <table className="manager-lines-table">
          <thead><tr><th>Линия</th><th>День OEE</th><th>День выпуск</th><th>Ночь OEE</th><th>Ночь выпуск</th></tr></thead>
          <tbody>
            {data.equipment.map(row=><tr key={row.code}>
              <td><b>{row.code}</b><small>{row.name}</small></td>
              <td>{row.day?.oee==null?"—":`${nf.format(row.day.oee)}%`}</td>
              <td>{nf.format(row.day?.output||0)}</td>
              <td>{row.night?.oee==null?"—":`${nf.format(row.night.oee)}%`}</td>
              <td>{nf.format(row.night?.output||0)}</td>
            </tr>)}
            {data.equipment.length===0 && <tr><td colSpan="5"><div className="empty-state">Нет данных по линиям.</div></td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  </>;
}
