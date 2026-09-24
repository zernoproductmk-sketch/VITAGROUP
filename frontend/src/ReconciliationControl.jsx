import { useEffect, useMemo, useState } from "react";
import { api } from "./api";

const nf = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 });

const issueLabels = {
  PLAN_OPERATOR: "План → оператор",
  OPERATOR_QC: "Оператор → ОТК",
  QC_ACCOUNTANT: "ОТК → учетчик",
  ACCOUNTANT_WAREHOUSE: "Учетчик → склад",
  WAREHOUSE_ERP: "Склад → ERP"
};

function SeverityBadge({ value }) {
  const map = {
    OK: ["success", "СХОДИТСЯ"],
    WARNING: ["warning", "ОТКЛОНЕНИЕ"],
    CRITICAL: ["danger", "КРИТИЧНО"]
  };
  const [cls, label] = map[value] || ["warning", value || "—"];
  return <span className={`status ${cls}`}>{label}</span>;
}

function CaseModal({ row, reasons, canEdit, onClose, onSaved }) {
  const [status, setStatus] = useState(row.case?.status || "OPEN");
  const [reasonCode, setReasonCode] = useState(row.case?.reason_code || "");
  const [comment, setComment] = useState(row.case?.comment || "");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const save = async () => {
    setBusy(true);
    setMessage("");
    try {
      await api.saveReconciliationCase(row.production_run_id, {
        status,
        reason_code: reasonCode || null,
        comment: comment || null
      });
      await onSaved();
      setMessage("Комментарий сохранен");
    } catch (error) {
      setMessage(error.message || "Не удалось сохранить");
    } finally {
      setBusy(false);
    }
  };

  return <div className="modal-backdrop" onMouseDown={onClose}>
    <div className="modal-card reconciliation-modal" onMouseDown={e => e.stopPropagation()}>
      <div className="modal-head">
        <div>
          <small>{row.equipment_code} · {row.order_no || "без заказа"}</small>
          <h2>Разбор расхождения</h2>
        </div>
        <button className="modal-close" onClick={onClose}>×</button>
      </div>

      <div className="event-summary">
        <div><span>Участок цепочки</span><b>{issueLabels[row.primary_issue] || "—"}</b></div>
        <div><span>Артикул</span><b>{row.product_article}</b></div>
        <div><span>Продукция</span><b>{row.product_name}</b></div>
      </div>

      <div className="chain-card">
        <div><span>План 1С</span><b>{nf.format(row.plan_qty)}</b></div>
        <i>→</i>
        <div><span>Оператор</span><b>{nf.format(row.operator_qty)}</b></div>
        <i>→</i>
        <div><span>После ОТК</span><b>{nf.format(row.qc_good_qty)}</b></div>
        <i>→</i>
        <div><span>Учетчик</span><b>{nf.format(row.accounting_qty)}</b></div>
        <i>→</i>
        <div><span>Склад</span><b>{nf.format(row.warehouse_qty)}</b></div>
        <i>→</i>
        <div><span>ERP</span><b>{nf.format(row.erp_qty)}</b></div>
      </div>

      <label className="form-label">Причина</label>
      <select className="form-control" disabled={!canEdit} value={reasonCode} onChange={e => setReasonCode(e.target.value)}>
        <option value="">Не выбрано</option>
        {reasons.map(item => <option key={item.code} value={item.code}>{item.label}</option>)}
      </select>

      <label className="form-label">Комментарий мастера / ответственного</label>
      <textarea className="form-control recon-comment" disabled={!canEdit} value={comment} onChange={e => setComment(e.target.value)} placeholder="Что произошло и что сделано для устранения расхождения" />

      <label className="form-label">Статус</label>
      <select className="form-control" disabled={!canEdit} value={status} onChange={e => setStatus(e.target.value)}>
        <option value="OPEN">Открыто</option>
        <option value="EXPLAINED">Причина зафиксирована</option>
        <option value="RESOLVED">Закрыто</option>
      </select>

      {message && <div className="notice">{message}</div>}

      <div className="modal-actions">
        <button className="btn ghost" onClick={onClose}>Закрыть</button>
        {canEdit && <button className="btn primary" disabled={busy} onClick={save}>Сохранить</button>}
      </div>
    </div>
  </div>;
}

