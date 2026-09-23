import { useEffect, useMemo, useState } from "react";
import { api } from "./api";

const nf = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 3 });
const money = new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", maximumFractionDigits: 2 });

const statusLabels = {
  READY: "Готово",
  NEEDS_BASIS: "Выберите базу",
  MISSING_EMPLOYEE: "Не найден сотрудник",
  NEEDS_ALLOCATION: "Нужно распределение",
  MISSING_PRODUCT_ATTRIBUTES: "Нужны признаки продукции",
  MISSING_RATE: "Тариф не найден",
  AMBIGUOUS_RATE: "Несколько тарифов"
};

function statusClass(status) {
  return status === "READY" ? "success" : status === "MISSING_RATE" ? "danger" : "warning";
}

function defaultPeriod() {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  return {
    from: `${yyyy}-${mm}-01`,
    to: `${yyyy}-${mm}-${dd}`
  };
}

function ProductAttributesModal({ row, onClose, onSaved }) {
  const [options, setOptions] = useState(null);
  const [productType, setProductType] = useState(row.product_type || "");
  const [printFlag, setPrintFlag] = useState(row.print_flag || "");
  const [tariffGroup, setTariffGroup] = useState(row.tariff_group || "");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.payrollRateOptions(row.equipment_id, row.business_date).then(setOptions);
  }, [row.equipment_id, row.business_date]);

  const save = async () => {
    setBusy(true);
    await api.payrollSaveProductAttributes(row.product_id, {
      product_type: productType || null,
      print_flag: printFlag || null,
      tariff_group: tariffGroup || null
    });
    await onSaved();
    setBusy(false);
    onClose();
  };

  return <div className="modal-backdrop" onMouseDown={onClose}>
    <div className="modal-card" onMouseDown={e => e.stopPropagation()}>
      <div className="modal-head">
        <div><small>{row.equipment_code} · {row.order_no || "без заказа"}</small><h2>Тарифные признаки продукции</h2></div>
        <button className="modal-close" onClick={onClose}>×</button>
      </div>

      <div className="event-summary">
        <div><span>Артикул</span><b>{row.product_article || row.product_code}</b></div>
        <div><span>Продукция</span><b>{row.product_name}</b></div>
        <div><span>Линия</span><b>{row.equipment_code}</b></div>
      </div>

      <label className="form-label">Вид продукции</label>
      <select className="form-control" value={productType} onChange={e => setProductType(e.target.value)}>
        <option value="">Не выбрано</option>
        {(options?.product_types || []).map(v => <option key={v}>{v}</option>)}
      </select>

      <label className="form-label">Признак печати</label>
      <select className="form-control" value={printFlag} onChange={e => setPrintFlag(e.target.value)}>
        <option value="">Не выбрано</option>
        {(options?.print_flags || []).map(v => <option key={v}>{v}</option>)}
      </select>

      <label className="form-label">Группа тарифа</label>
      <select className="form-control" value={tariffGroup} onChange={e => setTariffGroup(e.target.value)}>
        <option value="">Не выбрано</option>
        {(options?.tariff_groups || []).map(v => <option key={v}>{v}</option>)}
      </select>

      <div className="modal-actions">
        <button className="btn ghost" onClick={onClose}>Отмена</button>
        <button className="btn primary" disabled={busy} onClick={save}>Сохранить признаки</button>
      </div>
    </div>
  </div>;
}

