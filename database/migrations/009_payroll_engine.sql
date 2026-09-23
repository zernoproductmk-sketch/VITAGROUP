-- Piecework payroll calculation engine.

ALTER TABLE employee_shift_assignments
    ADD COLUMN IF NOT EXISTS production_run_id uuid REFERENCES production_runs(id),
    ADD COLUMN IF NOT EXISTS allocation_confirmed boolean NOT NULL DEFAULT false;

CREATE UNIQUE INDEX IF NOT EXISTS uq_assignment_run_employee
    ON employee_shift_assignments(production_run_id, employee_id)
    WHERE production_run_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_assignment_run
    ON employee_shift_assignments(production_run_id)
    WHERE production_run_id IS NOT NULL;

ALTER TABLE payroll_periods
    ADD COLUMN IF NOT EXISTS quantity_basis text
        CHECK (
            quantity_basis IS NULL
            OR quantity_basis IN ('OUTPUT','QC_GOOD','WAREHOUSE','ERP')
        ),
    ADD COLUMN IF NOT EXISTS notes text;

CREATE UNIQUE INDEX IF NOT EXISTS uq_payroll_period_dates
    ON payroll_periods(date_from, date_to);

ALTER TABLE payroll_lines
    ALTER COLUMN operation_id DROP NOT NULL;

ALTER TABLE payroll_lines
    ADD COLUMN IF NOT EXISTS rate_rule_id uuid REFERENCES payroll_rate_rules(id),
    ADD COLUMN IF NOT EXISTS quantity_basis text
        CHECK (
            quantity_basis IS NULL
            OR quantity_basis IN ('OUTPUT','QC_GOOD','WAREHOUSE','ERP')
        ),
    ADD COLUMN IF NOT EXISTS source_quantity numeric(18,3),
    ADD COLUMN IF NOT EXISTS calculation_status text NOT NULL DEFAULT 'READY'
        CHECK (calculation_status IN ('READY','PRELIMINARY')),
    ADD COLUMN IF NOT EXISTS calculation_details jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE UNIQUE INDEX IF NOT EXISTS uq_payroll_line_period_employee_run
    ON payroll_lines(payroll_period_id, employee_id, production_run_id)
    WHERE production_run_id IS NOT NULL;

CREATE TABLE product_payroll_attributes (
    product_id uuid PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE,
    product_type text,
    print_flag text,
    tariff_group text,
    confirmed boolean NOT NULL DEFAULT false,
    source_system text NOT NULL DEFAULT 'WEB',
    source_record_id text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by_user_id uuid REFERENCES users(id)
);
