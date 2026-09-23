-- Resolve ERP plan staging into production orders and runs.

ALTER TABLE erp_plan_staging
    ADD COLUMN IF NOT EXISTS product_id uuid REFERENCES products(id),
    ADD COLUMN IF NOT EXISTS equipment_id uuid REFERENCES equipment(id),
    ADD COLUMN IF NOT EXISTS shift_id uuid REFERENCES shifts(id),
    ADD COLUMN IF NOT EXISTS production_order_id uuid REFERENCES production_orders(id),
    ADD COLUMN IF NOT EXISTS production_run_id uuid REFERENCES production_runs(id),
    ADD COLUMN IF NOT EXISTS promotion_status text NOT NULL DEFAULT 'UNRESOLVED'
        CHECK (promotion_status IN ('UNRESOLVED','PARTIAL','ORDER_CREATED','RUN_CREATED','ERROR')),
    ADD COLUMN IF NOT EXISTS promotion_details jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS promoted_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_erp_plan_staging_promotion
    ON erp_plan_staging(promotion_status, business_date);

CREATE INDEX IF NOT EXISTS idx_erp_plan_staging_order_fk
    ON erp_plan_staging(production_order_id)
    WHERE production_order_id IS NOT NULL;
