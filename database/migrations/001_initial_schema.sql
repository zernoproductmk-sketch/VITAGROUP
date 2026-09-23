-- VITAGROUP Production & OEE System
-- PostgreSQL initial schema v1
-- PostgreSQL 16+

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------- Access ----------

CREATE TABLE roles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE,
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE employees (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    personnel_number text NOT NULL UNIQUE,
    full_name text NOT NULL,
    position_name text,
    department_name text,
    erp_id text UNIQUE,
    is_active boolean NOT NULL DEFAULT true,
    valid_from date,
    valid_to date,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)
);

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    employee_id uuid REFERENCES employees(id),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_roles (
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

-- ---------- Master data ----------

CREATE TABLE production_areas (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE,
    name text NOT NULL,
    is_active boolean NOT NULL DEFAULT true
);

CREATE TABLE equipment (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE,
    name text NOT NULL,
    production_area_id uuid REFERENCES production_areas(id),
    erp_id text UNIQUE,
    coverse_id text,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE products (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    erp_id text UNIQUE,
    code text NOT NULL UNIQUE,
    article text,
    name text NOT NULL,
    unit text NOT NULL DEFAULT 'pcs',
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE operations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE,
    name text NOT NULL,
    is_active boolean NOT NULL DEFAULT true
);

CREATE TABLE downtime_reasons (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE,
    category text NOT NULL,
    name text NOT NULL,
    affects_availability boolean NOT NULL DEFAULT true,
    is_planned boolean NOT NULL DEFAULT false,
    is_active boolean NOT NULL DEFAULT true
);

CREATE TABLE defect_reasons (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE,
    category text,
    name text NOT NULL,
    is_active boolean NOT NULL DEFAULT true
);

-- ---------- Shifts ----------

CREATE TABLE shift_types (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE,
    name text NOT NULL,
    start_time time NOT NULL,
    end_time time NOT NULL,
    crosses_midnight boolean NOT NULL DEFAULT false
);

CREATE TABLE shifts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    shift_type_id uuid NOT NULL REFERENCES shift_types(id),
    business_date date NOT NULL,
    started_at timestamptz NOT NULL,
    ended_at timestamptz NOT NULL,
    status text NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN','CLOSED','VERIFIED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (shift_type_id, business_date),
    CHECK (ended_at > started_at)
);

CREATE TABLE employee_shift_assignments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    shift_id uuid NOT NULL REFERENCES shifts(id),
    employee_id uuid NOT NULL REFERENCES employees(id),
    equipment_id uuid REFERENCES equipment(id),
    operation_id uuid REFERENCES operations(id),
    started_at timestamptz,
    ended_at timestamptz,
    allocation_factor numeric(12,6) NOT NULL DEFAULT 1,
    source_system text NOT NULL DEFAULT 'WEB',
    source_record_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (allocation_factor > 0),
    CHECK (ended_at IS NULL OR started_at IS NULL OR ended_at > started_at)
);

-- ---------- Orders / runs ----------

CREATE TABLE production_orders (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    erp_id text UNIQUE,
    order_no text NOT NULL,
    product_id uuid NOT NULL REFERENCES products(id),
    planned_quantity numeric(18,3),
    planned_start_at timestamptz,
    planned_end_at timestamptz,
    status text NOT NULL DEFAULT 'PLANNED',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (order_no, product_id)
);

