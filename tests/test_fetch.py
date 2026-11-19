"""Tests for skipping unchanged PDFs during a fetch: the size check and the weekly
full download. Uses an in-memory database and a fake size answer, so no network.

Run with: .venv/bin/python -m unittest discover -s tests
"""

import os
import sys
import unittest
from datetime import date, timedelta
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import jobs  # noqa: E402
import scrape  # noqa: E402
import store  # noqa: E402

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


if __name__ == '__main__':
    unittest.main()
