import { useEffect, useMemo, useState } from "react";
import { api } from "./api";

const nf = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 });

function StateBadge({ state }) {
  const map = {
    RUNNING: ["success", "В РАБОТЕ"],
    DOWNTIME: ["danger", "ПРОСТОЙ"],
    PAUSED: ["warning", "ПАУЗА"],
    PLANNED: ["warning", "ПЛАН"],
    COMPLETED: ["success", "ЗАВЕРШЕНО"],
    VERIFIED: ["success", "ПРОВЕРЕНО"],
  };
  const [cls, label] = map[state] || ["warning", state || "—"];
  return <span className={`status ${cls}`}>{label}</span>;
}

function Kpi({ label, value, suffix = "" }) {
  return <div className="card mini-kpi">
    <span>{label}</span>
    <b>{value === null || value === undefined ? "—" : `${nf.format(value)}${suffix}`}</b>
  </div>;
}

function LineCard({ line, onOpenControl, canComplete, onComplete }) {
  const progress = line.planned_qty > 0
    ? Math.min(100, Math.max(0, line.output_qty / line.planned_qty * 100))
    : 0;

  return <article className={`master-line-card ${line.alerts?.some(a=>a.severity==="CRITICAL") ? "critical" : ""}`}>
    <div className="master-line-head">
      <div>
        <div className="master-line-code">{line.equipment_code}</div>
        <b>{line.equipment_name}</b>
      </div>
      <StateBadge state={line.state} />
    </div>

    <div className="master-order">
      <span>{line.order_no || "Без заказа"}</span>
      <b>{line.product_name}</b>
      <small>{line.product_article}</small>
    </div>

    <div className="progress"><i style={{width:`${progress}%`}} /></div>

    <div className="master-line-stats">
      <div><span>План</span><b>{nf.format(line.planned_qty || 0)}</b></div>
      <div><span>Выпуск</span><b>{nf.format(line.output_qty || 0)}</b></div>
      <div><span>OEE</span><b>{line.oee == null ? "—" : `${nf.format(line.oee)}%`}</b></div>
      <div><span>Темп</span><b>{line.pace_percent == null ? "—" : `${nf.format(line.pace_percent)}%`}</b></div>
    </div>

    <div className="master-staff">
      <span>На линии</span>
      <div>
        {line.staff?.length
          ? line.staff.map(person => <span className="staff-chip" key={person.id}>{person.full_name}</span>)
          : <small>Сотрудники не определены</small>}
      </div>
    </div>

    {line.active_downtime && <div className="master-downtime">
      <b>{line.active_downtime.reason}</b>
      <span>Простой с {new Date(line.active_downtime.started_at).toLocaleTimeString("ru-RU",{hour:"2-digit",minute:"2-digit"})}</span>
    </div>}

    {line.alerts?.length > 0 && <div className="master-alert-list">
      {line.alerts.map((alert,index)=><div key={index} className={alert.severity==="CRITICAL" ? "critical-alert" : "warning-alert"}>{alert.message}</div>)}
    </div>}

    <div className="master-line-actions">
      {line.reconciliation?.severity && line.reconciliation.severity !== "OK" && <button className="btn secondary" onClick={()=>onOpenControl(line.production_run_id)}>
        Разобрать расхождение
      </button>}
      {canComplete && !["COMPLETED","VERIFIED"].includes(line.state) && <button
        className="btn ghost"
        disabled={Boolean(line.active_downtime)}
        onClick={()=>onComplete(line)}
      >
        Завершить запуск
      </button>}
    </div>
  </article>;
}

