import { useEffect, useMemo, useState } from "react";
import { api } from "./api";

const nf = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 });

const labels = {
  operator: {
    title: "Кабинет оператора",
    subtitle: "Выпуск продукции, брак и простои"
  },
  qc: {
    title: "Кабинет ОТК",
    subtitle: "Контроль качества и подтвержденный брак"
  },
  warehouse: {
    title: "Кабинет кладовщика",
    subtitle: "Приемка готовой продукции"
  },
  accountant: {
    title: "Кабинет учетчика",
    subtitle: "Оперативный учет выпуска по талонам"
  }
};

const uuid = () => (
  globalThis.crypto?.randomUUID?.() ||
  `${Date.now()}-${Math.random().toString(16).slice(2)}`
);

function RunCard({ run, selected, onClick }) {
  const completion = run.planned_qty > 0
    ? Math.min(100, Math.round((run.output_qty / run.planned_qty) * 100))
    : 0;

  return <button className={`workspace-run ${selected ? "selected" : ""}`} onClick={onClick}>
    <div className="workspace-run-head">
      <div><b>{run.equipment_code}</b><span>{run.order_no || "Без заказа"}</span></div>
      <span className="status success">{run.status}</span>
    </div>
    <strong>{run.product_name}</strong>
    <small>{run.product_article || run.product_code}</small>
    <div className="progress"><i style={{width: `${completion}%`}} /></div>
    <div className="workspace-run-stats">
      <span>План <b>{nf.format(run.planned_qty || 0)}</b></span>
      <span>Выпуск <b>{nf.format(run.output_qty || 0)}</b></span>
    </div>
  </button>;
}

function WorkspaceHeader({ context }) {
  return <section className="card workspace-current">
    <div>
      <span className="workspace-eyebrow">Текущая смена</span>
      <h2>{context.shift.label} · {context.shift.time}</h2>
      <p>{context.shift.business_date}</p>
    </div>
    <div className="workspace-shift-badge">
      <span>Запусков</span>
      <b>{context.runs.length}</b>
    </div>
  </section>;
}

