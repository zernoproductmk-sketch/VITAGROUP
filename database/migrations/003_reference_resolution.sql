-- Reference resolution layer for external production events.

ALTER TABLE external_event_staging
    ADD COLUMN IF NOT EXISTS shift_id uuid REFERENCES shifts(id),
    ADD COLUMN IF NOT EXISTS employee_id uuid REFERENCES employees(id),
    ADD COLUMN IF NOT EXISTS equipment_id uuid REFERENCES equipment(id),
    ADD COLUMN IF NOT EXISTS product_id uuid REFERENCES products(id),
    ADD COLUMN IF NOT EXISTS production_order_id uuid REFERENCES production_orders(id),
    ADD COLUMN IF NOT EXISTS production_run_id uuid REFERENCES production_runs(id),
    ADD COLUMN IF NOT EXISTS linked_staging_id uuid REFERENCES external_event_staging(id),
    ADD COLUMN IF NOT EXISTS good_quantity numeric(18,3),
    ADD COLUMN IF NOT EXISTS ended_at timestamptz,
    ADD COLUMN IF NOT EXISTS resolution_status text NOT NULL DEFAULT 'UNRESOLVED'
        CHECK (resolution_status IN ('UNRESOLVED','PARTIAL','RESOLVED','ERROR')),
    ADD COLUMN IF NOT EXISTS resolution_details jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS resolved_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_external_staging_resolution
    ON external_event_staging(resolution_status, event_type, business_date);

CREATE INDEX IF NOT EXISTS idx_external_staging_ticket
    ON external_event_staging(ticket_no)
    WHERE ticket_no IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_external_staging_refs
    ON external_event_staging(employee_id, equipment_id, product_id);

CREATE TABLE external_reference_aliases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_system text NOT NULL,
    entity_type text NOT NULL
        CHECK (entity_type IN ('EMPLOYEE','EQUIPMENT','PRODUCT','PRODUCTION_ORDER')),
    external_code text NOT NULL,
    entity_id uuid NOT NULL,
    canonical_label text,
    is_active boolean NOT NULL DEFAULT true,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_system, entity_type, external_code)
);

CREATE TABLE resolution_issues (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    staging_event_id uuid NOT NULL REFERENCES external_event_staging(id) ON DELETE CASCADE,
    issue_code text NOT NULL,
    field_name text,
    external_value text,
    message text NOT NULL,
    status text NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN','RESOLVED','IGNORED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    UNIQUE (staging_event_id, issue_code, field_name)
);

CREATE INDEX IF NOT EXISTS idx_resolution_issues_open
    ON resolution_issues(status, issue_code);
