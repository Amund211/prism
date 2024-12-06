BEGIN;

ALTER TABLE stats ALTER COLUMN data_format_version DROP NOT NULL;

UPDATE stats SET data_format_version=NULL WHERE data_format_version='0';

COMMIT;