CREATE TABLE production_norms (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id uuid NOT NULL REFERENCES products(id),
    equipment_id uuid NOT NULL REFERENCES equipment(id),
    operation_id uuid REFERENCES operations(id),
    ideal_rate_per_hour numeric(18,6) NOT NULL,
    valid_from date NOT NULL,
    valid_to date,
    source_system text NOT NULL DEFAULT 'ERP',
    source_record_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (ideal_rate_per_hour > 0),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE TABLE production_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    shift_id uuid NOT NULL REFERENCES shifts(id),
    equipment_id uuid NOT NULL REFERENCES equipment(id),
    product_id uuid NOT NULL REFERENCES products(id),
    production_order_id uuid REFERENCES production_orders(id),
    operation_id uuid REFERENCES operations(id),
    planned_start_at timestamptz,
    planned_end_at timestamptz,
    actual_start_at timestamptz,
    actual_end_at timestamptz,
    planned_qty numeric(18,3),
    ideal_rate_per_hour numeric(18,6),
    status text NOT NULL DEFAULT 'PLANNED'
        CHECK (status IN ('PLANNED','RUNNING','PAUSED','COMPLETED','CANCELLED','VERIFIED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (ideal_rate_per_hour IS NULL OR ideal_rate_per_hour > 0),
    CHECK (actual_end_at IS NULL OR actual_start_at IS NULL OR actual_end_at > actual_start_at)
);

-- ---------- Integration import ----------

CREATE TABLE import_batches (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_system text NOT NULL
        CHECK (source_system IN ('COVERSE','ERP','GOOGLE_SHEETS','EXCEL','WEB','SYSTEM')),
    data_type text NOT NULL,
    source_name text,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    rows_total integer NOT NULL DEFAULT 0,
    rows_success integer NOT NULL DEFAULT 0,
    rows_error integer NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'RUNNING'
        CHECK (status IN ('RUNNING','COMPLETED','COMPLETED_WITH_ERRORS','FAILED')),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE import_errors (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    import_batch_id uuid NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    row_number integer,
    error_code text,
    error_message text NOT NULL,
    raw_data jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------- Facts ----------

CREATE TABLE production_output_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    production_run_id uuid NOT NULL REFERENCES production_runs(id),
    occurred_at timestamptz NOT NULL,
    quantity numeric(18,3) NOT NULL,
    event_kind text NOT NULL DEFAULT 'INCREMENT'
        CHECK (event_kind IN ('INCREMENT','CORRECTION','FINAL')),
    status text NOT NULL DEFAULT 'RECORDED'
        CHECK (status IN ('RECORDED','VERIFIED','REJECTED')),
    source_system text NOT NULL
        CHECK (source_system IN ('COVERSE','ERP','GOOGLE_SHEETS','EXCEL','WEB','SYSTEM')),
    source_record_id text,
    import_batch_id uuid REFERENCES import_batches(id),
    entered_by_user_id uuid REFERENCES users(id),
    comment text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE NULLS NOT DISTINCT (source_system, source_record_id)
);

CREATE TABLE defect_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    production_run_id uuid NOT NULL REFERENCES production_runs(id),
    occurred_at timestamptz NOT NULL,
    quantity numeric(18,3) NOT NULL CHECK (quantity >= 0),
    defect_reason_id uuid REFERENCES defect_reasons(id),
    reported_by text NOT NULL
        CHECK (reported_by IN ('OPERATOR','QC','SYSTEM_RECONCILIATION')),
    is_confirmed boolean NOT NULL DEFAULT false,
    source_system text NOT NULL
        CHECK (source_system IN ('COVERSE','ERP','GOOGLE_SHEETS','EXCEL','WEB','SYSTEM')),
    source_record_id text,
    import_batch_id uuid REFERENCES import_batches(id),
    entered_by_user_id uuid REFERENCES users(id),
    comment text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE NULLS NOT DISTINCT (source_system, source_record_id)
);

CREATE TABLE downtime_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    production_run_id uuid REFERENCES production_runs(id),
    equipment_id uuid NOT NULL REFERENCES equipment(id),
    shift_id uuid NOT NULL REFERENCES shifts(id),
    reason_id uuid REFERENCES downtime_reasons(id),
    started_at timestamptz NOT NULL,
    ended_at timestamptz,
    is_planned boolean NOT NULL DEFAULT false,
    source_system text NOT NULL
        CHECK (source_system IN ('COVERSE','ERP','GOOGLE_SHEETS','EXCEL','WEB','SYSTEM')),
    source_record_id text,
    import_batch_id uuid REFERENCES import_batches(id),
    entered_by_user_id uuid REFERENCES users(id),
    comment text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (ended_at IS NULL OR ended_at > started_at),
    UNIQUE NULLS NOT DISTINCT (source_system, source_record_id)
);

CREATE TABLE warehouse_receipts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    production_run_id uuid REFERENCES production_runs(id),
    shift_id uuid REFERENCES shifts(id),
    product_id uuid NOT NULL REFERENCES products(id),
    received_at timestamptz NOT NULL,
    quantity numeric(18,3) NOT NULL CHECK (quantity >= 0),
    warehouse_document_no text,
    source_system text NOT NULL
        CHECK (source_system IN ('COVERSE','ERP','GOOGLE_SHEETS','EXCEL','WEB','SYSTEM')),
    source_record_id text,
    import_batch_id uuid REFERENCES import_batches(id),
    entered_by_user_id uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE NULLS NOT DISTINCT (source_system, source_record_id)
);

