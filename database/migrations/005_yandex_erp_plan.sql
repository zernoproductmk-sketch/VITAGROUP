-- Yandex Disk / ERP production-plan staging.

CREATE TABLE erp_plan_import_batches (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_system text NOT NULL DEFAULT 'YANDEX_DISK',
    source_file_name text,
    source_file_modified timestamptz,
    source_file_size bigint,
    source_public_key_hash text,
    source_sheet text,
    status text NOT NULL DEFAULT 'RUNNING'
        CHECK (status IN ('RUNNING','COMPLETED','COMPLETED_WITH_ERRORS','BLOCKED','FAILED')),
    rows_read integer NOT NULL DEFAULT 0,
    rows_applied integer NOT NULL DEFAULT 0,
    rows_skipped integer NOT NULL DEFAULT 0,
    rows_error integer NOT NULL DEFAULT 0,
    message text,
    mapping jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE INDEX idx_erp_plan_batches_created
    ON erp_plan_import_batches(created_at DESC);

CREATE TABLE erp_plan_staging (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    import_batch_id uuid NOT NULL REFERENCES erp_plan_import_batches(id) ON DELETE CASCADE,
    source_system text NOT NULL DEFAULT 'YANDEX_DISK',
    source_file_name text NOT NULL,
    source_sheet text NOT NULL,
    source_row integer NOT NULL,
    source_record_key text NOT NULL UNIQUE,

    erp_guid text,
    task_id text,
    business_date date,
    shift_code text CHECK (shift_code IS NULL OR shift_code IN ('DAY','NIGHT')),
    workshop text,
    equipment_code text,
    order_no text,
    article text,
    customer text,
    tech_card text,
    plan_qty_pcs numeric(18,3),
    pcs_per_box numeric(18,3),
    boxes_per_pallet numeric(18,3),
    plan_kg numeric(18,3),
    source_status text,

    raw_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    row_status text NOT NULL DEFAULT 'PENDING'
        CHECK (row_status IN ('PENDING','VALID','PARTIAL','ERROR','IGNORED')),
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_erp_plan_staging_date
    ON erp_plan_staging(business_date, shift_code);

CREATE INDEX idx_erp_plan_staging_order
    ON erp_plan_staging(order_no)
    WHERE order_no IS NOT NULL;

CREATE INDEX idx_erp_plan_staging_article
    ON erp_plan_staging(article)
    WHERE article IS NOT NULL;
