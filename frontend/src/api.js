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

const erpPlanSummaryFallback = {
  counts: { total: 1, runs: 0, orders_only: 1, partial: 1, errors: 0 },
  last_import: {
    source_file_name: "Этап производства — пример.xlsx",
    source_sheet: "Лист1",
    status: "COMPLETED",
    rows_read: 1,
    rows_applied: 1
  }
};

const erpPlanRowsFallback = {
  rows: [{
    id: "44444444-4444-4444-8444-444444444444",
    business_date: "2026-09-25",
    task_id: "Задание ERP",
    order_no: "Заказ ERP",
    article: "Артикул",
    product_name: "Продукция из задания 1С",
    plan_qty_pcs: 22500,
    route_equipment_hint: "16/2",
    resolved_equipment_code: null,
    shift_code: null,
    ideal_rate_per_hour: 5921.05,
    promotion_status: "ORDER_CREATED"
  }]
};

const yandexStatusFallback = {
  configured: false,
  resource_path_configured: false,
  last_import: erpPlanSummaryFallback.last_import
};

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

const TOKEN_KEY = "vitagroup_access_token";
let demoSession = false;
const BUILD_DEMO_MODE = import.meta.env.VITE_DEMO_MODE === "true";

function getToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {}
}

function authHeaders(options = {}) {
  const token = getToken();
  return {
    Accept: "application/json",
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {})
  };
}