function AllocationModal({ rows, onClose, onSaved }) {
  const initial = rows.map(row => ({
    employee_id: row.employee_id,
    name: row.employee_name,
    personnel_number: row.personnel_number,
    allocation_factor: row.allocation_factor || 0
  }));
  const [items, setItems] = useState(initial);
  const [busy, setBusy] = useState(false);

  const setFactor = (id, value) => {
    setItems(current => current.map(item =>
      item.employee_id === id ? { ...item, allocation_factor: Number(value) / 100 } : item
    ));
  };

  const total = items.reduce((sum, item) => sum + Number(item.allocation_factor || 0), 0);

  const save = async () => {
    setBusy(true);
    await api.payrollSaveAllocation(rows[0].production_run_id, {
      entries: items.map(item => ({
        employee_id: item.employee_id,
        allocation_factor: Number(item.allocation_factor)
      }))
    });
    await onSaved();
    setBusy(false);
    onClose();
  };

  return <div className="modal-backdrop" onMouseDown={onClose}>
    <div className="modal-card" onMouseDown={e => e.stopPropagation()}>
      <div className="modal-head">
        <div><small>{rows[0].equipment_code} · {rows[0].order_no || "без заказа"}</small><h2>Распределение бригадной выработки</h2></div>
        <button className="modal-close" onClick={onClose}>×</button>
      </div>

      <div className="allocation-list">
        {items.map(item => <div className="allocation-row" key={item.employee_id}>
          <div><b>{item.name}</b><span>Таб. № {item.personnel_number}</span></div>
          <div className="allocation-input">
            <input type="number" min="0" max="100" step="0.1" value={Math.round(item.allocation_factor * 10000) / 100} onChange={e => setFactor(item.employee_id, e.target.value)} />
            <span>%</span>
          </div>
        </div>)}
      </div>

      <div className={`allocation-total ${Math.abs(total - 1) < 0.0001 ? "ok" : "bad"}`}>
        Итого: {Math.round(total * 10000) / 100}%
      </div>

      <div className="modal-actions">
        <button className="btn ghost" onClick={onClose}>Отмена</button>
        <button className="btn primary" disabled={busy || Math.abs(total - 1) >= 0.0001} onClick={save}>Сохранить распределение</button>
      </div>
    </div>
  </div>;
}

