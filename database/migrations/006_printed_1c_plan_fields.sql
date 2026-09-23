-- Printed 1C production-task fields discovered in real ERP forms.

ALTER TABLE erp_plan_staging
    ADD COLUMN IF NOT EXISTS product_name text,
    ADD COLUMN IF NOT EXISTS output_unit text,
    ADD COLUMN IF NOT EXISTS route_operation text,
    ADD COLUMN IF NOT EXISTS route_equipment_name text,
    ADD COLUMN IF NOT EXISTS route_equipment_hint text,
    ADD COLUMN IF NOT EXISTS norm_hours numeric(18,6),
    ADD COLUMN IF NOT EXISTS ideal_rate_per_hour numeric(18,6),
    ADD COLUMN IF NOT EXISTS route_operations jsonb NOT NULL DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_erp_plan_staging_task
    ON erp_plan_staging(task_id)
    WHERE task_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_erp_plan_staging_route_equipment
    ON erp_plan_staging(route_equipment_hint)
    WHERE route_equipment_hint IS NOT NULL;
