-- Interactive shift assignment report for accountant workspace.

ALTER TABLE production_runs
    ADD COLUMN IF NOT EXISTS shift_assignment_report jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS shift_assignment_report_updated_at timestamptz,
    ADD COLUMN IF NOT EXISTS shift_assignment_report_updated_by uuid REFERENCES users(id);
