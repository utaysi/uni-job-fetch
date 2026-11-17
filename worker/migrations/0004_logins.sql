-- Logins to the hosted dashboard, shown only to the board owner (ADMIN_EMAILS) in the
-- Members panel. One row per Cloudflare Access session: login_at is when Access issued
-- the session's token (the login), last_seen_at the latest page load in that session.

CREATE TABLE logins (
    email TEXT NOT NULL,
    login_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (email, login_at)
);
