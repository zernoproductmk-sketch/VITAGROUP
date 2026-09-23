-- External integration staging layer.
-- Keeps source data safely before ERP/product/equipment references are fully resolved.

CREATE TABLE external_event_staging (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_system text NOT NULL,
    event_type text NOT NULL,
    source_document_id text NOT NULL,
    source_sheet text,
    source_row integer,
    source_record_key text NOT NULL UNIQUE,
    response_at timestamptz,
    business_date date,
    shift_code text CHECK (shift_code IS NULL OR shift_code IN ('DAY','NIGHT')),
    occurred_at timestamptz,
    personnel_number text,
    equipment_code text,
    order_no text,
    article_code text,
    ticket_no text,
    quantity numeric(18,3),
    secondary_quantity numeric(18,3),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    processing_status text NOT NULL DEFAULT 'PENDING'
        CHECK (processing_status IN ('PENDING','RESOLVED','ERROR','IGNORED')),
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_external_staging_type_time
    ON external_event_staging(event_type, occurred_at DESC);

CREATE INDEX idx_external_staging_status
    ON external_event_staging(processing_status, event_type);

CREATE INDEX idx_external_staging_business_shift
    ON external_event_staging(business_date, shift_code);

CREATE TABLE integration_sync_state (
    source_system text NOT NULL,
    source_key text NOT NULL,
    source_document_id text NOT NULL,
    last_source_row integer,
    last_revision_id text,
    last_sync_at timestamptz,
    last_success_at timestamptz,
    last_error text,
    PRIMARY KEY (source_system, source_key)
);
