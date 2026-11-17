"""SQLite data layer for the job-ad repository.

The database (jobs.db) is the single source of truth. Identity is the content
hash of the PDF bytes. Parsed fields are stored as columns; manual corrections
live in a JSON `overrides` column so a fix is never stomped and we can always
tell "parsed" from "fixed". `effective_*` helpers merge the two.
"""

import json
import os
import sqlite3
from datetime import datetime

DB_PATH = 'data/jobs.db'

# Parsed field columns (everything the extractor produces that we persist).
PARSED_FIELDS = [
    'job_id', 'department', 'working_group', 'position_title',
    'position_start_date', 'position_start_date_iso',
    'application_deadline', 'application_deadline_iso',
    'duration_of_contract', 'pay', 'workload',
    'contact_name', 'emails', 'phones', 'full_text', 'template',
]

# Fields a user may correct via the Excel round-trip (subset of parsed + notes).
OVERRIDABLE_FIELDS = [
    'job_id', 'department', 'working_group', 'position_title',
    'position_start_date', 'application_deadline', 'duration_of_contract',
    'pay', 'workload', 'contact_name', 'emails', 'phones',
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    hash TEXT PRIMARY KEY,
    original_pdf_name TEXT,
    count_of_pdf_from_first_seen_date INTEGER,
    pdf_filename TEXT,
    first_seen TEXT,
    last_seen TEXT,
    status TEXT,
    job_id TEXT,
    department TEXT,
    working_group TEXT,
    position_title TEXT,
    position_start_date TEXT,
    position_start_date_iso TEXT,
    application_deadline TEXT,
    application_deadline_iso TEXT,
    duration_of_contract TEXT,
    pay TEXT,
    workload TEXT,
    contact_name TEXT,
    emails TEXT,
    phones TEXT,
    full_text TEXT,
    template TEXT,
    needs_review INTEGER,
    notes TEXT,
    overrides TEXT
);
"""


def connect(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    return conn


def now_iso():
    return datetime.now().isoformat(timespec='seconds')


def today():
    return datetime.now().strftime('%Y-%m-%d')


def exists(conn, hash_):
    return conn.execute('SELECT 1 FROM jobs WHERE hash=?', (hash_,)).fetchone() is not None


def next_count_for_date(conn, date_str):
    """Sequence number among ads first seen on date_str (1-based)."""
    row = conn.execute(
        'SELECT COUNT(*) AS c FROM jobs WHERE substr(first_seen,1,10)=?',
        (date_str,)).fetchone()
    return row['c'] + 1


def insert_job(conn, hash_, fields, original_pdf_name, count, pdf_filename, seen_at):
    """Insert a brand-new ad. `fields` is the extractor output dict."""
    data = {
        'hash': hash_,
        'original_pdf_name': original_pdf_name,
        'count_of_pdf_from_first_seen_date': count,
        'pdf_filename': pdf_filename,
        'first_seen': seen_at,
        'last_seen': seen_at,
        'status': 'Online',
        'needs_review': 1 if fields.get('needs_review') else 0,
        'notes': '',
        'overrides': '{}',
    }
    for key in PARSED_FIELDS:
        val = fields.get(key, '')
        if key in ('emails', 'phones'):
            val = json.dumps(val or [], ensure_ascii=False)
        data[key] = val
    cols = ', '.join(data)
    placeholders = ', '.join('?' for _ in data)
    conn.execute(f'INSERT INTO jobs ({cols}) VALUES ({placeholders})', list(data.values()))


def mark_seen(conn, hash_, seen_at):
    conn.execute('UPDATE jobs SET last_seen=?, status=? WHERE hash=?',
                 (seen_at, 'Online', hash_))


def set_deadline(conn, hash_, value, iso):
    """Store a re-detected deadline (the parsed value; manual overrides stay as they are)."""
    conn.execute('UPDATE jobs SET application_deadline=?, application_deadline_iso=? WHERE hash=?',
                 (value, iso, hash_))


def first_seen_date(row):
    """The date an ad was first seen, or None."""
    try:
        return datetime.strptime((row['first_seen'] or '')[:10], '%Y-%m-%d').date()
    except ValueError:
        return None


def has_override(row, field):
    return field in _overrides(row)


def mark_offline_missing(conn, seen_hashes):
    """Flip every ad not in seen_hashes to Offline. Returns count flipped."""
    rows = conn.execute("SELECT hash FROM jobs WHERE status='Online'").fetchall()
    flipped = 0
    for row in rows:
        if row['hash'] not in seen_hashes:
            conn.execute("UPDATE jobs SET status='Offline' WHERE hash=?", (row['hash'],))
            flipped += 1
    return flipped


def _overrides(row):
    try:
        return json.loads(row['overrides'] or '{}')
    except (ValueError, TypeError):
        return {}


def effective(row, field):
    """Effective value of a field: override if present, else parsed."""
    ov = _overrides(row)
    if field in ov:
        return ov[field]
    val = row[field] if field in row.keys() else ''
    if field in ('emails', 'phones'):
        try:
            return json.loads(val or '[]')
        except (ValueError, TypeError):
            return []
    return val or ''


def apply_overrides(conn, hash_, new_values, notes=None, needs_review=None):
    """Persist manual corrections for a job.

    new_values maps overridable field -> corrected value. Only values that
    differ from the parsed value are stored as overrides; values reset to match
    the parsed value clear the override.
    """
    row = conn.execute('SELECT * FROM jobs WHERE hash=?', (hash_,)).fetchone()
    if row is None:
        return False
    ov = _overrides(row)
    for field, value in new_values.items():
        if field not in OVERRIDABLE_FIELDS:
            continue
        parsed = row[field] if field in row.keys() else ''
        if field in ('emails', 'phones'):
            try:
                parsed = json.loads(parsed or '[]')
            except (ValueError, TypeError):
                parsed = []
        if value == parsed:
            ov.pop(field, None)
        else:
            ov[field] = value
    sets = ['overrides=?']
    params = [json.dumps(ov, ensure_ascii=False)]
    if notes is not None:
        sets.append('notes=?')
        params.append(notes)
    if needs_review is not None:
        sets.append('needs_review=?')
        params.append(1 if needs_review else 0)
    params.append(hash_)
    conn.execute(f'UPDATE jobs SET {", ".join(sets)} WHERE hash=?', params)
    return True


def all_jobs(conn):
    return conn.execute('SELECT * FROM jobs ORDER BY first_seen DESC, '
                        'count_of_pdf_from_first_seen_date DESC').fetchall()


def stats(conn):
    total = conn.execute('SELECT COUNT(*) AS c FROM jobs').fetchone()['c']
    online = conn.execute("SELECT COUNT(*) AS c FROM jobs WHERE status='Online'").fetchone()['c']
    review = conn.execute('SELECT COUNT(*) AS c FROM jobs WHERE needs_review=1').fetchone()['c']
    return {'total': total, 'online': online, 'offline': total - online, 'needs_review': review}