async function strictRequest(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: authHeaders(options)
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = body?.detail || `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return body;
}

async function request(path, fallbackValue, options = {}) {
  try {
    return await strictRequest(path, options);
  } catch (error) {
    if (error?.status === 401) {
      setToken(null);
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event("vitagroup-auth-expired"));
      }
    }

    if (demoSession || BUILD_DEMO_MODE) {
      return fallbackValue;
    }

    throw error;
  }
}

export const api = {
  shiftLifecycle: (businessDate, shiftCode) => {
    const params = new URLSearchParams({ business_date: businessDate, shift_code: shiftCode });
    return strictRequest(`/api/v1/shift-lifecycle?${params.toString()}`);
  },
  testShiftContext: (businessDate, shiftCode) => {
    const params = new URLSearchParams({ business_date: businessDate, shift_code: shiftCode });
    return strictRequest(`/api/v1/test-shift?${params.toString()}`);
  },
  createTestShift: (businessDate, shiftCode) => {
    const params = new URLSearchParams({ business_date: businessDate, shift_code: shiftCode });
    return strictRequest(`/api/v1/test-shift/create?${params.toString()}`, { method: "POST" });
  },
  assignTestShiftStaff: (runId, employeeIds) => strictRequest(
    `/api/v1/test-shift/runs/${runId}/staff`,
    { method: "POST", body: JSON.stringify({ employee_ids: employeeIds }) }
  ),
  adminNorms: () => strictRequest("/api/v1/admin/norms"),
  adminSaveNorm: (payload) => strictRequest(
    "/api/v1/admin/norms",
    { method: "POST", body: JSON.stringify(payload) }
  ),
  adminReasons: () => strictRequest("/api/v1/admin/reasons"),
  adminSaveDowntimeReason: (payload) => strictRequest(
    "/api/v1/admin/reasons/downtime",
    { method: "POST", body: JSON.stringify(payload) }
  ),
  adminSaveDefectReason: (payload) => strictRequest(
    "/api/v1/admin/reasons/defect",
    { method: "POST", body: JSON.stringify(payload) }
  ),
  launchReadiness: () => request(
    "/api/v1/launch-readiness",
    {
      summary: {
        production_ready: false,
        production_blockers: 0,
        production_warnings: 0,
        payroll_ready: false,
        payroll_blockers: 0,
        payroll_warnings: 0
      },
      counts: {},
      roles: {},
      checks: []
    }
  ),
  setDemoMode: (enabled) => {
    demoSession = Boolean(enabled);
  },
  problemCenter: (businessDate, shiftCode) => {
    const params = new URLSearchParams();
    if (businessDate) params.set("business_date", businessDate);
    if (shiftCode) params.set("shift_code", shiftCode);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return request(
      `/api/v1/problem-center${suffix}`,
      {
        context: { business_date: businessDate || "", shift_code: shiftCode || "DAY" },
        summary: { total: 0, critical: 0, warning: 0, production: 0, integration: 0, shift: 0 },
        items: []
      }
    );
  },
  verifyShift: (businessDate, shiftCode) => {
    const params = new URLSearchParams({ business_date: businessDate, shift_code: shiftCode });
    return strictRequest(
      `/api/v1/production-manager/verify-shift?${params.toString()}`,
      { method: "POST" }
    );
  },
  managementOverview: (endDate, days = 14) => {
    const params = new URLSearchParams({ days: String(days) });
    if (endDate) params.set("end_date", endDate);
    return request(
      `/api/v1/management/overview?${params.toString()}`,
      {
        period: { date_from: "", date_to: endDate || "", days },
        summary: {
          plan: 0,
          output: 0,
          good: 0,
          qc_defect: 0,
          downtime_minutes: 0,
          open_cases: 0,
          critical_cases: 0,
          missing_norm_runs: 0,
          completion_percent: null,
          defect_rate_percent: null,
          average_oee: null
        },
        trend_change: { oee: null, completion: null },
        daily: [],
        problem_lines: []
      }
    );
  },
  productionManagerDay: (businessDate) => {
    const params = new URLSearchParams({ business_date: businessDate });
    return request(
      `/api/v1/production-manager/day?${params.toString()}`,
      {
        business_date: businessDate,
        summary: {
          plan: 0,
          output: 0,
          good: 0,
          qc_defect: 0,
          downtime_minutes: 0,
          completion_percent: null,
          oee: null,
          open_cases: 0,
          critical_cases: 0,
          missing_norm_runs: 0
        },
        day: null,
        night: null,
        equipment: []
      }
    );
  },
  completeProductionRun: (runId) => strictRequest(
    `/api/v1/shift-master/runs/${runId}/complete`,
    { method: "POST" }
  ),
  shiftCloseReadiness: (businessDate, shiftCode) => {
    const params = new URLSearchParams({ business_date: businessDate, shift_code: shiftCode });
    return request(
      `/api/v1/shift-master/close-readiness?${params.toString()}`,
      { ready: false, shift: { business_date: businessDate, type: shiftCode }, blockers: [], warnings: [] }
    );
  },
  closeShift: (businessDate, shiftCode) => {
    const params = new URLSearchParams({ business_date: businessDate, shift_code: shiftCode });
    return strictRequest(
      `/api/v1/shift-master/close?${params.toString()}`,
      { method: "POST" }
    );
  },
  shiftMasterDashboard: (businessDate, shiftCode) => {
    const params = new URLSearchParams();
    if (businessDate) params.set("business_date", businessDate);
    if (shiftCode) params.set("shift_code", shiftCode);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return request(
      `/api/v1/shift-master/dashboard${suffix}`,
      {
        shift: { business_date: businessDate || "", type: shiftCode || "DAY", label: shiftCode === "NIGHT" ? "НОЧЬ" : "ДЕНЬ", time: shiftCode === "NIGHT" ? "21:00–09:00" : "09:00–21:00" },
        kpi: { oee: null, availability: null, performance: null, quality: null },
        production: { plan: 0, operator_output: 0, good_product: 0, operator_defect: 0, qc_defect: 0, warehouse_received: 0, erp_fact: 0 },
        time: { planned_minutes: 0, downtime_minutes: 0, runtime_minutes: 0 },
        expected_progress_percent: 0,
        summary: { lines: 0, running: 0, downtime: 0, problem_lines: 0, staff: 0 },
        lines: [],
        alerts: []
      }
    );
  },
  reconciliationControl: (businessDate, shiftCode) => {
    const params = new URLSearchParams();
    if (businessDate) params.set("business_date", businessDate);
    if (shiftCode) params.set("shift_code", shiftCode);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return request(
      `/api/v1/reconciliation-control${suffix}`,
      {
        summary: { runs: 0, ok: 0, warning: 0, critical: 0, open_cases: 0 },
        rows: [],
        reason_options: []
      }
    );
  },
  saveReconciliationCase: (runId, payload) => strictRequest(
    `/api/v1/reconciliation-control/${runId}/case`,
    { method: "POST", body: JSON.stringify(payload) }
  ),
  workspaceContext: (kind, businessDate, shiftCode) => {
    const params = new URLSearchParams();
    if (businessDate) params.set("business_date", businessDate);
    if (shiftCode) params.set("shift_code", shiftCode);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return request(
      `/api/v1/workspaces/${kind}/context${suffix}`,
      {
        workspace: kind,
        shift: { business_date: businessDate || "", code: shiftCode || "DAY", label: shiftCode === "NIGHT" ? "НОЧЬ" : "ДЕНЬ", time: shiftCode === "NIGHT" ? "21:00–09:00" : "09:00–21:00" },
        runs: [],
        downtime_reasons: [],
        defect_reasons: [],
        active_downtime: [],
        recent: []
      }
    );
  },
  operatorOutput: (payload) => request("/api/v1/workspaces/operator/output", { status: "demo" }, { method: "POST", body: JSON.stringify(payload) }),
  operatorDefect: (payload) => request("/api/v1/workspaces/operator/defect", { status: "demo" }, { method: "POST", body: JSON.stringify(payload) }),
  operatorDowntimeStart: (payload) => request("/api/v1/workspaces/operator/downtime/start", { status: "demo" }, { method: "POST", body: JSON.stringify(payload) }),
  operatorDowntimeStop: (downtimeId, payload = {}) => request(`/api/v1/workspaces/operator/downtime/${downtimeId}/stop`, { status: "demo" }, { method: "POST", body: JSON.stringify(payload) }),
  qcDefect: (payload) => request("/api/v1/workspaces/qc/defect", { status: "demo" }, { method: "POST", body: JSON.stringify(payload) }),
  warehouseReceipt: (payload) => request("/api/v1/workspaces/warehouse/receipt", { status: "demo" }, { method: "POST", body: JSON.stringify(payload) }),
  accountantControl: (payload) => request("/api/v1/workspaces/accountant/control", { status: "demo" }, { method: "POST", body: JSON.stringify(payload) }),
  hasToken: () => Boolean(getToken()),
  login: async (email, password) => {
    const result = await strictRequest("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password })
    });
    setToken(result.access_token);
    return result;
  },
  authMe: async () => {
    if (!getToken()) return null;
    try {
      return await strictRequest("/api/v1/auth/me");
    } catch {
      setToken(null);
      return null;
    }
  },
  logout: () => setToken(null),
  changePassword: (currentPassword, newPassword) => strictRequest(
    "/api/v1/auth/change-password",
    {
      method: "POST",
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword
      })
    }
  ),
  adminUsers: () => strictRequest("/api/v1/admin/users"),
  adminMeta: () => strictRequest("/api/v1/admin/users/meta"),
  adminCreateUser: (payload) => strictRequest("/api/v1/admin/users", {
    method: "POST",
    body: JSON.stringify(payload)
  }),
  adminSetRoles: (userId, roles) => strictRequest(`/api/v1/admin/users/${userId}/roles`, {
    method: "PUT",
    body: JSON.stringify({ roles })
  }),
  adminSetActive: (userId, isActive) => strictRequest(`/api/v1/admin/users/${userId}/active`, {
    method: "PUT",
    body: JSON.stringify({ is_active: isActive })
  }),
  adminResetPassword: (userId, newPassword) => strictRequest(`/api/v1/admin/users/${userId}/reset-password`, {
    method: "POST",
    body: JSON.stringify({ new_password: newPassword })
  }),
  oeeRuns: (businessDate, shiftCode) => {
    const params = new URLSearchParams();
    if (businessDate) params.set("business_date", businessDate);
    if (shiftCode) params.set("shift_code", shiftCode);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return request(`/api/v1/oee/runs${suffix}`, { rows: [] });
  },
  oeeRunDetail: (runId) => request(
    `/api/v1/oee/runs/${runId}`,
    {
      run: {
        id: runId,
        equipment_code: "DEMO",
        equipment_name: "Демо-линия",
        order_no: "DEMO",
        product_name: "Демо-продукция",
        planned_qty: 10000,
        output_qty: 9000,
        good_qty: 8820,
        ideal_rate_per_hour: 5000,
        theoretical_qty: 9500,
        planned_minutes: 120,
        downtime_minutes: 6,
        runtime_minutes: 114,
        operator_defect_qty: 220,
        qc_defect_qty: 180,
        warehouse_qty: 8750,
        erp_qty: 8700,
        availability: 95,
        performance: 94.7,
        quality: 98,
        oee: 88.2
      },
      formula: {
        availability: { numerator: 114, denominator: 120, result: 95 },
        performance: { numerator: 9000, denominator: 9500, result: 94.7 },
        quality: { numerator: 8820, denominator: 9000, result: 98 },
        oee: { availability: 95, performance: 94.7, quality: 98, result: 88.2 }
      },
      warnings: [],
      events: { output: [], downtime: [], defects: [], warehouse: [], erp: [] }
    }
  ),
  summary: (businessDate, shiftCode) => {
    const params = new URLSearchParams();
    if (businessDate) params.set("business_date", businessDate);
    if (shiftCode) params.set("shift_code", shiftCode);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return request(`/api/v1/dashboard/summary${suffix}`, fallback);
  },
  downtime: (businessDate, shiftCode) => {
    const params = new URLSearchParams();
    if (businessDate) params.set("business_date", businessDate);
    if (shiftCode) params.set("shift_code", shiftCode);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return request(`/api/v1/downtime${suffix}`, [
    { equipment: "LINE-02", start: "12:34", end: null, minutes: 57, reason: "Ожидание материала", planned: false },
    { equipment: "LINE-03", start: "10:11", end: "10:29", minutes: 18, reason: "Переналадка", planned: true }
    ]);
  },
  reconciliation: (businessDate, shiftCode) => {
    const params = new URLSearchParams();
    if (businessDate) params.set("business_date", businessDate);
    if (shiftCode) params.set("shift_code", shiftCode);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return request(`/api/v1/reconciliation${suffix}`, [
    { product: "Арт. 34001", operator: 12400, qc_good: 12280, warehouse: 12240, erp: 12240 },
    { product: "Арт. 37008", operator: 8200, qc_good: 8170, warehouse: 8150, erp: 8100 },
    { product: "Арт. 41012", operator: 15600, qc_good: 15340, warehouse: 15180, erp: 15000 }
    ]);
  },
  payrollPreview: (dateFrom, dateTo, quantityBasis) => {
    const params = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
    if (quantityBasis) params.set("quantity_basis", quantityBasis);
    return request(
      `/api/v1/payroll/preview?${params.toString()}`,
      {
        date_from: dateFrom,
        date_to: dateTo,
        quantity_basis: quantityBasis,
        summary: { runs: 0, rows: 0, ready_rows: 0, blocked_rows: 0, preliminary_rows: 0, ready_amount: 0, blockers: {}, warnings: {} },
        rows: []
      }
    );
  },
  payrollPeriods: () => request("/api/v1/payroll/periods", { rows: [] }),
  payrollCreatePeriod: (payload) => request(
    "/api/v1/payroll/periods",
    { id: "demo-period", ...payload, status: "DRAFT" },
    { method: "POST", body: JSON.stringify(payload) }
  ),
  payrollCalculatePeriod: (periodId) => request(
    `/api/v1/payroll/periods/${periodId}/calculate`,
    { status: "BLOCKED", period_id: periodId, summary: { blocked_rows: 1 }, rows: [] },
    { method: "POST" }
  ),
  payrollRateOptions: (equipmentId, businessDate) => {
    const params = new URLSearchParams({ equipment_id: equipmentId, business_date: businessDate });
    return request(`/api/v1/payroll/rate-options?${params.toString()}`, { product_types: [], print_flags: [], tariff_groups: [], rules: [] });
  },
  payrollSaveProductAttributes: (productId, payload) => request(
    `/api/v1/payroll/products/${productId}/attributes`,
    { product_id: productId, ...payload, confirmed: true },
    { method: "POST", body: JSON.stringify(payload) }
  ),
  payrollSaveAllocation: (runId, payload) => request(
    `/api/v1/payroll/runs/${runId}/allocation`,
    { status: "ok", production_run_id: runId },
    { method: "POST", body: JSON.stringify(payload) }
  ),
  erpPlanSummary: () => request("/api/v1/erp-plan/summary", erpPlanSummaryFallback),
  erpPlanRows: () => request("/api/v1/erp-plan/rows?limit=300", erpPlanRowsFallback),
  erpPlanPromote: () => request("/api/v1/erp-plan/promote", { demo: true, orders_created_or_updated: 1, runs_created_or_found: 0 }, { method: "POST" }),
  yandexStatus: () => request("/api/v1/integrations/yandex-disk/status", yandexStatusFallback),
  yandexPreview: () => request("/api/v1/integrations/yandex-disk/preview", { demo: true, message: "Предпросмотр будет доступен после запуска сервера" }, { method: "POST" }),
  yandexImport: () => request("/api/v1/integrations/yandex-disk/import", { demo: true, file_name: "Файл плана", status: "DEMO" }, { method: "POST" }),
  integrationDashboard: () => request("/api/v1/reference/dashboard", integrationFallback),
  unresolved: () => request("/api/v1/reference/unresolved?limit=200", { rows: unresolvedFallback }),
  masterSources: () => request("/api/v1/master-data/sources", []),
  previewMasterSource: (key) => strictRequest(`/api/v1/master-data/preview/${key}`, { method: "POST" }),
  pilotSyncMasterData: () => strictRequest("/api/v1/master-data/pilot-sync", { method: "POST" }),
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