CREATE TABLE erp_production_facts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    erp_document_id text NOT NULL,
    erp_document_no text,
    production_order_id uuid REFERENCES production_orders(id),
    product_id uuid NOT NULL REFERENCES products(id),
    production_run_id uuid REFERENCES production_runs(id),
    occurred_at timestamptz NOT NULL,
    quantity numeric(18,3) NOT NULL CHECK (quantity >= 0),
    defect_quantity numeric(18,3) CHECK (defect_quantity IS NULL OR defect_quantity >= 0),
    import_batch_id uuid REFERENCES import_batches(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (erp_document_id, product_id, occurred_at)
);

-- ---------- Payroll ----------

CREATE TABLE payroll_rates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    operation_id uuid NOT NULL REFERENCES operations(id),
    product_id uuid REFERENCES products(id),
    equipment_id uuid REFERENCES equipment(id),
    rate_per_unit numeric(18,6) NOT NULL CHECK (rate_per_unit >= 0),
    currency char(3) NOT NULL DEFAULT 'RUB',
    valid_from date NOT NULL,
    valid_to date,
    source_document text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE TABLE payroll_periods (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    date_from date NOT NULL,
    date_to date NOT NULL,
    status text NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT','CALCULATED','VERIFIED','APPROVED','EXPORTED')),
    calculated_by_user_id uuid REFERENCES users(id),
    verified_by_user_id uuid REFERENCES users(id),
    approved_by_user_id uuid REFERENCES users(id),
    calculated_at timestamptz,
    verified_at timestamptz,
    approved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (date_to >= date_from)
);

CREATE TABLE payroll_lines (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    payroll_period_id uuid NOT NULL REFERENCES payroll_periods(id) ON DELETE CASCADE,
    employee_id uuid NOT NULL REFERENCES employees(id),
    shift_id uuid REFERENCES shifts(id),
    production_run_id uuid REFERENCES production_runs(id),
    operation_id uuid NOT NULL REFERENCES operations(id),
    approved_quantity numeric(18,3) NOT NULL CHECK (approved_quantity >= 0),
    rate_per_unit numeric(18,6) NOT NULL CHECK (rate_per_unit >= 0),
    allocation_factor numeric(12,6) NOT NULL DEFAULT 1 CHECK (allocation_factor > 0),
    amount numeric(18,2) GENERATED ALWAYS AS
        (round((approved_quantity * rate_per_unit * allocation_factor)::numeric, 2)) STORED,
    basis text,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------- Audit ----------

CREATE TABLE audit_log (
    id bigserial PRIMARY KEY,
    table_name text NOT NULL,
    record_id uuid,
    action text NOT NULL CHECK (action IN ('INSERT','UPDATE','DELETE','APPROVE','VERIFY','REJECT')),
    changed_by_user_id uuid REFERENCES users(id),
    old_data jsonb,
    new_data jsonb,
    reason text,
    changed_at timestamptz NOT NULL DEFAULT now()
);

-- ---------- Indexes ----------

CREATE INDEX idx_shifts_started_at ON shifts(started_at);
CREATE INDEX idx_runs_shift_equipment ON production_runs(shift_id, equipment_id);
CREATE INDEX idx_runs_product ON production_runs(product_id);
CREATE INDEX idx_output_run_time ON production_output_events(production_run_id, occurred_at);
CREATE INDEX idx_defects_run_time ON defect_events(production_run_id, occurred_at);
CREATE INDEX idx_downtime_equipment_time ON downtime_events(equipment_id, started_at);
CREATE INDEX idx_warehouse_product_time ON warehouse_receipts(product_id, received_at);
CREATE INDEX idx_erp_product_time ON erp_production_facts(product_id, occurred_at);
CREATE INDEX idx_payroll_lines_period_employee ON payroll_lines(payroll_period_id, employee_id);
CREATE INDEX idx_audit_record ON audit_log(table_name, record_id, changed_at);

-- ---------- Seed roles / shifts ----------

INSERT INTO roles (code, name) VALUES
('OPERATOR', 'Оператор'),
('ACCOUNTANT_PRODUCTION', 'Учетчик производства'),
('WAREHOUSE', 'Кладовщик'),
('QC', 'ОТК'),
('SHIFT_MASTER', 'Сменный мастер'),
('PRODUCTION_MANAGER', 'Руководитель производства'),
('ECONOMIST', 'Экономист'),
('ADMIN', 'Администратор'),
('MANAGEMENT', 'Руководство')
ON CONFLICT (code) DO NOTHING;

INSERT INTO shift_types (code, name, start_time, end_time, crosses_midnight) VALUES
('DAY', 'День', '09:00', '21:00', false),
('NIGHT', 'Ночь', '21:00', '09:00', true)
ON CONFLICT (code) DO NOTHING;
