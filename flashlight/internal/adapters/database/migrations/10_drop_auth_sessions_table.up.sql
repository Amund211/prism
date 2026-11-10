-- Sessions are immutable, signed, stateless tokens. Nothing has read or
-- written this table since the cutover; it was kept only so a revert had a
-- table to land on.
--
-- THE ROWS ARE GONE FOR GOOD. There is no backup and the down migration
-- recreates the table empty. Clients recover by logging in again, which
-- costs an anonymous client one proof-of-work handshake.
DROP TABLE IF EXISTS auth_sessions;
