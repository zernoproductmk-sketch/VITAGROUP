import { useEffect, useMemo, useState } from "react";
import { api } from "./api";

const today = () => new Date().toISOString().slice(0,10);

const emptyForm = {
  id: null,
  product_id: "",
  equipment_id: "",
  ideal_rate_per_hour: "",
  valid_from: today(),
  valid_to: "",
  apply_to_open_runs: true
};

export default function NormAdminPage(){
  const [data,setData]=useState({products:[],equipment:[],norms:[]});
  const [form,setForm]=useState(emptyForm);
  const [notice,setNotice]=useState("");
  const [busy,setBusy]=useState(false);
  const [query,setQuery]=useState("");

  const refresh=async()=>setData(await api.adminNorms());
  useEffect(()=>{refresh();},[]);

  const filtered=useMemo(()=>{
    const needle=query.trim().toLowerCase();
    if(!needle) return data.norms;
    return data.norms.filter(row=>
      [row.product_article,row.product_code,row.product_name,row.equipment_code,row.equipment_name]
        .some(value=>String(value||"").toLowerCase().includes(needle))
    );
  },[data.norms,query]);

  const save=async()=>{
    setBusy(true);
    setNotice("");
    try{
      const result=await api.adminSaveNorm({
        ...form,
        ideal_rate_per_hour:Number(form.ideal_rate_per_hour),
        valid_to:form.valid_to||null
      });
      setNotice(
        result.applied_runs > 0
          ? `Норматив сохранен и применен к запускам без нормы: ${result.applied_runs}`
          : "Норматив сохранен."
      );
      setForm(emptyForm);
      await refresh();
    }catch(error){
      setNotice(error.message||"Не удалось сохранить норматив");
    }finally{
      setBusy(false);
    }
  };

  const edit=(row)=>setForm({
    id:row.source_system==="WEB"?row.id:null,
    product_id:row.product_id,
    equipment_id:row.equipment_id,
    ideal_rate_per_hour:String(row.ideal_rate_per_hour??""),
    valid_from:row.valid_from,
    valid_to:row.valid_to||"",
    apply_to_open_runs:true
  });

  return <>
    <section className="card panel">
      <div className="panel-head">
        <div>
          <h2>Нормативы скорости</h2>
          <span>Резервный справочник для Performance и OEE</span>
        </div>
      </div>

      <div className="norm-admin-form">
        <label>
          <span>Продукция</span>
          <select className="form-control" value={form.product_id} onChange={e=>setForm({...form,product_id:e.target.value})}>
            <option value="">Выберите продукцию</option>
            {data.products.map(item=><option key={item.id} value={item.id}>
              {(item.article||item.code)} · {item.name}
            </option>)}
          </select>
        </label>

        <label>
          <span>Линия</span>
          <select className="form-control" value={form.equipment_id} onChange={e=>setForm({...form,equipment_id:e.target.value})}>
            <option value="">Выберите линию</option>
            {data.equipment.map(item=><option key={item.id} value={item.id}>
              {item.code} · {item.name}
            </option>)}
          </select>
        </label>

        <label>
          <span>Идеальная скорость, шт./час</span>
          <input className="form-control" type="number" min="0" step="0.001" value={form.ideal_rate_per_hour} onChange={e=>setForm({...form,ideal_rate_per_hour:e.target.value})}/>
        </label>

        <label>
          <span>Действует с</span>
          <input className="form-control" type="date" value={form.valid_from} onChange={e=>setForm({...form,valid_from:e.target.value})}/>
        </label>

        <label>
          <span>Действует по</span>
          <input className="form-control" type="date" value={form.valid_to} onChange={e=>setForm({...form,valid_to:e.target.value})}/>
        </label>

        <label className="norm-checkbox">
          <input type="checkbox" checked={form.apply_to_open_runs} onChange={e=>setForm({...form,apply_to_open_runs:e.target.checked})}/>
          <span>Сразу применить к незавершенным запускам без нормы</span>
        </label>
      </div>

      <div className="action-row">
        <button
          className="btn primary"
          disabled={busy||!form.product_id||!form.equipment_id||Number(form.ideal_rate_per_hour)<=0||!form.valid_from}
          onClick={save}
        >
          {form.id?"Обновить норматив":"Добавить норматив"}
        </button>
        {form.id && <button className="btn ghost" onClick={()=>setForm(emptyForm)}>Отменить редактирование</button>}
      </div>

      {notice && <div className="notice">{notice}</div>}
    </section>

    <section className="card panel">
      <div className="panel-head">
        <h2>Действующие и исторические нормативы</h2>
        <input className="form-control norm-search" placeholder="Поиск по артикулу или линии" value={query} onChange={e=>setQuery(e.target.value)}/>
      </div>
      <div className="table-wrap">
        <table className="norm-table">
          <thead>
            <tr>
              <th>Продукция</th><th>Линия</th><th>Норма, шт./ч</th><th>Период</th><th>Источник</th><th></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(row=><tr key={row.id}>
              <td><b>{row.product_article||row.product_code}</b><small>{row.product_name}</small></td>
              <td><b>{row.equipment_code}</b><small>{row.equipment_name}</small></td>
              <td>{new Intl.NumberFormat("ru-RU",{maximumFractionDigits:3}).format(row.ideal_rate_per_hour||0)}</td>
              <td>{row.valid_from} — {row.valid_to||"без окончания"}</td>
              <td><span className={`status ${row.source_system==="WEB"?"warning":"success"}`}>{row.source_system}</span></td>
              <td>
                <button className="btn ghost" onClick={()=>edit(row)}>
                  {row.source_system==="WEB"?"Редактировать":"Взять за основу"}
                </button>
              </td>
            </tr>)}
            {filtered.length===0 && <tr><td colSpan="6"><div className="empty-state">Нормативы пока не заполнены.</div></td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  </>;
}