function OperatorForm({ context, selectedRun, onRefresh }) {
  const [tab, setTab] = useState("output");
  const [quantity, setQuantity] = useState("");
  const [defect, setDefect] = useState("");
  const [reason, setReason] = useState("");
  const [comment, setComment] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const submitOutput = async () => {
    if (!selectedRun || Number(quantity) <= 0) return;
    setBusy(true);
    await api.operatorOutput({
      production_run_id: selectedRun.id,
      quantity: Number(quantity),
      defect_quantity: null,
      occurred_at: null,
      comment: comment || null,
      client_event_id: uuid()
    });
    setQuantity("");
    setComment("");
    setNotice("Выпуск сохранен");
    await onRefresh();
    setBusy(false);
  };

  const submitDefect = async () => {
    if (!selectedRun || Number(defect) <= 0) return;
    setBusy(true);
    await api.operatorDefect({
      production_run_id: selectedRun.id,
      quantity: Number(defect),
      reason_id: reason || null,
      occurred_at: null,
      comment: comment || null,
      client_event_id: uuid()
    });
    setDefect("");
    setComment("");
    setNotice("Брак сохранен");
    await onRefresh();
    setBusy(false);
  };

  const startDowntime = async () => {
    if (!selectedRun) return;
    setBusy(true);
    await api.operatorDowntimeStart({
      production_run_id: selectedRun.id,
      reason_id: reason || null,
      started_at: null,
      comment: comment || null,
      client_event_id: uuid()
    });
    setNotice("Простой начат");
    await onRefresh();
    setBusy(false);
  };

  const active = context.active_downtime.find(item => item.production_run_id === selectedRun?.id);

  return <section className="card panel workspace-form-card">
    <div className="workspace-tabs">
      <button className={tab==="output" ? "active" : ""} onClick={() => setTab("output")}>Выпуск</button>
      <button className={tab==="defect" ? "active" : ""} onClick={() => setTab("defect")}>Брак</button>
      <button className={tab==="downtime" ? "active" : ""} onClick={() => setTab("downtime")}>Простой</button>
    </div>

    {tab === "output" && <>
      <label className="form-label">Количество, шт.</label>
      <input className="form-control" type="number" min="0" value={quantity} onChange={e => setQuantity(e.target.value)} />
      <label className="form-label">Комментарий</label>
      <input className="form-control" value={comment} onChange={e => setComment(e.target.value)} placeholder="При необходимости" />
      <button className="btn primary workspace-save" disabled={busy || !selectedRun || Number(quantity)<=0} onClick={submitOutput}>Сохранить выпуск</button>
    </>}

    {tab === "defect" && <>
      <label className="form-label">Количество брака, шт.</label>
      <input className="form-control" type="number" min="0" value={defect} onChange={e => setDefect(e.target.value)} />
      <label className="form-label">Причина</label>
      <select className="form-control" value={reason} onChange={e => setReason(e.target.value)}>
        <option value="">Не выбрано</option>
        {context.defect_reasons.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select>
      <label className="form-label">Комментарий</label>
      <input className="form-control" value={comment} onChange={e => setComment(e.target.value)} />
      <button className="btn primary workspace-save" disabled={busy || !selectedRun || Number(defect)<=0} onClick={submitDefect}>Сохранить брак</button>
    </>}

    {tab === "downtime" && <>
      {active ? <div className="workspace-active-downtime">
        <b>Простой идет</b>
        <span>{active.reason}</span>
        <small>Начало: {new Date(active.started_at).toLocaleTimeString("ru-RU",{hour:"2-digit",minute:"2-digit"})}</small>
        <button className="btn primary" disabled={busy} onClick={async()=>{
          setBusy(true);
          await api.operatorDowntimeStop(active.id,{ended_at:null});
          setNotice("Простой завершен");
          await onRefresh();
          setBusy(false);
        }}>Завершить простой</button>
      </div> : <>
        <label className="form-label">Причина простоя</label>
        <select className="form-control" value={reason} onChange={e => setReason(e.target.value)}>
          <option value="">Не выбрано</option>
          {context.downtime_reasons.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
        <label className="form-label">Комментарий</label>
        <input className="form-control" value={comment} onChange={e => setComment(e.target.value)} />
        <button className="btn primary workspace-save" disabled={busy || !selectedRun} onClick={startDowntime}>Начать простой</button>
      </>}
    </>}

    {notice && <div className="notice">{notice}</div>}
  </section>;
}

function QCForm({ context, selectedRun, onRefresh }) {
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState("");
  const [comment, setComment] = useState("");
  const [notice, setNotice] = useState("");

  const save = async () => {
    await api.qcDefect({
      production_run_id: selectedRun.id,
      quantity: Number(quantity),
      reason_id: reason || null,
      occurred_at: null,
      comment: comment || null,
      client_event_id: uuid()
    });
    setQuantity("");
    setComment("");
    setNotice("Подтвержденный брак ОТК сохранен");
    await onRefresh();
  };

  const saveNoDefect = async () => {
    await api.qcNoDefect({
      production_run_id: selectedRun.id,
      occurred_at: null,
      comment: comment || "Проверено ОТК, брак не выявлен",
      client_event_id: uuid()
    });
    setQuantity("");
    setReason("");
    setComment("");
    setNotice("Проверка ОТК без брака подтверждена");
    await onRefresh();
  };

  return <section className="card panel workspace-form-card">
    <h2>Фиксация брака ОТК</h2>
    <label className="form-label">Количество, шт.</label>
    <input className="form-control" type="number" min="0" value={quantity} onChange={e=>setQuantity(e.target.value)} />
    <label className="form-label">Причина брака</label>
    <select className="form-control" value={reason} onChange={e=>setReason(e.target.value)}>
      <option value="">Не выбрано</option>
      {context.defect_reasons.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}
    </select>
    <label className="form-label">Комментарий</label>
    <input className="form-control" value={comment} onChange={e=>setComment(e.target.value)} />
    <div className="qc-actions">
      <button className="btn primary workspace-save" disabled={!selectedRun || Number(quantity)<=0} onClick={save}>Сохранить брак</button>
      <button className="btn secondary workspace-save" disabled={!selectedRun} onClick={saveNoDefect}>Проверено, брака нет</button>
    </div>
    {notice && <div className="notice">{notice}</div>}
  </section>;
}

function WarehouseForm({ selectedRun, onRefresh }) {
  const [quantity, setQuantity] = useState("");
  const [documentNo, setDocumentNo] = useState("");
  const [notice, setNotice] = useState("");

  const save = async () => {
    await api.warehouseReceipt({
      production_run_id: selectedRun.id,
      quantity: Number(quantity),
      received_at: null,
      document_no: documentNo || null,
      client_event_id: uuid()
    });
    setQuantity("");
    setDocumentNo("");
    setNotice("Готовая продукция принята");
    await onRefresh();
  };

  return <section className="card panel workspace-form-card">
    <h2>Приемка готовой продукции</h2>
    <label className="form-label">Талон / документ</label>
    <input className="form-control" value={documentNo} onChange={e=>setDocumentNo(e.target.value)} />
    <label className="form-label">Количество, шт.</label>
    <input className="form-control" type="number" min="0" value={quantity} onChange={e=>setQuantity(e.target.value)} />
    <button className="btn primary workspace-save" disabled={!selectedRun || Number(quantity)<=0} onClick={save}>Принять на склад</button>
    {notice && <div className="notice">{notice}</div>}
  </section>;
}

function ShiftAssignmentForm({ context, selectedRun, onRefresh }) {
  const [open,setOpen]=useState(false);
  const [report,setReport]=useState({});
  const [notice,setNotice]=useState("");
  const [busy,setBusy]=useState(false);

  useEffect(()=>{
    setReport(selectedRun?.shift_assignment_report || {});
  },[selectedRun?.id,selectedRun?.shift_assignment_report]);

  if(!selectedRun) return null;

  const setField=(key,value)=>setReport(current=>({...current,[key]:value}));
  const materials=selectedRun.erp_raw_data?.materials || [];

  const save=async()=>{
    setBusy(true);
    try{
      await api.operatorShiftAssignment({
        production_run_id:selectedRun.id,
        report
      });
      setNotice("Сменное задание сохранено");
      await onRefresh();
    }catch(error){
      setNotice(error.message||"Не удалось сохранить сменное задание");
    }finally{
      setBusy(false);
    }
  };

  const plan=selectedRun.planned_qty||0;
  const shiftLabel=context?.shift?.code==="NIGHT"?"НОЧЬ":"ДЕНЬ";

  const input=(key,placeholder="",type="text")=><input
    className="shift-task-input"
    type={type}
    value={report[key]??""}
    placeholder={placeholder}
    onChange={e=>setField(key,e.target.value)}
  />;

  return <>
    <section className="card panel accountant-shift-task-card">
      <div>
        <span className="workspace-eyebrow">Документ смены</span>
        <h2>Сменное задание</h2>
        <p>{selectedRun.erp_task_id||selectedRun.order_no||"Задание ERP"} · {selectedRun.equipment_code}</p>
      </div>
      <button className="btn primary" onClick={()=>setOpen(true)}>Открыть сменное задание</button>
    </section>

    {open&&<div className="modal-backdrop shift-task-backdrop">
      <div className="shift-task-modal">
        <div className="shift-task-modal-head">
          <div>
            <span>СМЕННОЕ ЗАДАНИЕ</span>
            <h2>{selectedRun.erp_task_id||selectedRun.order_no||"Производственное задание"}</h2>
          </div>
          <button className="modal-close" onClick={()=>setOpen(false)}>×</button>
        </div>

        <div className="shift-task-sheet">
          <div className="shift-task-topline">
            <div><b>СМЕННОЕ ЗАДАНИЕ ЦЕХ № 2</b></div>
            <div><span>Дата:</span><b>{context?.shift?.business_date||""} {shiftLabel}</b></div>
          </div>
          <div className="shift-task-note">К сменному заданию крепить все этикетки и бирки с рулона, чек-листы</div>
          <div className="shift-task-machine"><span>Наименование станка:</span><b>{selectedRun.equipment_code} · {selectedRun.equipment_name||""}</b></div>

          <div className="shift-task-job-title">{selectedRun.product_name}</div>

          <div className="shift-task-grid shift-task-grid-head">
            <div><span>№ заказа</span><b>{selectedRun.order_no||"—"}</b></div>
            <div><span>Артикул</span><b>{selectedRun.product_article||selectedRun.product_code||"—"}</b></div>
            <div><span>Клиент</span><b>{selectedRun.erp_customer||"—"}</b></div>
            <div><span>Тех. карта / спецификация</span><b>{selectedRun.erp_tech_card||"—"}</b></div>
          </div>

          <div className="shift-task-grid shift-task-plan">
            <div><span>План на смену, шт</span><b>{nf.format(plan)}</b></div>
            <div><span>План, кг</span><b>{selectedRun.erp_plan_kg ? nf.format(selectedRun.erp_plan_kg) : "—"}</b></div>
            <div><span>Нормативное время, ч</span><b>{selectedRun.erp_norm_hours ? nf.format(selectedRun.erp_norm_hours) : "—"}</b></div>
            <div><span>Фасовка, шт/упак.</span><b>{selectedRun.erp_pcs_per_box ? nf.format(selectedRun.erp_pcs_per_box) : "—"}</b></div>
          </div>

          <div className="shift-task-report-title">Отчет по заданию — заполняет учетчик</div>
          <div className="shift-task-input-grid">
            <label><span>По счетчику, шт</span>{input("counter_qty","0","number")}</label>
            <label><span>Брак, шт</span>{input("defect_qty","0","number")}</label>
            <label><span>Брак, кг (тех. отходы)</span>{input("defect_kg","0","number")}</label>
            <label><span>Начало работы</span>{input("work_start","","time")}</label>
            <label><span>Конец работы</span>{input("work_end","","time")}</label>
            <label><span>Брак ОТК, шт</span>{input("qc_defect_qty","0","number")}</label>
            <label><span>Фактически, шт</span>{input("actual_qty","0","number")}</label>
            <label><span>Факт, коробов</span>{input("actual_boxes","0","number")}</label>
            <label><span>Факт, паллет</span>{input("actual_pallets","0","number")}</label>
          </div>

          <label className="shift-task-wide-input">
            <span>Примечание (простои, переналадка, брак качества и др.)</span>
            <textarea value={report.note??""} onChange={e=>setField("note",e.target.value)} />
          </label>

          <div className="shift-task-section-title">Материалы по заданию 1С:ERP</div>
          <div className="table-wrap shift-task-materials">
            <table>
              <thead><tr><th>Артикул</th><th>Материал</th><th>Склад</th><th>Ед.</th><th>Норматив</th></tr></thead>
              <tbody>
                {materials.map((item,index)=><tr key={index}>
                  <td>{item.article||"—"}</td>
                  <td>{item.name||"—"}</td>
                  <td>{item.warehouse||"—"}</td>
                  <td>{item.unit||"—"}</td>
                  <td>{item.normative||"—"}</td>
                </tr>)}
                {materials.length===0&&<tr><td colSpan="5"><div className="empty-state">Материалы появятся после повторной загрузки печатного задания из 1С:ERP.</div></td></tr>}
              </tbody>
            </table>
          </div>

          <div className="shift-task-section-title">Расход бумаги ролевой за смену</div>
          <div className="shift-task-input-grid shift-task-material-inputs">
            <label><span>Номер роля</span>{input("paper_roll_no")}</label>
            <label><span>Производитель</span>{input("paper_manufacturer")}</label>
            <label><span>Вес роля, кг</span>{input("paper_roll_weight","","number")}</label>
            <label><span>Марка</span>{input("paper_brand")}</label>
            <label><span>Граммаж</span>{input("paper_grammage","","number")}</label>
            <label><span>Формат</span>{input("paper_format")}</label>
            <label><span>Остаток, кг</span>{input("paper_remainder_kg","","number")}</label>
            <label><span>Остаток, радиус рулона</span>{input("paper_remainder_radius")}</label>
          </div>

          <div className="shift-task-supplies-grid">
            <div>
              <div className="shift-task-section-title">Расход клея за смену</div>
              <label><span>Производитель / наименование</span>{input("glue_name")}</label>
              <label><span>№ партии</span>{input("glue_batch")}</label>
              <label><span>Марка</span>{input("glue_brand")}</label>
              <label><span>Вес, кг</span>{input("glue_weight","","number")}</label>
            </div>
            <div>
              <div className="shift-task-section-title">Расход шпагата за смену</div>
              <label><span>Цвет</span>{input("twine_color")}</label>
              <label><span>Дата производства</span>{input("twine_date","","date")}</label>
              <label><span>Вес, кг</span>{input("twine_weight","","number")}</label>
            </div>
            <div>
              <div className="shift-task-section-title">Расход ленты для плоской ручки</div>
              <label><span>Цвет</span>{input("flat_tape_color")}</label>
              <label><span>Дата производства</span>{input("flat_tape_date","","date")}</label>
              <label><span>Вес, кг</span>{input("flat_tape_weight","","number")}</label>
            </div>
          </div>

          <div className="shift-task-supplies-grid shift-task-supplies-two">
            <div>
              <div className="shift-task-section-title">Расход ленты для усилителя</div>
              <label><span>Цвет</span>{input("reinforcement_tape_color")}</label>
              <label><span>Дата производства</span>{input("reinforcement_tape_date","","date")}</label>
              <label><span>Вес, кг</span>{input("reinforcement_tape_weight","","number")}</label>
            </div>
            <div>
              <div className="shift-task-section-title">Дополнительное примечание</div>
              <label><span>Комментарий</span>{input("general_note")}</label>
            </div>
          </div>

          <div className="shift-task-checks">
            <label><input type="checkbox" checked={Boolean(report.checklist_control)} onChange={e=>setField("checklist_control",e.target.checked)}/> Чек-лист контроля заполнен и подписан</label>
            <label><input type="checkbox" checked={Boolean(report.checklist_handover)} onChange={e=>setField("checklist_handover",e.target.checked)}/> Чек-лист передачи смены заполнен и подписан</label>
            <label><input type="checkbox" checked={Boolean(report.safety_ok)} onChange={e=>setField("safety_ok",e.target.checked)}/> Предохранительные устройства исправны</label>
          </div>

          <div className="shift-task-section-title">Ответственные за смену</div>
          <div className="shift-task-signatures">
            <label><span>Мастер — ФИО</span>{input("master_name")}<em><input type="checkbox" checked={Boolean(report.master_signed)} onChange={e=>setField("master_signed",e.target.checked)}/> подтверждено</em></label>
            <label><span>Оператор — ФИО</span>{input("operator_name")}<em><input type="checkbox" checked={Boolean(report.operator_signed)} onChange={e=>setField("operator_signed",e.target.checked)}/> подтверждено</em></label>
            <label><span>Бригадир — ФИО</span>{input("brigadier_name")}<em><input type="checkbox" checked={Boolean(report.brigadier_signed)} onChange={e=>setField("brigadier_signed",e.target.checked)}/> подтверждено</em></label>
            <label><span>Упаковщик — ФИО</span>{input("packer_name")}<em><input type="checkbox" checked={Boolean(report.packer_signed)} onChange={e=>setField("packer_signed",e.target.checked)}/> подтверждено</em></label>
          </div>
        </div>

        <div className="shift-task-actions">
          <div>{notice&&<div className="notice">{notice}</div>}</div>
          <div className="action-row">
            <button className="btn ghost" onClick={()=>setOpen(false)}>Закрыть</button>
            <button className="btn primary" disabled={busy} onClick={save}>{busy?"Сохранение…":"Сохранить сменное задание"}</button>
          </div>
        </div>
      </div>
    </div>}
  </>;
}

function AccountantForm({ selectedRun, onRefresh }) {
  const [ticket, setTicket] = useState("");
  const [packages, setPackages] = useState("");
  const [perPackage, setPerPackage] = useState("");
  const [comment, setComment] = useState("");
  const [notice, setNotice] = useState("");

  const total = Number(packages || 0) * Number(perPackage || 0);

  const save = async () => {
    await api.accountantControl({
      production_run_id: selectedRun.id,
      packages_qty: Number(packages),
      qty_per_package: Number(perPackage),
      observed_at: null,
      ticket_no: ticket || null,
      comment: comment || null,
      client_event_id: uuid()
    });
    setTicket("");
    setPackages("");
    setPerPackage("");
    setComment("");
    setNotice("Запись учетчика сохранена");
    await onRefresh();
  };

  return <section className="card panel workspace-form-card">
    <h2>Ввод по талону</h2>
    <label className="form-label">Талон</label>
    <input className="form-control" value={ticket} onChange={e=>setTicket(e.target.value)} />
    <div className="workspace-two-fields">
      <label><span>Упаковок</span><input className="form-control" type="number" min="0" value={packages} onChange={e=>setPackages(e.target.value)} /></label>
      <label><span>Шт. в упаковке</span><input className="form-control" type="number" min="0" value={perPackage} onChange={e=>setPerPackage(e.target.value)} /></label>
    </div>
    <div className="workspace-total"><span>Итого, шт.</span><b>{nf.format(total)}</b></div>
    <label className="form-label">Комментарий</label>
    <input className="form-control" value={comment} onChange={e=>setComment(e.target.value)} />
    <button className="btn primary workspace-save" disabled={!selectedRun || total<=0} onClick={save}>Сохранить запись</button>
    {notice && <div className="notice">{notice}</div>}
  </section>;
}

function ComparePanel({ kind, run }) {
  if (!run) return <section className="card panel"><div className="empty-state">Выберите задание.</div></section>;

  const rows = kind === "qc"
    ? [["Оператор — брак", run.operator_defect_qty], ["ОТК — подтверждено", run.qc_defect_qty], ["Расхождение", run.qc_defect_qty-run.operator_defect_qty]]
    : kind === "warehouse"
      ? [["Выпуск оператора", run.output_qty], ["После ОТК", Math.max(run.output_qty-run.qc_defect_qty,0)], ["Принято на склад", run.warehouse_qty], ["Расхождение", Math.max(run.output_qty-run.qc_defect_qty,0)-run.warehouse_qty]]
      : kind === "accountant"
        ? [["Оператор", run.output_qty], ["ОТК — годное", Math.max(run.output_qty-run.qc_defect_qty,0)], ["Учетчик", run.accounting_qty], ["Склад", run.warehouse_qty]]
        : [["План", run.planned_qty], ["Выпуск", run.output_qty], ["Брак оператора", run.operator_defect_qty], ["Брак ОТК", run.qc_defect_qty]];

  return <section className="card panel">
    <div className="panel-head"><h2>Сверка данных</h2><span>на текущий момент</span></div>
    <div className="workspace-compare">
      {rows.map(([label,value])=><div key={label}><span>{label}</span><b>{nf.format(value || 0)}</b></div>)}
    </div>
  </section>;
}

function HistoryTable({ rows = [] }) {
  return <section className="card panel workspace-history">
    <div className="panel-head"><h2>История записей за смену</h2><span>{rows.length} строк</span></div>
    <div className="table-wrap">
      <table>
        <thead><tr><th>Время</th><th>Тип</th><th>Линия</th><th>Заказ</th><th>Продукция</th><th>Количество</th><th>Комментарий / талон</th></tr></thead>
        <tbody>
          {rows.map((row) => <tr key={row.id}>
            <td>{new Date(row.event_at).toLocaleTimeString("ru-RU",{hour:"2-digit",minute:"2-digit"})}</td>
            <td>{row.event_type}</td>
            <td>{row.equipment_code || "—"}</td>
            <td>{row.order_no || "—"}</td>
            <td>{row.product_name || "—"}</td>
            <td>{nf.format(row.quantity || 0)}</td>
            <td>{row.comment || "—"}</td>
          </tr>)}
          {rows.length === 0 && <tr><td colSpan="7"><div className="empty-state">Записей за смену пока нет.</div></td></tr>}
        </tbody>
      </table>
    </div>
  </section>;
}

export default function RoleWorkspace({ kind, businessDate, shiftCode }) {
  const [context, setContext] = useState(null);
  const [selectedRunId, setSelectedRunId] = useState(null);

  const refresh = async () => {
    const result = await api.workspaceContext(kind, businessDate, shiftCode);
    setContext(result);
    setSelectedRunId(current => current || result.runs?.[0]?.id || null);
  };

  useEffect(() => { refresh(); }, [kind, businessDate, shiftCode]);

  const selectedRun = useMemo(
    () => context?.runs?.find(run => run.id === selectedRunId) || null,
    [context, selectedRunId]
  );

  if (!context) return <div className="card panel">Загрузка рабочего кабинета…</div>;

  return <>
    <div className="workspace-title">
      <div><h2>{labels[kind].title}</h2><p>{labels[kind].subtitle}</p></div>
    </div>
    <WorkspaceHeader context={context} />

    <div className="workspace-layout">
      <section className="card panel workspace-runs">
        <div className="panel-head"><h2>Текущие задания</h2><span>{context.runs.length}</span></div>
        <div className="workspace-run-list">
          {context.runs.map(run=><RunCard key={run.id} run={run} selected={run.id===selectedRunId} onClick={()=>setSelectedRunId(run.id)} />)}
          {context.runs.length===0 && <div className="empty-state">На выбранную смену производственные запуски пока не созданы.</div>}
        </div>
      </section>

      <div>
        {kind==="operator" && <>
          <ShiftAssignmentForm context={context} selectedRun={selectedRun} onRefresh={refresh} />
          <OperatorForm context={context} selectedRun={selectedRun} onRefresh={refresh} />
        </>}
        {kind==="qc" && <QCForm context={context} selectedRun={selectedRun} onRefresh={refresh} />}
        {kind==="warehouse" && <WarehouseForm selectedRun={selectedRun} onRefresh={refresh} />}
        {kind==="accountant" && <AccountantForm selectedRun={selectedRun} onRefresh={refresh} />}
        <ComparePanel kind={kind} run={selectedRun} />
      </div>
    </div>

    <HistoryTable rows={context.recent || []} />
  </>;
}
