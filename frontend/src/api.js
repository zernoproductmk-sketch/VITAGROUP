const fallback = {
  status: "ONLINE",
  shift: { business_date: "2026-09-23", type: "DAY", label: "ДЕНЬ", time: "09:00–21:00" },
  kpi: { oee: 76.4, availability: 88.2, performance: 91.5, quality: 94.7 },
  production: {
    plan: 82000,
    operator_output: 61450,
    good_product: 59870,
    operator_defect: 1580,
    qc_defect: 1490,
    warehouse_received: 59320,
    erp_fact: 58900
  },
  equipment: [
    { code: "LINE-01", name: "Пакетоделательная линия №1", state: "RUNNING", oee: 82.1, product: "Пакет бумажный 320×200", output: 18400, downtime_minutes: 22 },
    { code: "LINE-02", name: "Пакетоделательная линия №2", state: "DOWNTIME", oee: 68.7, product: "Пакет бумажный 260×150", output: 13950, downtime_minutes: 57, downtime_reason: "Ожидание материала" },
    { code: "LINE-03", name: "Пакетоделательная линия №3", state: "RUNNING", oee: 78.4, product: "Пакет бумажный 400×240", output: 16600, downtime_minutes: 31 },
    { code: "LINE-04", name: "Печатная машина №1", state: "RUNNING", oee: 74.9, product: "Печать / заказ ERP-260923-18", output: 12500, downtime_minutes: 44 }
  ]
};

const integrationFallback = {
  event_sources: {
    downtime: { total: 1, resolved: 0, partial: 1, errors: 0, promoted: 0 },
    production_output: { total: 1, resolved: 0, partial: 1, errors: 0, promoted: 0 },
    qc_defects: { total: 1, resolved: 0, partial: 1, errors: 0, promoted: 0 },
    warehouse: { total: 1, resolved: 0, partial: 1, errors: 0, promoted: 0 },
    accountant: { total: 1, resolved: 0, partial: 1, errors: 0, promoted: 0 }
  },
  master_sources: {
    employees: { status: "READY", rows_read: 0, rows_applied: 0 },
    equipment: { status: "READY", rows_read: 0, rows_applied: 0 },
    products: { status: "READY", rows_read: 0, rows_applied: 0 },
    tariffs: { status: "READY", rows_read: 0, rows_applied: 0 },
    production_norms: { status: "BLOCKED", rows_read: 26, rows_applied: 0, message: "Источник норм требует исправления структуры" }
  },
  totals: { unresolved: 5, open_resolution_issues: 5, open_master_issues: 1 }
};

const unresolvedFallback = [
  {
    id: "11111111-1111-4111-8111-111111111111",
    event_type: "production_output",
    business_date: "2026-09-22",
    shift_code: "DAY",
    personnel_number: "00452",
    order_no: "430.83.1",
    resolution_status: "PARTIAL",
    resolution_details: { missing: ["production_order_id", "production_run_id", "equipment_id", "product_id", "shift_id"] }
  },
  {
    id: "22222222-2222-4222-8222-222222222222",
    event_type: "qc_defects",
    business_date: "2026-09-22",
    shift_code: "DAY",
    personnel_number: "00262",
    resolution_status: "PARTIAL",
    resolution_details: { missing: ["product_id", "production_run_id", "shift_id"] }
  },
  {
    id: "33333333-3333-4333-8333-333333333333",
    event_type: "warehouse",
    business_date: "2026-09-22",
    shift_code: "DAY",
    personnel_number: "00453",
    article_code: "1001",
    ticket_no: "Дтест/01/220926/14/1",
    resolution_status: "PARTIAL",
    resolution_details: { missing: ["employee_id", "product_id", "shift_id"] }
  }
];