export default function ReconciliationControl({ businessDate, shiftCode, canEdit }) {
  const [data, setData] = useState(null);
  const [problemOnly, setProblemOnly] = useState(true);
  const [selected, setSelected] = useState(null);

  const refresh = async () => {
    setData(await api.reconciliationControl(businessDate, shiftCode));
  };

  useEffect(() => { refresh(); }, [businessDate, shiftCode]);

  const rows = useMemo(() => {
    if (!data) return [];
    return problemOnly ? data.rows.filter(row => row.severity !== "OK") : data.rows;
  }, [data, problemOnly]);

  if (!data) return <div className="card panel">Загрузка сверки смены…</div>;

  return <>
    <div className="integration-toolbar card">
      <div>
        <h2>Сквозная сверка смены</h2>
        <p>План 1С → оператор → ОТК → учетчик → склад → ERP</p>
      </div>
      <label className="problem-switch">
        <input type="checkbox" checked={problemOnly} onChange={e => setProblemOnly(e.target.checked)} />
        <span>Только проблемные</span>
      </label>
    </div>

    <div className="integration-kpis">
      <div className="card mini-kpi"><span>Запусков</span><b>{data.summary.runs}</b></div>
      <div className="card mini-kpi"><span>Сходится</span><b>{data.summary.ok}</b></div>
      <div className="card mini-kpi"><span>Отклонения</span><b>{data.summary.warning}</b></div>
      <div className="card mini-kpi"><span>Критично</span><b>{data.summary.critical}</b></div>
      <div className="card mini-kpi"><span>Открытых кейсов</span><b>{data.summary.open_cases}</b></div>
    </div>

    <section className="card panel">
      <div className="panel-head"><h2>Производственные запуски</h2><span>{rows.length} строк</span></div>
      <div className="table-wrap">
        <table className="reconciliation-control-table">
          <thead>
            <tr>
              <th>Линия</th><th>Заказ</th><th>Артикул</th><th>План</th><th>Оператор</th><th>ОТК</th><th>Учетчик</th><th>Склад</th><th>ERP</th><th>Проблемный участок</th><th>Статус</th><th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map(row => <tr key={row.production_run_id} className={row.severity === "CRITICAL" ? "critical-row" : ""}>
              <td><b>{row.equipment_code}</b></td>
              <td>{row.order_no || "—"}</td>
              <td><b>{row.product_article}</b><small>{row.product_name}</small></td>
              <td>{nf.format(row.plan_qty)}</td>
              <td>{nf.format(row.operator_qty)}</td>
              <td>{nf.format(row.qc_good_qty)}</td>
              <td>{nf.format(row.accounting_qty)}</td>
              <td>{nf.format(row.warehouse_qty)}</td>
              <td>{nf.format(row.erp_qty)}</td>
              <td>{issueLabels[row.primary_issue] || "—"}</td>
              <td>
                <SeverityBadge value={row.severity} />
                {row.case?.status && <small>{row.case.status}</small>}
              </td>
              <td><button className="btn secondary" onClick={() => setSelected(row)}>{row.case ? "Открыть" : "Разобрать"}</button></td>
            </tr>)}
            {rows.length === 0 && <tr><td colSpan="12"><div className="empty-state">Расхождений по выбранной смене нет.</div></td></tr>}
          </tbody>
        </table>
      </div>
    </section>

    {selected && <CaseModal
      row={selected}
      reasons={data.reason_options || []}
      canEdit={canEdit}
      onClose={() => setSelected(null)}
      onSaved={refresh}
    />}
  </>;
}
