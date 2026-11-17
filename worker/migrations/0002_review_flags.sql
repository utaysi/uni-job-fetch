-- Council decisions on the "needs review" mark. The parser (or the owner's Excel
-- round-trip) sets the mark in jobs.db; a row here overrides it for that ad, in
-- both directions, and records who changed it last.

CREATE TABLE review_flags (
    job_hash TEXT PRIMARY KEY,
    needs_review INTEGER NOT NULL CHECK (needs_review IN (0, 1)),
    set_by TEXT NOT NULL,
    set_at TEXT NOT NULL
);