const demoCandidates = {
  EMPLOYEE: [
    { id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", code: "00452", label: "Оператор — тестовая запись", secondary: "Производство" },
    { id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", code: "00453", label: "Кладовщик — тестовая запись", secondary: "Склад" }
  ],
  EQUIPMENT: [
    { id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc", code: "L-14/1", label: "L-14/1", secondary: null },
    { id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd", code: "L-18", label: "L-18", secondary: null }
  ],
  PRODUCT: [
    { id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee", code: "ОВ-55-3442", label: "Бумага оберточная 340х420 мм", secondary: "1001" }
  ],
  PRODUCTION_ORDER: [
    { id: "ffffffff-ffff-4fff-8fff-ffffffffffff", code: "430.83.1", label: "Заказ 430.83.1", secondary: "Демо ERP" }
  ]
};

async function request(path, fallbackValue, options = {}) {
  try {
    const response = await fetch(path, {
      headers: { Accept: "application/json", "Content-Type": "application/json", ...(options.headers || {}) },
      ...options
    });
    if (!response.ok) throw new Error(String(response.status));
    return await response.json();
  } catch {
    return fallbackValue;
  }
}

export const api = {
  summary: () => request("/api/v1/dashboard/summary", fallback),
  downtime: () => request("/api/v1/downtime", [
    { equipment: "LINE-02", start: "12:34", end: null, minutes: 57, reason: "Ожидание материала", planned: false },
    { equipment: "LINE-03", start: "10:11", end: "10:29", minutes: 18, reason: "Переналадка", planned: true }
  ]),
  reconciliation: () => request("/api/v1/reconciliation", [
    { product: "Арт. 34001", operator: 12400, qc_good: 12280, warehouse: 12240, erp: 12240 },
    { product: "Арт. 37008", operator: 8200, qc_good: 8170, warehouse: 8150, erp: 8100 },
    { product: "Арт. 41012", operator: 15600, qc_good: 15340, warehouse: 15180, erp: 15000 }
  ]),
  payroll: () => request("/api/v1/payroll/summary", [
    { employee: "Иванов И.И.", shifts: 14, approved_quantity: 183400, amount: 184250 },
    { employee: "Петров П.П.", shifts: 13, approved_quantity: 171200, amount: 176840 },
    { employee: "Сидоров А.А.", shifts: 15, approved_quantity: 194600, amount: 191320 }
  ]),
  integrationDashboard: () => request("/api/v1/reference/dashboard", integrationFallback),
  unresolved: () => request("/api/v1/reference/unresolved?limit=200", { rows: unresolvedFallback }),
  masterSources: () => request("/api/v1/master-data/sources", []),
  coverseSources: () => request("/api/v1/integrations/coverse/sources", []),
  syncMasterData: () => request("/api/v1/master-data/sync", { demo: true }, { method: "POST" }),
  syncMasterSource: (key) => request(`/api/v1/master-data/sync/${key}`, { source: key, status: "DEMO" }, { method: "POST" }),
  syncCoverseSource: (key) => request(`/api/v1/integrations/coverse/sync/${key}`, { source: key, demo: true }, { method: "POST" }),
  resolveReferences: () => request("/api/v1/reference/resolve", { demo: true, processed: 0 }, { method: "POST" }),
  promoteResolved: () => request("/api/v1/reference/promote", { demo: true, promoted: 0 }, { method: "POST" }),
  candidates: (entityType, q = "") => {
    const all = demoCandidates[entityType] || [];
    const needle = q.trim().toLowerCase();
    const filtered = needle
      ? all.filter(item => [item.code, item.label, item.secondary].some(v => String(v || "").toLowerCase().includes(needle)))
      : all;
    return request(
      `/api/v1/reference/candidates/${entityType}?q=${encodeURIComponent(q)}`,
      { rows: filtered }
    );
  },
  manualMap: (payload) => request(
    "/api/v1/reference/manual-map",
    { status: "demo", event: { id: payload.staging_event_id, resolution_status: "PARTIAL" } },
    { method: "POST", body: JSON.stringify(payload) }
  ),
  addAlias: (payload) => request("/api/v1/reference/aliases", { status: "demo" }, { method: "POST", body: JSON.stringify(payload) })
};
