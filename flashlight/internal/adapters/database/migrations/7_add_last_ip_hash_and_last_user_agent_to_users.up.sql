ALTER TABLE users ADD COLUMN last_ip_hash TEXT;
UPDATE users SET last_ip_hash = '';
ALTER TABLE users ALTER COLUMN last_ip_hash SET NOT NULL;

ALTER TABLE users ADD COLUMN last_user_agent TEXT;
UPDATE users SET last_user_agent = '';
ALTER TABLE users ALTER COLUMN last_user_agent SET NOT NULL;
