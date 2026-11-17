-- Deadlines corrected by council members on the hosted dashboard. A row replaces
-- the deadline detected from the ad (src/deadline.py) for that ad: either a date
-- or "none" (no deadline). Deleting the row goes back to the detected deadline.

CREATE TABLE deadline_overrides (
    job_hash TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('date', 'none')),
    deadline TEXT CHECK ((kind = 'date') = (deadline IS NOT NULL)),
    set_by TEXT NOT NULL,
    set_at TEXT NOT NULL
);
