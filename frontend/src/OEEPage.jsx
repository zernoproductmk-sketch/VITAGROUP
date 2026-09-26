import { useEffect, useMemo, useState } from "react";
import { api } from "./api";

const nf = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 });

const fmt = (value) => (
  value === null || value === undefined ? "—" : nf.format(Number(value))
);

const pct = (value) => (
  value === null || value === undefined ? "—" : `${fmt(value)}%`
);

function Score({ label, value }) {
  return <div className="oee-score">
    <span>{label}</span>
    <b>{pct(value)}</b>
  </div>;
}

function RunDetail({ runId, onClose }) {
  const [detail, setDetail] = useState(null);

  useEffect(() => {
    setDetail(null);
    api.oeeRunDetail(runId).then(setDetail);
  }, [runId]);

  if (!detail) {
    return <div className="modal-backdrop" onMouseDown={onClose}>
      <div className="modal-card oee-modal" onMouseDown={e => e.stopPropagation()}>
        <div className="loading-inline">Загрузка расчета…</div>
      </div>
    </div>;
  }

  const r = detail.run;
  const f = detail.formula;
  const e = detail.events;

  return <div className="modal-backdrop" onMouseDown={onClose}>
    <div className="modal-card oee-modal" onMouseDown={event => event.stopPropagation()}>
      <div className="modal-head">
        <div>
          <small>{r.equipment_code} · {r.order_no || "без заказа"}</small>
          <h2>{r.product_name}</h2>
        </div>
        <button className="modal-close" onClick={onClose}>×</button>
      </div>

      {detail.warnings?.map((warning, index) =>
        <div className="data-warning" key={index}>{warning}</div>
      )}

      <div className="oee-score-grid">
        <Score label="Availability" value={r.availability} />
        <Score label="Performance" value={r.performance} />
        <Score label="Quality" value={r.quality} />
        <Score label="Выполнение плана" value={r.plan_fulfillment} />
        <Score label="OEE" value={r.oee} />
      </div>

      <div className="oee-detail-grid">
        <section className="detail-block">
          <h3>Время</h3>
          <div className="detail-line"><span>Плановое время</span><b>{fmt(r.planned_minutes)} мин</b></div>
          <div className="detail-line"><span>Простой</span><b>{fmt(r.downtime_minutes)} мин</b></div>
          <div className="detail-line"><span>Время работы</span><b>{fmt(r.runtime_minutes)} мин</b></div>
        </section>

        <section className="detail-block">
          <h3>Выпуск</h3>
          <div className="detail-line"><span>План</span><b>{fmt(r.planned_qty)} шт.</b></div>
          <div className="detail-line"><span>Факт оператора (годная продукция)</span><b>{fmt(r.output_qty)} шт.</b></div>
          <div className="detail-line"><span>Всего произведено до брака</span><b>{fmt(r.total_count_qty)} шт.</b></div>
          <div className="detail-line"><span>Годная продукция после ОТК</span><b>{fmt(r.good_qty)} шт.</b></div>
          <div className="detail-line"><span>Норматив</span><b>{fmt(r.ideal_rate_per_hour)} шт./ч</b></div>
          <div className="detail-line"><span>Теоретический выпуск</span><b>{fmt(r.theoretical_qty)} шт.</b></div>
        </section>

        <section className="detail-block">
          <h3>Качество и сверка</h3>
          <div className="detail-line"><span>Брак оператора</span><b>{fmt(r.operator_defect_qty)}</b></div>
          <div className="detail-line"><span>Брак ОТК</span><b>{fmt(r.qc_defect_qty)}</b></div>
          <div className="detail-line"><span>Склад</span><b>{fmt(r.warehouse_qty)}</b></div>
          <div className="detail-line"><span>Факт 1С:ERP</span><b>{fmt(r.erp_qty)}</b></div>
        </section>
      </div>

      <section className="formula-card">
        <h3>Формула расчета</h3>
        <div className="formula-row">
          <b>Availability</b>
          <span>{fmt(f.availability.numerator)} / {fmt(f.availability.denominator)} = {pct(f.availability.result)}</span>
        </div>
        <div className="formula-row">
          <b>Performance</b>
          <span>{fmt(f.performance.numerator)} / {fmt(f.performance.denominator)} = {pct(f.performance.result)}</span>
        </div>
        <div className="formula-row">
          <b>Quality</b>
          <span>{fmt(f.quality.numerator)} / {fmt(f.quality.denominator)} = {pct(f.quality.result)}</span>
        </div>
        <div className="formula-row">
          <b>Выполнение плана по годной продукции</b>
          <span>{fmt(f.plan_fulfillment.numerator)} / {fmt(f.plan_fulfillment.denominator)} = {pct(f.plan_fulfillment.result)}</span>
        </div>
        <div className="formula-row total">
          <b>OEE</b>
          <span>{pct(f.oee.availability)} × {pct(f.oee.performance)} × {pct(f.oee.quality)} = {pct(f.oee.result)}</span>
        </div>
      </section>

      <section className="event-section">
        <h3>Простои</h3>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Начало</th><th>Окончание</th><th>Причина</th><th>Минут</th><th>В OEE</th></tr></thead>
            <tbody>
              {e.downtime.map((item, index) => <tr key={item.id || index}>
                <td>{item.started_at ? new Date(item.started_at).toLocaleTimeString("ru-RU", {hour:"2-digit", minute:"2-digit"}) : "—"}</td>
                <td>{item.ended_at ? new Date(item.ended_at).toLocaleTimeString("ru-RU", {hour:"2-digit", minute:"2-digit"}) : "идет"}</td>
                <td>{item.reason}</td>
                <td>{fmt(item.overlap_minutes)}</td>
                <td>{item.counted_in_availability ? "Да" : "Нет"}</td>
              </tr>)}
              {e.downtime.length === 0 && <tr><td colSpan="5">Простоев нет</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section className="event-section">
        <h3>Первичные события</h3>
        <div className="event-counters">
          <div><span>Выпуск</span><b>{e.output.length}</b></div>
          <div><span>Брак</span><b>{e.defects.length}</b></div>
          <div><span>Склад</span><b>{e.warehouse.length}</b></div>
          <div><span>ERP</span><b>{e.erp.length}</b></div>
        </div>
      </section>
    </div>
  </div>;
}

export default function OEEPage({ businessDate, shiftCode }) {
  const [rows, setRows] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    api.oeeRuns(businessDate, shiftCode).then(result => setRows(result.rows || []));
  }, [businessDate, shiftCode]);

  const filtered = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter(row =>
      [
        row.equipment_code,
        row.equipment_name,
        row.order_no,
        row.product_article,
        row.product_name
      ].some(value => String(value || "").toLowerCase().includes(needle))
    );
  }, [rows, filter]);

  return <>
    <div className="integration-toolbar card">
      <div>
        <h2>OEE по линиям и заказам</h2>
        <p>Каждая строка — отдельный производственный запуск</p>
      </div>
      <input
        className="form-control oee-search"
        placeholder="Поиск по линии, заказу, артикулу"
        value={filter}
        onChange={e => setFilter(e.target.value)}
      />
    </div>

    <section className="card panel">
      <div className="panel-head">
        <h2>Производственные запуски</h2>
        <span>{filtered.length} строк</span>
      </div>
      <div className="table-wrap">
        <table className="oee-table">
          <thead>
            <tr>
              <th>Линия</th>
              <th>Заказ</th>
              <th>Артикул</th>
              <th>План</th>
              <th>Факт</th>
              <th>Простой, мин</th>
              <th>A</th>
              <th>P</th>
              <th>Q</th>
              <th>План, %</th>
              <th>OEE</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(row => <tr key={row.id}>
              <td><b>{row.equipment_code}</b><small>{row.equipment_name}</small></td>
              <td>{row.order_no || "—"}</td>
              <td><b>{row.product_article || row.product_code}</b><small>{row.product_name}</small></td>
              <td>{fmt(row.planned_qty)}</td>
              <td>{fmt(row.output_qty)}</td>
              <td>{fmt(row.downtime_minutes)}</td>
              <td>{pct(row.availability)}</td>
              <td>{pct(row.performance)}</td>
              <td>{pct(row.quality)}</td>
              <td>{pct(row.plan_fulfillment)}</td>
              <td><b>{pct(row.oee)}</b></td>
              <td><button className="btn secondary" onClick={() => setSelectedRunId(row.id)}>Расчет</button></td>
            </tr>)}
            {filtered.length === 0 && <tr><td colSpan="12"><div className="empty-state">Для выбранной смены запусков пока нет.</div></td></tr>}
          </tbody>
        </table>
      </div>
    </section>

    {selectedRunId && <RunDetail runId={selectedRunId} onClose={() => setSelectedRunId(null)} />}
  </>;
}
