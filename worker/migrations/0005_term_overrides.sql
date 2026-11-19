-- Contract duration (months) and hours per month entered by council members on
-- the hosted dashboard. A row replaces the value detected from the ad
-- (src/terms.py) for that ad and field. Deleting the row goes back to the
-- detected value.

CREATE TABLE term_overrides (
    job_hash TEXT NOT NULL,
    field TEXT NOT NULL CHECK (field IN ('duration', 'hours')),
    value REAL NOT NULL CHECK (value > 0),
    set_by TEXT NOT NULL,
    set_at TEXT NOT NULL,
    PRIMARY KEY (job_hash, field)
);
