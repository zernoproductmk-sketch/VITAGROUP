import { useEffect, useMemo, useState } from "react";
import { api } from "./api";

const isoToday = () => new Date().toISOString().slice(0,10);

function RunSetup({ run, employees, onSaved }) {
  const [selected,setSelected]=useState(run.staff?.map(item=>item.employee_id)||[]);
  const [notice,setNotice]=useState("");

  useEffect(()=>{
    setSelected(run.staff?.map(item=>item.employee_id)||[]);
  },[run.id,run.staff]);

  const save=async()=>{
    try{
      await api.assignTestShiftStaff(run.id,selected);
      setNotice("Сотрудники назначены");
      await onSaved();
    }catch(error){
      setNotice(error.message||"Не удалось сохранить назначение");
    }
  };

  const toggle=(id)=>{
    setSelected(current=>current.includes(id)
      ? current.filter(item=>item!==id)
      : [...current,id]
    );
  };

  return <article className={`test-run-card ${run.ready?"ready":"blocked"}`}>
    <div className="test-run-head">
      <div>
        <b>{run.equipment_code}</b>
        <span>{run.order_no||"Без заказа"}</span>
      </div>
      <span className={`status ${run.ready?"success":"warning"}`}>
        {run.ready?"ГОТОВО":"ТРЕБУЕТ ПОДГОТОВКИ"}
      </span>
    </div>

    <h3>{run.product_name}</h3>
    <small>{run.product_article||run.product_code}</small>

    <div className="test-run-facts">
      <div><span>План</span><b>{new Intl.NumberFormat("ru-RU").format(run.planned_qty||0)}</b></div>
      <div><span>Норма</span><b>{run.ideal_rate_per_hour ? new Intl.NumberFormat("ru-RU",{maximumFractionDigits:1}).format(run.ideal_rate_per_hour) + " шт/ч" : "нет"}</b></div>
      <div><span>Сотрудников</span><b>{run.staff?.length||0}</b></div>
    </div>

    <div className="test-staff-picker">
      {employees.map(employee=><label key={employee.id}>
        <input type="checkbox" checked={selected.includes(employee.id)} onChange={()=>toggle(employee.id)}/>
        <span><b>{employee.full_name}</b><small>{employee.position_name||"Без должности"} · {employee.personnel_number}</small></span>
      </label>)}
    </div>

    <button className="btn secondary test-save" disabled={selected.length===0} onClick={save}>
      Сохранить состав линии
    </button>

    {notice&&<div className="notice">{notice}</div>}
  </article>;
}

export default function TestShiftPage({ onOpenERP, onOpenNorms, onOpenMaster }) {
  const [businessDate,setBusinessDate]=useState(isoToday());
  const [shiftCode,setShiftCode]=useState("DAY");
  const [data,setData]=useState(null);
  const [notice,setNotice]=useState("");

  const refresh=async()=>{
    try{
      setData(await api.testShiftContext(businessDate,shiftCode));
    }catch(error){
      setNotice(error.message||"Не удалось загрузить подготовку смены");
    }
  };

  useEffect(()=>{refresh();},[businessDate,shiftCode]);

  const blockers=useMemo(()=>data?.summary?.blockers||[],[data]);

  if(!data) return <div className="card panel">Загрузка мастера тестовой смены…</div>;

  return <>
    <div className="integration-toolbar card">
      <div>
        <h2>Мастер первой тестовой смены</h2>
        <p>Подготовка плана, нормативов и сотрудников перед запуском</p>
      </div>
      <div className="test-shift-controls">
        <input className="form-control" type="date" value={businessDate} onChange={e=>setBusinessDate(e.target.value)}/>
        <div className="shift-switch">
          <button className={shiftCode==="DAY"?"active":""} onClick={()=>setShiftCode("DAY")}>ДЕНЬ</button>
          <button className={shiftCode==="NIGHT"?"active":""} onClick={()=>setShiftCode("NIGHT")}>НОЧЬ</button>
        </div>
      </div>
    </div>

    <div className="test-shift-summary">
      <div className="card mini-kpi"><span>Запусков</span><b>{data.summary.runs}</b></div>
      <div className="card mini-kpi"><span>С нормой</span><b>{data.summary.with_norm}</b></div>
      <div className="card mini-kpi"><span>С сотрудниками</span><b>{data.summary.with_staff}</b></div>
      <div className="card mini-kpi"><span>Статус</span><b>{data.summary.ready?"ГОТОВО":"НЕ ГОТОВО"}</b></div>
    </div>

    {data.shift.status==="NOT_CREATED" && <section className="card panel">
      <div className="panel-head"><h2>Смена еще не создана</h2></div>
      <p className="muted">Сначала загрузите и продвиньте производственный план. Если план уже подготовлен, можно создать смену вручную и затем повторно продвинуть ERP-план.</p>
      <div className="action-row">
        <button className="btn secondary" onClick={onOpenERP}>Открыть план ERP</button>
        <button className="btn primary" onClick={async()=>{
          try{
            await api.createTestShift(businessDate,shiftCode);
            setNotice("Смена создана. Теперь продвиньте ERP-план в производственные запуски.");
            await refresh();
          }catch(error){setNotice(error.message||"Не удалось создать смену");}
        }}>Создать смену</button>
      </div>
    </section>}

    {blockers.length>0 && <section className="card panel">
      <div className="panel-head"><h2>Что мешает запуску</h2><span>{blockers.length}</span></div>
      <div className="test-blockers">
        {blockers.map((item,index)=><div key={index}>{item}</div>)}
      </div>
      <div className="action-row">
        <button className="btn ghost" onClick={onOpenERP}>План ERP</button>
        <button className="btn ghost" onClick={onOpenNorms}>Нормативы</button>
      </div>
    </section>}

    <section className="test-run-grid">
      {data.runs.map(run=><RunSetup key={run.id} run={run} employees={data.employees} onSaved={refresh}/>)}
      {data.runs.length===0 && <div className="card panel"><div className="empty-state">Производственные запуски для выбранной смены пока не созданы.</div></div>}
    </section>

    {data.summary.ready && <section className="card panel test-ready-box">
      <div>
        <span>Контроль пройден</span>
        <h2>Смена готова к тестовому запуску</h2>
        <p>По всем запускам есть план, норматив скорости и назначенные сотрудники.</p>
      </div>
      <button className="btn primary" onClick={()=>onOpenMaster(shiftCode)}>Перейти в кабинет сменного мастера</button>
    </section>}

    {notice&&<div className="notice">{notice}</div>}
  </>;
}
