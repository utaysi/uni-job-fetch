"""Dashboard HTTP server.

Serves the static dashboard (web/) and a live JSON view of the DB at
/api/jobs.json (also /api/jobs) and the stored PDFs under /pdfs/ (on disk in
data/pdfs/). No data file is written to disk; the DB is queried per request so
the dashboard always reflects the current state.

This local server is read-only. Notes, tags and the fetch button only exist on
the hosted dashboard (see worker/ and docs/TECHNICAL.md); the page hides them
when it runs here.
"""

import http.server
import json
import os
import posixpath
import urllib.parse
from datetime import timedelta

import deadline
import store

PORT = 8080


def jobs_payload(conn):
    """All ads as plain dicts with effective (override-merged) field values."""
    out = []
    for row in store.all_jobs(conn):
        item = {
            'hash': row['hash'],
            'status': row['status'],
            'first_seen': row['first_seen'],
            'last_seen': row['last_seen'],
            'original_pdf_name': row['original_pdf_name'],
            'pdf_filename': row['pdf_filename'],
            'pdf': f'pdfs/{row["pdf_filename"]}' if row['pdf_filename'] else '',
            'needs_review': bool(row['needs_review']),
            'template': row['template'],
        }
        for field in ['job_id', 'department', 'working_group', 'position_title',
                      'position_start_date', 'application_deadline',
                      'duration_of_contract', 'pay', 'workload', 'contact_name']:
            item[field] = store.effective(row, field)
        item['emails'] = store.effective(row, 'emails')
        item['phones'] = store.effective(row, 'phones')
        item.update(deadline_fields(row))
        out.append(item)
    return out


def deadline_fields(row):
    """How the dashboard shows the deadline: kind, date, and the text for the card.

    deadline_kind is one of date, relative, rolling, none, unknown, text (see
    deadline.py). deadline_iso is the date to count down to; for "relative" it is
    estimated from the day the ad was first seen.
    """
    first_seen = store.first_seen_date(row)
    dl = deadline.detect(store.effective(row, 'application_deadline'), row['full_text'] or '',
                         ref=first_seen, trust_box=store.has_override(row, 'application_deadline'))
    iso = dl.iso
    if dl.kind == 'relative' and first_seen:
        iso = (first_seen + timedelta(days=dl.days)).isoformat()
    return {
        'application_deadline': dl.value,
        'deadline_kind': dl.kind,
        'deadline_iso': iso,
        'deadline_days': dl.days,
    }


def make_handler(db_path):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def _send_json(self, data):
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split('?')[0]
            if path in ('/api/jobs', '/api/jobs.json'):
                conn = store.connect(db_path)
                try:
                    self._send_json(jobs_payload(conn))
                finally:
                    conn.close()
                return
            if path == '/api/me':
                # No login locally: the page sees no user and stays read-only.
                self._send_json({'email': None})
                return
            super().do_GET()

        def translate_path(self, path):
            # The dashboard lives in web/ and the PDFs in data/pdfs/, but they are
            # served from a single URL space rooted at the project directory (cwd).
            # Map the URL onto disk: /pdfs/... -> data/pdfs/..., everything else
            # -> web/... (so '/' resolves to web/index.html).
            clean = urllib.parse.unquote(path.split('?', 1)[0].split('#', 1)[0])
            rel = posixpath.normpath(clean).lstrip('/')
            if rel == 'pdfs' or rel.startswith('pdfs/'):
                base = os.path.join(os.getcwd(), 'data')
            else:
                base = os.path.join(os.getcwd(), 'web')
            return os.path.join(base, *rel.split('/'))

        def log_message(self, *args):
            pass  # quiet

    return Handler


def serve(db_path=store.DB_PATH, port=PORT):
    handler = make_handler(db_path)
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', port), handler)
    print(f'Dashboard at http://localhost:{port}  (Ctrl+C to stop)')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
    finally:
        httpd.server_close()
