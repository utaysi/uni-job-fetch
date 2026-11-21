"""Tests for a fetch: skipping unchanged PDFs (the size check and the weekly full
download), and a whole fetch of a central job board ad. Uses a temporary folder or an
in-memory database and fake network answers, so no network or browser is needed.

Run with: .venv/bin/python -m unittest discover -s tests
"""

import io
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))

import jobs  # noqa: E402
import posting  # noqa: E402
import scrape  # noqa: E402
import store  # noqa: E402
from test_posting import page  # noqa: E402

URL = 'https://www.uni-marburg.de/de/fb12/a.pdf'
TODAY = date(2026, 11, 20)


def known(downloaded_at):
    return {'downloaded_at': downloaded_at}


class FullDownloadDue(unittest.TestCase):
    def test_not_twice_on_the_same_day(self):
        self.assertFalse(jobs.full_download_due(URL, known('2026-11-20T06:00:00'), TODAY))

    def test_after_a_week_always(self):
        self.assertTrue(jobs.full_download_due(URL, known('2026-11-13T06:00:00'), TODAY))
        self.assertTrue(jobs.full_download_due(URL, known('2026-10-01T06:00:00'), TODAY))

    def test_unreadable_date_downloads(self):
        self.assertTrue(jobs.full_download_due(URL, known(''), TODAY))

    def test_once_within_a_week_on_the_link_s_own_day(self):
        last = TODAY - timedelta(days=1)
        for n in range(200):
            url = f'{URL}?n={n}'
            due = [jobs.full_download_due(url, known(last.isoformat()), last + timedelta(days=d))
                   for d in range(1, 8)]
            # At most one day within the week (or none if its day was the day of the
            # last download), and always once a week has passed.
            self.assertLessEqual(sum(due[:6]), 1, url)
            self.assertTrue(due[6], url)

    def test_spread_over_the_days(self):
        # Downloaded yesterday: in the next six days each link is due only on its own day.
        last = known((TODAY - timedelta(days=1)).isoformat())
        due_days = set()
        for n in range(100):
            url = f'{URL}?n={n}'
            due_days.update(d for d in range(6) if jobs.full_download_due(url, last, TODAY + timedelta(days=d)))
        self.assertEqual(due_days, set(range(6)))


class UnchangedHash(unittest.TestCase):
    def setUp(self):
        self.conn = store.connect(':memory:')
        fields = {k: '' for k in store.PARSED_FIELDS}
        fields.update(emails=[], phones=[])
        store.insert_job(self.conn, 'abc123', fields, 'a', 1, 'a.pdf', '2026-11-19T15:00:00')
        store.remember_url(self.conn, URL, 'abc123', 1000, '2026-11-19T15:00:00')
        # A day on which this link is not due for its weekly full download.
        self.today = next(TODAY + timedelta(days=d) for d in range(7)
                          if not jobs.full_download_due(URL, store.known_url(self.conn, URL), TODAY + timedelta(days=d)))

    def check(self, size, expected, today=None):
        with mock.patch.object(scrape, 'size', side_effect=size if callable(size) else lambda url: size) as asked:
            self.assertEqual(jobs.unchanged_hash(self.conn, URL, today or self.today), expected)
        return asked

    def test_same_size_skips_the_download(self):
        self.check(1000, 'abc123')

    def test_other_size_downloads(self):
        self.check(1001, None)
        self.check(None, None)

    def test_size_check_failure_downloads(self):
        def fail(url):
            raise scrape.HTTPStatusError(403, 'Forbidden', url)
        self.check(fail, None)
        def timeout(url):
            raise TimeoutError('timed out')
        self.check(timeout, None)

    def test_unknown_link_downloads_without_asking(self):
        asked = mock.Mock()
        with mock.patch.object(scrape, 'size', asked):
            self.assertIsNone(jobs.unchanged_hash(self.conn, URL + '?new', self.today))
        asked.assert_not_called()

    def test_weekly_full_download_without_asking(self):
        asked = self.check(1000, None, today=TODAY + timedelta(days=8))
        asked.assert_not_called()

    def test_removed_ad_downloads(self):
        self.conn.execute("DELETE FROM jobs WHERE hash='abc123'")
        self.check(1000, None)

    def test_remember_url_replaces_the_old_entry(self):
        store.remember_url(self.conn, URL, 'def456', 2000, '2026-11-20T06:00:00')
        row = store.known_url(self.conn, URL)
        self.assertEqual((row['hash'], row['size'], row['downloaded_at']), ('def456', 2000, '2026-11-20T06:00:00'))



