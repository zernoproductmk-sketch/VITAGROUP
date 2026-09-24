import { useEffect, useMemo, useState } from "react";
import { api } from "./api";

const nf = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 });

function Kpi({ label, value, suffix="", delta=null }) {
  return <div className="card executive-kpi">
    <span>{label}</span>
    <b>{value==null?"—":`${nf.format(value)}${suffix}`}</b>
    {delta!==null && <small className={delta>=0 ? "delta-up" : "delta-down"}>
      {delta>=0?"+":""}{nf.format(delta)} п.п.
    </small>}
  </div>;
}

function TrendChart({ rows }) {
  if (!rows.length) return <div className="empty-state">Недостаточно данных для динамики.</div>;
  const max = Math.max(100, ...rows.map(r => Math.max(r.oee || 0, r.completion_percent || 0)));
  return <div className="executive-chart">
    {rows.map(row => <div className="executive-chart-col" key={row.business_date}>
      <div className="executive-bars">
        <i className="bar oee" style={{height:`${((row.oee||0)/max)*100}%`}} title={`OEE: ${row.oee ?? "—"}%`} />
        <i className="bar plan" style={{height:`${((row.completion_percent||0)/max)*100}%`}} title={`Выполнение: ${row.completion_percent ?? "—"}%`} />
      </div>
      <span>{row.business_date.slice(5)}</span>
    </div>)}
  </div>;
}

export default function ManagementDashboard({ businessDate, onOpenProductionManager, onOpenControl }) {
  const [days,setDays]=useState(14);
  const [data,setData]=useState(null);

  useEffect(()=>{
    setData(null);
    api.managementOverview(businessDate,days).then(setData);
  },[businessDate,days]);

  const problemLines=useMemo(()=>data?.problem_lines||[],[data]);

  if(!data) return <div className="card panel">Загрузка кабинета руководства…</div>;

  return <>
    <div className="integration-toolbar card">
      <div>
        <h2>Кабинет руководства</h2>
        <p>Сводная эффективность производства без оперативного ввода</p>
      </div>
      <div className="executive-period">
        {[7,14,30].map(value=><button key={value} className={days===value?"active":""} onClick={()=>setDays(value)}>{value} дней</button>)}
      </div>
    </div>

    <div className="executive-kpis">
      <Kpi label="Выполнение плана" value={data.summary.completion_percent} suffix="%" delta={data.trend_change.completion} />
      <Kpi label="Средний OEE" value={data.summary.average_oee} suffix="%" delta={data.trend_change.oee} />
      <Kpi label="Выпуск" value={data.summary.output} />
      <Kpi label="Брак ОТК" value={data.summary.defect_rate_percent} suffix="%" />
      <Kpi label="Простой" value={data.summary.downtime_minutes} suffix=" мин" />
      <Kpi label="Открытые проблемы" value={data.summary.open_cases} />
    </div>

    <div className="two-col executive-top">
      <section className="card panel">
        <div className="panel-head">
          <div><h2>Динамика</h2><span>OEE и выполнение плана по дням</span></div>
        </div>
        <div className="executive-legend"><span><i className="legend-oee" /> OEE</span><span><i className="legend-plan" /> Выполнение плана</span></div>
        <TrendChart rows={data.daily} />
      </section>

      <section className="card panel executive-summary-panel">
        <div className="panel-head"><h2>Итоги периода</h2><span>{data.period.date_from} — {data.period.date_to}</span></div>
        <div className="executive-summary-grid">
          <div><span>План</span><b>{nf.format(data.summary.plan||0)}</b></div>
          <div><span>Годная продукция</span><b>{nf.format(data.summary.good||0)}</b></div>
          <div><span>Брак ОТК</span><b>{nf.format(data.summary.qc_defect||0)}</b></div>
          <div><span>Критичных кейсов</span><b>{data.summary.critical_cases}</b></div>
          <div><span>Без норматива</span><b>{data.summary.missing_norm_runs}</b></div>
        </div>
        <div className="action-row">
          <button className="btn secondary" onClick={onOpenProductionManager}>Открыть производство</button>
          <button className="btn ghost" onClick={onOpenControl}>Открыть контроль смены</button>
        </div>
      </section>
    </div>

    <section className="card panel">
      <div className="panel-head"><h2>Линии, требующие внимания</h2><span>по выбранному периоду</span></div>
      <div className="table-wrap">
        <table className="executive-lines-table">
          <thead><tr><th>Линия</th><th>OEE</th><th>Выполнение</th><th>Простой</th><th>Проблемных смен</th><th>Индекс внимания</th></tr></thead>
          <tbody>
            {problemLines.map(row=><tr key={row.code}>
              <td><b>{row.code}</b><small>{row.name}</small></td>
              <td>{row.average_oee==null?"—":`${nf.format(row.average_oee)}%`}</td>
              <td>{row.completion_percent==null?"—":`${nf.format(row.completion_percent)}%`}</td>
              <td>{nf.format(row.downtime_minutes||0)} мин</td>
              <td>{row.problem_shifts} / {row.shifts}</td>
              <td><span className={`attention-badge ${row.attention_score>=25?"high":row.attention_score>=10?"medium":"low"}`}>{nf.format(row.attention_score)}</span></td>
            </tr>)}
            {!problemLines.length && <tr><td colSpan="6"><div className="empty-state">Проблемных линий за период не выявлено.</div></td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  </>;
}
