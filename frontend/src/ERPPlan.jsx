import { useEffect, useState } from "react";
import { api } from "./api";

const fmt = (value, digits = 0) => {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits }).format(n);
};

function Badge({ value }) {
  const status = String(value || "").toUpperCase();
  const cls = status === "RUN_CREATED" || status === "COMPLETED"
    ? "success"
    : status === "ERROR" || status === "FAILED"
      ? "danger"
      : "warning";
  return <span className={`status ${cls}`}>{value || "НЕ ОБРАБОТАНО"}</span>;
}

export default function ERPPlan() {
  const [summary, setSummary] = useState(null);
  const [rows, setRows] = useState([]);
  const [yandex, setYandex] = useState(null);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [loadError, setLoadError] = useState("");

  const refresh = async () => {
    setLoadError("");
    try {
      const [s, r, y] = await Promise.all([
        api.erpPlanSummary(),
        api.erpPlanRows(),
        api.yandexStatus()
      ]);
      setSummary(s);
      setRows(r.rows || []);
      setYandex(y);
    } catch (error) {
      setLoadError(error.message || "Backend временно недоступен");
    }
  };

  useEffect(() => { refresh(); }, []);

  const run = async (label, action) => {
    setBusy(label);
    setNotice("");
    const result = await action();
    setNotice(
      result?.message ||
      (result?.file_name ? `Файл ${result.file_name}: операция выполнена` : `Операция «${label}» выполнена`)
    );
    await refresh();
    setBusy("");
  };

  if (!summary && loadError) return <div className="card panel">
    <h2>План ERP временно недоступен</h2>
    <p className="muted">{loadError}</p>
    <button className="btn secondary" onClick={refresh}>Повторить</button>
  </div>;

  if (!summary) return <div className="card panel">Загрузка плана ERP…</div>;

  const counts = summary.counts || {};
  const last = summary.last_import;

  return <>
    <div className="integration-toolbar card">
      <div>
        <h2>Производственный план 1С / ERP</h2>
        <p>Яндекс Диск: все файлы папки → ERP staging → заказы → производственные запуски</p>
      </div>
      <div className="action-row">
        <button className="btn ghost" disabled={!!busy} onClick={() => run("Проверка файла", api.yandexPreview)}>Проверить файл</button>
        <button className="btn secondary" disabled={!!busy} onClick={() => run("Импорт папки", api.yandexImport)}>Импортировать все задания из папки</button>
        <button className="btn primary" disabled={!!busy} onClick={() => run("Создание заказов", api.erpPlanPromote)}>Создать заказы / запуски</button>
      </div>
    </div>

    {notice && <div className="notice">{notice}</div>}

    <div className="erp-kpis">
      <div className="card mini-kpi"><span>Строк плана</span><b>{fmt(counts.total)}</b></div>
      <div className="card mini-kpi"><span>Запусков создано</span><b>{fmt(counts.runs)}</b></div>
      <div className="card mini-kpi"><span>Только заказы</span><b>{fmt(counts.orders_only)}</b></div>
      <div className="card mini-kpi"><span>Требуют уточнения</span><b>{fmt(counts.partial)}</b></div>
      <div className="card mini-kpi"><span>Ошибок</span><b>{fmt(counts.errors)}</b></div>
    </div>

    <div className="two-col erp-meta-grid">
      <section className="card panel">
        <div className="panel-head"><h2>Источник</h2><Badge value={yandex?.configured ? "READY" : "НЕ НАСТРОЕН"} /></div>
        <div className="meta-list">
          <div><span>Источник</span><b>Яндекс Диск</b></div>
          <div><span>Ссылка настроена</span><b>{yandex?.configured ? "Да" : "Нет"}</b></div>
          <div><span>Путь внутри папки</span><b>{yandex?.resource_path_configured ? "Настроен" : "Не требуется / не задан"}</b></div>
        </div>
      </section>

      <section className="card panel">
        <div className="panel-head"><h2>Последний импорт</h2>{last && <Badge value={last.status} />}</div>
        <div className="meta-list">
          <div><span>Файл</span><b>{last?.source_file_name || "Пока не импортировался"}</b></div>
          <div><span>Лист</span><b>{last?.source_sheet || "—"}</b></div>
          <div><span>Прочитано</span><b>{fmt(last?.rows_read)}</b></div>
          <div><span>Применено</span><b>{fmt(last?.rows_applied)}</b></div>
        </div>
      </section>
    </div>

    <section className="card panel">
      <div className="panel-head"><h2>Задания и производственные запуски</h2><span>{rows.length} строк</span></div>
      <div className="table-wrap">
        <table className="erp-plan-table">
          <thead>
            <tr>
              <th>Дата</th>
              <th>Задание</th>
              <th>Заказ</th>
              <th>Артикул</th>
              <th>Наименование</th>
              <th>План, шт.</th>
              <th>Оборудование 1С</th>
              <th>Линия</th>
              <th>Смена</th>
              <th>Норма, шт./ч</th>
              <th>Статус</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => <tr key={row.id || index}>
              <td>{row.business_date || "—"}</td>
              <td>{row.task_id || "—"}</td>
              <td>{row.order_no || "—"}</td>
              <td>{row.article || "—"}</td>
              <td className="wide-cell">{row.resolved_product_name || row.product_name || "—"}</td>
              <td>{fmt(row.plan_qty_pcs)}</td>
              <td>{row.route_equipment_hint || row.equipment_code || "—"}</td>
              <td>{row.resolved_equipment_code || "—"}</td>
              <td>{row.shift_code || "Определится по факту"}</td>
              <td>{fmt(row.ideal_rate_per_hour, 2)}</td>
              <td><Badge value={row.promotion_status} /></td>
            </tr>)}
            {rows.length === 0 && <tr><td colSpan="11"><div className="empty-state">План еще не импортирован. После запуска сервера нажмите «Импортировать с Яндекс Диска».</div></td></tr>}
          </tbody>
        </table>
      </div>
      <div className="admin-note">
        Смена определяется по полю «Дата выполнения» из 1С: 09:00–20:59 — ДЕНЬ, 21:00–23:59 — НОЧЬ этой даты, 00:00–08:59 — НОЧЬ предыдущего дня.
      </div>
    </section>
  </>;
}
