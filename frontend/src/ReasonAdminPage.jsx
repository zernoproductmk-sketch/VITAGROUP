import { useEffect, useState } from "react";
import { api } from "./api";

const emptyDowntime = { id:null, code:"", category:"", name:"", affects_availability:true, is_planned:false, is_active:true };
const emptyDefect = { id:null, code:"", category:"", name:"", is_active:true };

export default function ReasonAdminPage(){
  const [data,setData]=useState({downtime:[],defects:[]});
  const [downtime,setDowntime]=useState(emptyDowntime);
  const [defect,setDefect]=useState(emptyDefect);
  const [notice,setNotice]=useState("");

  const refresh=async()=>setData(await api.adminReasons());
  useEffect(()=>{refresh();},[]);

  const saveDowntime=async()=>{
    await api.adminSaveDowntimeReason(downtime);
    setDowntime(emptyDowntime); setNotice("Причина простоя сохранена"); await refresh();
  };
  const saveDefect=async()=>{
    await api.adminSaveDefectReason(defect);
    setDefect(emptyDefect); setNotice("Причина брака сохранена"); await refresh();
  };

  return <>
    {notice && <div className="notice">{notice}</div>}
    <div className="two-col">
      <section className="card panel">
        <div className="panel-head"><h2>Причины простоев</h2><span>{data.downtime.length}</span></div>
        <div className="reason-form">
          <input className="form-control" placeholder="Код" value={downtime.code} onChange={e=>setDowntime({...downtime,code:e.target.value})}/>
          <input className="form-control" placeholder="Категория" value={downtime.category} onChange={e=>setDowntime({...downtime,category:e.target.value})}/>
          <input className="form-control" placeholder="Наименование" value={downtime.name} onChange={e=>setDowntime({...downtime,name:e.target.value})}/>
          <label><input type="checkbox" checked={downtime.affects_availability} onChange={e=>setDowntime({...downtime,affects_availability:e.target.checked})}/> Влияет на Availability</label>
          <label><input type="checkbox" checked={downtime.is_planned} onChange={e=>setDowntime({...downtime,is_planned:e.target.checked})}/> Плановый простой</label>
          <label><input type="checkbox" checked={downtime.is_active} onChange={e=>setDowntime({...downtime,is_active:e.target.checked})}/> Активна</label>
          <button className="btn primary" disabled={!downtime.code||!downtime.category||!downtime.name} onClick={saveDowntime}>Сохранить</button>
        </div>
        <div className="reason-list">
          {data.downtime.map(r=><button key={r.id} onClick={()=>setDowntime(r)}>
            <b>{r.code}</b><span>{r.name}</span><small>{r.category}{r.is_planned?" · плановый":""}</small>
          </button>)}
        </div>
      </section>

      <section className="card panel">
        <div className="panel-head"><h2>Причины брака</h2><span>{data.defects.length}</span></div>
        <div className="reason-form">
          <input className="form-control" placeholder="Код" value={defect.code} onChange={e=>setDefect({...defect,code:e.target.value})}/>
          <input className="form-control" placeholder="Категория" value={defect.category||""} onChange={e=>setDefect({...defect,category:e.target.value})}/>
          <input className="form-control" placeholder="Наименование" value={defect.name} onChange={e=>setDefect({...defect,name:e.target.value})}/>
          <label><input type="checkbox" checked={defect.is_active} onChange={e=>setDefect({...defect,is_active:e.target.checked})}/> Активна</label>
          <button className="btn primary" disabled={!defect.code||!defect.name} onClick={saveDefect}>Сохранить</button>
        </div>
        <div className="reason-list">
          {data.defects.map(r=><button key={r.id} onClick={()=>setDefect(r)}>
            <b>{r.code}</b><span>{r.name}</span><small>{r.category||"Без категории"}</small>
          </button>)}
        </div>
      </section>
    </div>
  </>;
}