export default function PayrollPage({ readOnly = false }) {
  const defaults = defaultPeriod();
  const [dateFrom, setDateFrom] = useState(defaults.from);
  const [dateTo, setDateTo] = useState(defaults.to);
  const [basis, setBasis] = useState("");
  const [preview, setPreview] = useState(null);
  const [periods, setPeriods] = useState([]);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [attributeRow, setAttributeRow] = useState(null);
  const [allocationRows, setAllocationRows] = useState(null);

  const loadPeriods = async () => {
    const result = await api.payrollPeriods();
    setPeriods(result.rows || []);
  };

  const loadPreview = async () => {
    setBusy("preview");
    const result = await api.payrollPreview(dateFrom, dateTo, basis || null);
    setPreview(result);
    setBusy("");
  };

  useEffect(() => { loadPeriods(); }, []);

  const groupedByRun = useMemo(() => {
    const groups = {};
    for (const row of preview?.rows || []) {
      groups[row.production_run_id] ||= [];
      groups[row.production_run_id].push(row);
    }
    return groups;
  }, [preview]);

  const createAndCalculate = async () => {
    setBusy("calculate");
    setNotice("");
    const period = await api.payrollCreatePeriod({
      date_from: dateFrom,
      date_to: dateTo,
      quantity_basis: basis || null
    });
    if (!period?.id) {
      setNotice("Не удалось создать расчетный период.");
      setBusy("");
      return;
    }
    const result = await api.payrollCalculatePeriod(period.id);
    if (result.status === "BLOCKED") {
      setNotice("Расчет не зафиксирован: сначала устраните блокирующие строки.");
      setPreview(result);
    } else {
      setNotice("Расчет периода сформирован.");
      await loadPreview();
      await loadPeriods();
    }
    setBusy("");
  };

  const summary = preview?.summary || {};
  const rows = preview?.rows || [];

  return <>
    <div className="integration-toolbar card payroll-toolbar">
      <div>
        <h2>Расчет сдельной заработной платы</h2>
        <p>Подтвержденная выработка × тариф × коэффициент участия</p>
      </div>
      <div className="payroll-controls">
        <label><span>С</span><input className="form-control" type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} /></label>
        <label><span>По</span><input className="form-control" type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} /></label>
        <label className="basis-control"><span>База начисления</span>
          <select className="form-control" value={basis} onChange={e => setBasis(e.target.value)}>
            <option value="">Не выбрана</option>
            <option value="OUTPUT">Выпуск оператора</option>
            <option value="QC_GOOD">Годная продукция после ОТК</option>
            <option value="WAREHOUSE">Принято складом</option>
            <option value="ERP">Факт ERP</option>
          </select>
        </label>
        <button className="btn secondary" disabled={!!busy} onClick={loadPreview}>Предварительный расчет</button>
        {!readOnly && <button className="btn primary" disabled={!!busy || !basis || (summary.blocked_rows || 0) > 0} onClick={createAndCalculate}>Зафиксировать расчет</button>}
      </div>
    </div>

    {notice && <div className="notice">{notice}</div>}

    {preview && <>
      <div className="payroll-kpis">
        <div className="card mini-kpi"><span>Запусков</span><b>{summary.runs || 0}</b></div>
        <div className="card mini-kpi"><span>Готовых строк</span><b>{summary.ready_rows || 0}</b></div>
        <div className="card mini-kpi"><span>Требуют настройки</span><b>{summary.blocked_rows || 0}</b></div>
        <div className="card mini-kpi"><span>Предварительных</span><b>{summary.preliminary_rows || 0}</b></div>
        <div className="card mini-kpi"><span>Сумма готовых</span><b>{money.format(summary.ready_amount || 0)}</b></div>
      </div>

      {!basis && <div className="data-warning"><b>Выберите базу начисления.</b> Система не будет сама решать, использовать выпуск оператора, ОТК, склад или ERP.</div>}

      <section className="card panel">
        <div className="panel-head"><h2>Строки расчета</h2><span>{rows.length} строк</span></div>
        <div className="table-wrap">
          <table className="payroll-table">
            <thead><tr>
              <th>Дата</th><th>Смена</th><th>Линия</th><th>Заказ</th><th>Сотрудник</th><th>Выработка</th><th>Коэф.</th><th>Тариф</th><th>Начислено</th><th>Статус</th><th></th>
            </tr></thead>
            <tbody>
              {rows.map((row, index) => <tr key={`${row.production_run_id}-${row.employee_id || index}`}>
                <td>{row.business_date}</td>
                <td>{row.shift_code}</td>
                <td>{row.equipment_code}</td>
                <td>{row.order_no || "—"}</td>
                <td><b>{row.employee_name || "—"}</b><small>{row.personnel_number ? `Таб. № ${row.personnel_number}` : ""}</small></td>
                <td>{row.source_quantity === null || row.source_quantity === undefined ? "—" : nf.format(row.source_quantity)}</td>
                <td>{nf.format((row.allocation_factor || 0) * 100)}%</td>
                <td>{row.rate === null || row.rate === undefined ? "—" : money.format(row.rate)}</td>
                <td><b>{row.amount === null || row.amount === undefined ? "—" : money.format(row.amount)}</b></td>
                <td><span className={`status ${statusClass(row.status)}`}>{statusLabels[row.status] || row.status}</span>{row.preliminary && <small>Запуск не VERIFIED</small>}</td>
                <td>
                  {!readOnly && row.status === "MISSING_PRODUCT_ATTRIBUTES" && <button className="btn secondary" onClick={() => setAttributeRow(row)}>Признаки</button>}
                  {!readOnly && row.status === "NEEDS_ALLOCATION" && <button className="btn secondary" onClick={() => setAllocationRows(groupedByRun[row.production_run_id])}>Распределить</button>}
                </td>
              </tr>)}
              {rows.length === 0 && <tr><td colSpan="11"><div className="empty-state">За выбранный период производственных запусков нет.</div></td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </>}

    <section className="card panel">
      <div className="panel-head"><h2>Расчетные периоды</h2><span>{periods.length}</span></div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Период</th><th>База</th><th>Статус</th><th>Строк</th><th>Сумма</th></tr></thead>
          <tbody>{periods.map(period => <tr key={period.id}>
            <td>{period.date_from} — {period.date_to}</td>
            <td>{period.quantity_basis || "—"}</td>
            <td><span className="status success">{period.status}</span></td>
            <td>{period.line_count}</td>
            <td>{money.format(Number(period.amount || 0))}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </section>

    {attributeRow && <ProductAttributesModal row={attributeRow} onClose={() => setAttributeRow(null)} onSaved={loadPreview} />}
    {allocationRows && <AllocationModal rows={allocationRows} onClose={() => setAllocationRows(null)} onSaved={loadPreview} />}
  </>;
}
