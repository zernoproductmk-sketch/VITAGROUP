import { useEffect, useMemo, useState } from "react";
import { api } from "./api";

const statusMeta = {
  READY: { label: "ГОТОВО", cls: "success" },
  WARNING: { label: "ВНИМАНИЕ", cls: "warning" },
  BLOCKED: { label: "БЛОКИРУЕТ", cls: "danger" }
};

function ReadinessCard({ item, onNavigate }) {
  const meta = statusMeta[item.status] || statusMeta.WARNING;
  return <article className={`readiness-card ${item.status.toLowerCase()}`}>
    <div className="readiness-card-head">
      <h3>{item.title}</h3>
      <span className={`status ${meta.cls}`}>{meta.label}</span>
    </div>
    <p>{item.message}</p>
    <button className="btn ghost" onClick={() => onNavigate(item.target_section)}>
      Перейти
    </button>
  </article>;
}

function SummaryBlock({ title, ready, blockers, warnings, note }) {
  return <section className={`card readiness-summary ${ready ? "ready" : "blocked"}`}>
    <div>
      <span>{title}</span>
      <h2>{ready ? "Готово к запуску" : "Требует подготовки"}</h2>
      <p>{note}</p>
    </div>
    <div className="readiness-summary-stats">
      <div><span>Блокирует</span><b>{blockers}</b></div>
      <div><span>Предупреждения</span><b>{warnings}</b></div>
    </div>
  </section>;
}

export default function LaunchReadiness({ onNavigate }) {
  const [data, setData] = useState(null);

  const refresh = async () => setData(await api.launchReadiness());

  useEffect(() => { refresh(); }, []);

  const productionChecks = useMemo(
    () => data?.checks?.filter(item => item.scope === "CORE") || [],
    [data]
  );
  const payrollChecks = useMemo(
    () => data?.checks?.filter(item => item.scope === "PAYROLL") || [],
    [data]
  );

  if (!data) return <div className="card panel">Проверка готовности к запуску…</div>;

  return <>
    <div className="integration-toolbar card">
      <div>
        <h2>Готовность к запуску</h2>
        <p>Контроль обязательных справочников, пользователей, интеграций и расчетного контура</p>
      </div>
      <button className="btn ghost" onClick={refresh}>Проверить снова</button>
    </div>

    <div className="readiness-summary-grid">
      <SummaryBlock
        title="Производственный контур"
        ready={data.summary.production_ready}
        blockers={data.summary.production_blockers}
        warnings={data.summary.production_warnings}
        note="Все, что необходимо для проведения тестовой производственной смены."
      />
      <SummaryBlock
        title="Сдельная заработная плата"
        ready={data.summary.payroll_ready}
        blockers={data.summary.payroll_blockers}
        warnings={data.summary.payroll_warnings}
        note="Отдельная готовность расчетного контура. Не блокирует запуск производства."
      />
    </div>

    <section className="card panel">
      <div className="panel-head">
        <h2>Производство</h2>
        <span>{productionChecks.length} проверок</span>
      </div>
      <div className="readiness-grid">
        {productionChecks.map(item =>
          <ReadinessCard key={item.key} item={item} onNavigate={onNavigate} />
        )}
      </div>
    </section>

    <section className="card panel">
      <div className="panel-head">
        <h2>Сдельная ЗП</h2>
        <span>{payrollChecks.length} проверок</span>
      </div>
      <div className="readiness-grid">
        {payrollChecks.map(item =>
          <ReadinessCard key={item.key} item={item} onNavigate={onNavigate} />
        )}
      </div>
    </section>

    <section className="card panel">
      <div className="panel-head"><h2>Сводные количества</h2></div>
      <div className="readiness-counts">
        <div><span>Сотрудники</span><b>{data.counts.employees || 0}</b></div>
        <div><span>Линии</span><b>{data.counts.equipment || 0}</b></div>
        <div><span>Номенклатура</span><b>{data.counts.products || 0}</b></div>
        <div><span>Нормативы</span><b>{data.counts.production_norms || 0}</b></div>
        <div><span>Тарифы</span><b>{data.counts.payroll_rates || 0}</b></div>
        <div><span>План ERP</span><b>{data.counts.erp_plan_rows || 0}</b></div>
      </div>
    </section>
  </>;
}
