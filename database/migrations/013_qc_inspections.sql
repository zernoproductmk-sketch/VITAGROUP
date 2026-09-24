-- Explicit QC inspection confirmations, including zero-defect checks.

CREATE TABLE IF NOT EXISTS qc_inspections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    production_run_id uuid NOT NULL REFERENCES production_runs(id) ON DELETE CASCADE,
    checked_at timestamptz NOT NULL,
    result text NOT NULL
        CHECK (result IN ('NO_DEFECT','DEFECT_RECORDED')),
    defect_quantity numeric(18,3) NOT NULL DEFAULT 0
        CHECK (defect_quantity >= 0),
    source_system text NOT NULL DEFAULT 'WEB'
        CHECK (source_system IN ('COVERSE','WEB','SYSTEM')),
    source_record_id text,
    entered_by_user_id uuid REFERENCES users(id),
    comment text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_qc_inspection_source_record
    ON qc_inspections(source_system, source_record_id)
    WHERE source_record_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_qc_inspection_run_time
    ON qc_inspections(production_run_id, checked_at DESC);
