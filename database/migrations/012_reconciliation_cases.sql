-- Shift reconciliation cases and explanations.

CREATE TABLE IF NOT EXISTS reconciliation_cases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    production_run_id uuid NOT NULL UNIQUE
        REFERENCES production_runs(id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN','EXPLAINED','RESOLVED')),
    reason_code text,
    comment text,
    created_by_user_id uuid REFERENCES users(id),
    updated_by_user_id uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_reconciliation_cases_status
    ON reconciliation_cases(status, updated_at DESC);
