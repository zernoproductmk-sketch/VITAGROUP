-- Coverse master-data synchronization support.

CREATE TABLE master_data_sync_log (
    id bigserial PRIMARY KEY,
    source_system text NOT NULL,
    source_key text NOT NULL,
    source_document_id text NOT NULL,
    source_sheet text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    rows_read integer NOT NULL DEFAULT 0,
    rows_applied integer NOT NULL DEFAULT 0,
    rows_skipped integer NOT NULL DEFAULT 0,
    rows_error integer NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'RUNNING'
        CHECK (status IN ('RUNNING','COMPLETED','COMPLETED_WITH_ERRORS','FAILED','BLOCKED')),
    message text,
    details jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX idx_master_sync_key_time
    ON master_data_sync_log(source_key, started_at DESC);

CREATE TABLE master_data_sync_issues (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_system text NOT NULL,
    source_key text NOT NULL,
    source_document_id text NOT NULL,
    source_sheet text NOT NULL,
    source_row integer,
    issue_code text NOT NULL,
    severity text NOT NULL DEFAULT 'ERROR'
        CHECK (severity IN ('INFO','WARNING','ERROR')),
    message text NOT NULL,
    raw_data jsonb,
    status text NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN','RESOLVED','IGNORED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz
);

CREATE INDEX idx_master_sync_issues_open
    ON master_data_sync_issues(status, source_key, severity);

-- Flexible tariff rules copied from Coverse tariff grid.
CREATE TABLE payroll_rate_rules (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    accrual_type text NOT NULL,
    role_name text,
    equipment_id uuid REFERENCES equipment(id),
    equipment_external_code text,
    product_type text,
    print_flag text,
    tariff_group text,
    unit text NOT NULL,
    rate numeric(18,6) NOT NULL CHECK (rate >= 0),
    payment_type text,
    valid_from date NOT NULL,
    valid_to date,
    source_system text NOT NULL DEFAULT 'COVERSE',
    source_document_id text,
    source_sheet text,
    source_row integer,
    source_record_key text NOT NULL UNIQUE,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE INDEX idx_payroll_rate_rules_lookup
    ON payroll_rate_rules(equipment_id, role_name, valid_from, valid_to);

-- Warehouse/product code mappings remain explicit instead of overloading products.code.
CREATE TABLE product_external_codes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    source_system text NOT NULL,
    code_type text NOT NULL,
    external_code text NOT NULL,
    is_primary boolean NOT NULL DEFAULT false,
    is_active boolean NOT NULL DEFAULT true,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_system, code_type, external_code)
);

CREATE INDEX idx_product_external_codes_product
    ON product_external_codes(product_id, is_active);