export default function ShiftMasterDashboard({ businessDate, shiftCode, onOpenControl, canClose }) {
  const [data, setData] = useState(null);
  const [showProblems, setShowProblems] = useState(false);
  const [closeState, setCloseState] = useState(null);
  const [closeMessage, setCloseMessage] = useState("");

  const refresh = async () => {
    const [dashboard, readiness] = await Promise.all([
      api.shiftMasterDashboard(businessDate, shiftCode),
      api.shiftCloseReadiness(businessDate, shiftCode)
    ]);
    setData(dashboard);
    setCloseState(readiness);
  };

  useEffect(() => {
    setData(null);
    setCloseState(null);
    refresh();
  }, [businessDate, shiftCode]);

  const lines = useMemo(() => {
    if (!data) return [];
    return showProblems ? data.lines.filter(line => line.alerts?.length) : data.lines;
  }, [data, showProblems]);

  if (!data) return <div className="card panel">Загрузка кабинета сменного мастера…</div>;

  return <>
    <div className="integration-toolbar card master-toolbar">
      <div>
        <h2>Кабинет сменного мастера</h2>
        <p>{data.shift.label} · {data.shift.time} · оперативный контроль производства</p>
      </div>
      <label className="problem-switch">
        <input type="checkbox" checked={showProblems} onChange={e=>setShowProblems(e.target.checked)} />
        <span>Только проблемные линии</span>
      </label>
    </div>

    <div className="master-kpis">
      <Kpi label="Линий в смене" value={data.summary.lines} />
      <Kpi label="В работе" value={data.summary.running} />
      <Kpi label="В простое" value={data.summary.downtime} />
      <Kpi label="Проблемных" value={data.summary.problem_lines} />
      <Kpi label="Сотрудников" value={data.summary.staff} />
      <Kpi label="OEE смены" value={data.kpi.oee} suffix="%" />
    </div>

    <div className="master-progress card">
      <div>
        <span>Время смены прошло</span>
        <b>{nf.format(data.expected_progress_percent || 0)}%</b>
      </div>
      <div className="progress"><i style={{width:`${Math.min(100,data.expected_progress_percent || 0)}%`}} /></div>
      <div className="master-production-strip">
        <span>План <b>{nf.format(data.production.plan || 0)}</b></span>
        <span>Выпуск <b>{nf.format(data.production.operator_output || 0)}</b></span>
        <span>Годное <b>{nf.format(data.production.good_product || 0)}</b></span>
        <span>Простой <b>{nf.format(data.time.downtime_minutes || 0)} мин</b></span>
      </div>
    </div>

    {data.alerts?.length > 0 && <section className="card panel">
      <div className="panel-head"><h2>Требует внимания</h2><span>{data.alerts.length} событий</span></div>
      <div className="master-alert-board">
        {data.alerts.slice(0,8).map((alert,index)=><div key={index} className={alert.severity==="CRITICAL" ? "critical-alert" : "warning-alert"}>
          <b>{alert.equipment_code}</b>
          <span>{alert.message}</span>
        </div>)}
      </div>
    </section>}

    <section className="card panel master-close-panel">
      <div className="panel-head">
        <div>
          <h2>Закрытие смены</h2>
          <span>Контрольный чек-лист перед фиксацией статуса CLOSED</span>
        </div>
        <span className={`status ${closeState?.ready ? "success" : "warning"}`}>
          {closeState?.ready ? "ГОТОВА К ЗАКРЫТИЮ" : "ЕСТЬ БЛОКИРУЮЩИЕ ПУНКТЫ"}
        </span>
      </div>

      <div className="close-checklist">
        {(closeState?.blockers || []).map(item => <div className="close-item blocker" key={item.code}>
          <b>Блокирует</b><span>{item.message}</span>
        </div>)}
        {(closeState?.warnings || []).map(item => <div className="close-item warning-item" key={item.code}>
          <b>Предупреждение</b><span>{item.message}</span>
        </div>)}
        {closeState?.ready && (closeState?.warnings || []).length === 0 && <div className="close-item ready-item">
          <b>Готово</b><span>Блокирующих замечаний нет.</span>
        </div>}
      </div>

      {closeMessage && <div className="notice">{closeMessage}</div>}

      {canClose && <div className="master-close-actions">
        <button
          className="btn primary"
          disabled={!closeState?.ready || data.shift?.status === "CLOSED" || data.shift?.status === "VERIFIED"}
          onClick={async()=>{
            try {
              const result = await api.closeShift(businessDate, shiftCode);
              setCloseMessage(result.already_closed ? "Смена уже была закрыта." : "Смена закрыта.");
              await refresh();
            } catch (error) {
              setCloseMessage(error.message || "Не удалось закрыть смену");
            }
          }}
        >
          {data.shift?.status === "CLOSED" || data.shift?.status === "VERIFIED" ? "Смена закрыта" : "Закрыть смену"}
        </button>
      </div>}
    </section>

    <section className="master-lines">
      {lines.map(line => <LineCard
        key={line.production_run_id}
        line={line}
        onOpenControl={onOpenControl}
        canComplete={canClose}
        onComplete={async(currentLine)=>{
          const ok = window.confirm(`Завершить запуск на линии ${currentLine.equipment_code} по заказу ${currentLine.order_no || "без номера"}?`);
          if (!ok) return;
          try {
            await api.completeProductionRun(currentLine.production_run_id);
            setCloseMessage(`Запуск ${currentLine.equipment_code} завершен.`);
            await refresh();
          } catch (error) {
            setCloseMessage(error.message || "Не удалось завершить запуск");
          }
        }}
      />)}
      {lines.length===0 && <div className="card panel"><div className="empty-state">Линий для отображения нет.</div></div>}
    </section>
  </>;
}