class FetchCentralAd(unittest.TestCase):
    """A whole fetch of one ad of the central job board, without network or browser."""

    URL = 'https://stellenangebote.uni-marburg.de/jobposting/0123456789abcdef'

    def setUp(self):
        self.cwd = os.getcwd()
        self.tmp = tempfile.TemporaryDirectory()
        os.chdir(self.tmp.name)
        os.makedirs('data')

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def fetch(self, html, size=None):
        """Run `fetch` with the board listing one ad whose page is html; returns the output."""
        data = html.encode('utf-8')
        board = [{'href': self.URL, 'url': self.URL, 'department': 'Department 20 Medicine',
                  'original_name': 'fb20-0001-shk-2026', 'posting': True}]
        out = io.TextIOWrapper(io.BytesIO(), encoding='utf-8')
        with mock.patch.object(scrape, 'discover_all', return_value=board), \
                mock.patch.object(scrape, 'download', return_value=data) as self.download, \
                mock.patch.object(scrape, 'size', return_value=len(data) if size is None else size), \
                mock.patch.object(scrape, 'close'), mock.patch.object(scrape, 'timing_summary', return_value=[]), \
                mock.patch.object(posting, 'find_browser', return_value=None), \
                mock.patch.object(sys, 'stdout', out):
            self.assertEqual(jobs.cmd_fetch(None), 0)
        out.flush()
        return out.buffer.getvalue().decode('utf-8')

    def rows(self):
        conn = store.connect()
        try:
            return [dict(r) for r in conn.execute('SELECT * FROM jobs ORDER BY first_seen, rowid')]
        finally:
            conn.close()

    def test_new_ad_is_saved_as_a_pdf_and_read(self):
        output = self.fetch(page())
        self.assertIn('no browser found', output)
        self.assertRegex(output, r'NEW \S+_fb20-0001-shk-2026_1\.pdf \(plain PDF\)')
        [row] = self.rows()
        self.assertEqual(row['hash'], posting.read(page()).hash)
        self.assertEqual((row['job_id'], row['department'], row['status']),
                         ('fb20-0001-shk-2026', 'Department 20 Medicine', 'Online'))
        self.assertEqual((row['application_deadline_iso'], row['duration_of_contract'], row['workload']),
                         ('2026-11-29', '1 Jahr', '40 Std./Monat'))
        with open(os.path.join('data', 'pdfs', row['pdf_filename']), 'rb') as f:
            self.assertTrue(f.read().startswith(b'%PDF'))
        conn = store.connect()
        self.assertEqual(store.known_url(conn, self.URL)['size'], len(page().encode('utf-8')))
        conn.close()

    def test_same_ad_again_is_not_new(self):
        self.fetch(page())
        output = self.fetch(page())  # same size: not even downloaded
        self.download.assert_not_called()
        self.assertIn('not downloaded: same size', output)
        self.fetch(page(), size=1)   # downloaded again, same content: the same ad
        self.download.assert_called_once()
        [row] = self.rows()
        self.assertEqual(row['status'], 'Online')

    def test_changed_ad_is_a_new_one_and_the_old_goes_offline(self):
        self.fetch(page())
        self.fetch(page(extra='Neu: auch remote.'), size=1)
        old, new = self.rows()
        self.assertEqual((old['status'], new['status']), ('Offline', 'Online'))
        self.assertNotEqual(old['hash'], new['hash'])

    def test_page_without_an_ad_is_an_error(self):
        output = self.fetch('<html><body>Wartungsarbeiten</body></html>')
        self.assertIn('skipped (not a job posting page', output)
        self.assertIn('Errors/skipped: 1', output)
        self.assertEqual(self.rows(), [])


if __name__ == '__main__':
    unittest.main()
