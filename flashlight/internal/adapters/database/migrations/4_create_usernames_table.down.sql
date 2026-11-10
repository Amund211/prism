BEGIN;

DROP TABLE IF EXISTS usernames;

DROP INDEX IF EXISTS idx_usernames_username_lowercase;

COMMIT;
