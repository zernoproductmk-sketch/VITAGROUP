-- Support a final incomplete box in production accounting.
ALTER TABLE accounting_control_events
    ADD COLUMN IF NOT EXISTS partial_package_qty numeric(18,3) NOT NULL DEFAULT 0;

ALTER TABLE accounting_control_events
    DROP CONSTRAINT IF EXISTS accounting_control_events_partial_package_qty_check;

ALTER TABLE accounting_control_events
    ADD CONSTRAINT accounting_control_events_partial_package_qty_check
    CHECK (partial_package_qty >= 0);
