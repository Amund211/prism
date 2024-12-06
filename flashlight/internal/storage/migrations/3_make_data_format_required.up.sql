BEGIN;

UPDATE stats SET data_format_version=0 WHERE data_format_version IS NULL;

ALTER TABLE stats ALTER COLUMN data_format_version SET NOT NULL;

COMMIT;
