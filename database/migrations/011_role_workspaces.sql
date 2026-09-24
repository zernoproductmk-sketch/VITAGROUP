-- Role-specific operational workspaces.

CREATE TABLE IF NOT EXISTS accounting_control_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    production_run_id uuid REFERENCES production_runs(id),
    shift_id uuid NOT NULL REFERENCES shifts(id),
    equipment_id uuid REFERENCES equipment(id),
    product_id uuid NOT NULL REFERENCES products(id),
    observed_at timestamptz NOT NULL,
    ticket_no text,
    packages_qty numeric(18,3) CHECK (packages_qty IS NULL OR packages_qty >= 0),
    qty_per_package numeric(18,3) CHECK (qty_per_package IS NULL OR qty_per_package >= 0),
    quantity numeric(18,3) NOT NULL CHECK (quantity >= 0),
    source_system text NOT NULL DEFAULT 'WEB'
        CHECK (source_system IN ('COVERSE','WEB','SYSTEM')),
    source_record_id text,
    entered_by_user_id uuid REFERENCES users(id),
    comment text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_accounting_control_source_record
    ON accounting_control_events(source_system, source_record_id)
    WHERE source_record_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_accounting_control_shift_time
    ON accounting_control_events(shift_id, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_accounting_control_run
    ON accounting_control_events(production_run_id)
    WHERE production_run_id IS NOT NULL;
