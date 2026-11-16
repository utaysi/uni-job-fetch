-- Council annotations (notes and tags) and usage counters for the hosted dashboard.
-- Job ads themselves are not stored here; they are identified by their 16-char PDF hash.

CREATE TABLE notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_hash TEXT NOT NULL,
    author TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT
);
CREATE INDEX idx_notes_job_hash ON notes(job_hash);

CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE job_tags (
    job_hash TEXT NOT NULL,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    added_by TEXT NOT NULL,
    added_at TEXT NOT NULL,
    PRIMARY KEY (job_hash, tag_id)
);

-- Per-user daily write counter (protects the free D1 write quota).
CREATE TABLE write_counts (
    email TEXT NOT NULL,
    day TEXT NOT NULL,
    n INTEGER NOT NULL,
    PRIMARY KEY (email, day)
);

-- One row per "Fetch now" click that started a run; enforces the daily limit.
CREATE TABLE fetch_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    day TEXT NOT NULL,
    requested_at TEXT NOT NULL
);
CREATE INDEX idx_fetch_log_day ON fetch_log(day);
