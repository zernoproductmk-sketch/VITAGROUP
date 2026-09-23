-- Fix source deduplication: manual/system records may have NULL external IDs.
-- Uniqueness applies only when an external source_record_id is present.

ALTER TABLE production_output_events
    DROP CONSTRAINT IF EXISTS production_output_events_source_system_source_record_id_key;
ALTER TABLE defect_events
    DROP CONSTRAINT IF EXISTS defect_events_source_system_source_record_id_key;
ALTER TABLE downtime_events
    DROP CONSTRAINT IF EXISTS downtime_events_source_system_source_record_id_key;
ALTER TABLE warehouse_receipts
    DROP CONSTRAINT IF EXISTS warehouse_receipts_source_system_source_record_id_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_output_source_record
    ON production_output_events(source_system, source_record_id)
    WHERE source_record_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_defect_source_record
    ON defect_events(source_system, source_record_id)
    WHERE source_record_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_downtime_source_record
    ON downtime_events(source_system, source_record_id)
    WHERE source_record_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_warehouse_source_record
    ON warehouse_receipts(source_system, source_record_id)
    WHERE source_record_id IS NOT NULL;
