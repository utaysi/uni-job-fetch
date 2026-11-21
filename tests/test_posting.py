"""Tests for saving the central job board's web-page ads as PDFs: cleaning the page,
the hash that identifies an ad, the plain PDF and the browser print with its fallback.

The page below copies the structure of the board's ad pages with made-up content.
No browser and no network are needed: the browser is replaced by a fake.

Run with: .venv/bin/python -m unittest discover -s tests
"""

import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import extract  # noqa: E402
import posting  # noqa: E402

URL = 'https://stellenangebote.uni-marburg.de/jobposting/0123456789abcdef'

FIELD = '''<div class="__bjp-content--block-20">
  <img class="__bjp-content--icon" src="https://jobs.b-ite.com/api/v1/assets/{n}.svg" alt="Img">
  <p class="__bjp-content--block-20--text"> <b>{label}:<br></b> {value} </p>
</div>'''

PAGE = '''<!DOCTYPE html>
<html lang="de"><head><title>Studentische Hilfskraft | Universität Marburg</title>
<link href="https://jobs-cdn.b-ite.com/modern/job-posting.css" rel="stylesheet">
<style>.x {{ color: red }}</style><script>var tracking = "Bewerbungsfrist: 01.01.2000";</script>
</head><body>
<nav>Navigation der Seite</nav>
<div class="__bjp-jobofferWrapper">
  <div class="__bjp-content--header image-container">
    <img class="__bjp-banner" src="https://jobs.b-ite.com/api/v1/assets/{banner}.png" alt="Image">
    <p class="id overlay"> Ausschreibungs-ID:<br> fb20-0001-shk-2026 </p>
  </div>
  <div class="__bjp-content--content">
    <div class="__bjp-content--content--columns">
      {fields}
    </div>
    <div class="__bjp-content--content--in">
      <p style="padding-top: 2px">Am Fachbereich Medizin, Klinik f&uuml;r Beispiele, ist zum n&auml;chstm&ouml;glichen
      Zeitpunkt eine Stelle (40 Std./Monat) als</p>
      <h1>Studentische Hilfskraft</h1>
      <p>zu besetzen. {extra}</p>
      <h2>Ihre Aufgaben:</h2>
      <ul><li>Unterst&uuml;tzung bei Studien</li><li>Pflege von <a href="https://example.org/">Webseiten</a></li></ul>
      <button onclick="apply()">Jetzt bewerben</button>
      <p>Kontakt: Dr. Alice Example, alice@example.org, +49 6421 00000</p>
      <p>Ihre Bewerbungsunterlagen senden Sie bitte bis zum 29.11.2026 an alice@example.org.</p>
    </div>
  </div>
  <footer id="bite_button_control_footer"><a href="#">Zur&uuml;ck zur &Uuml;bersicht</a></footer>
</div>
<div class="site-footer">Impressum</div>
<script src="https://cs-assets.b-ite.com/uni-marburg/templates/js/app.js"></script>
</body></html>'''

FIELDS = [('Eintrittstermin', 'n&auml;chstm&ouml;glich'), ('Bewerbungsfrist', '29.11.2026'),
          ('Entgeltgruppe', 'SHK-Verg&uuml;tung'), ('Befristung', '1 Jahr'), ('Umfang', '40 Std./Monat')]


def page(banner='60ae', extra='', fields=FIELDS, icon='d2bf'):
    return PAGE.format(banner=banner, extra=extra,
                       fields='\n'.join(FIELD.format(n=f'{icon}{i}', label=l, value=v)
                                        for i, (l, v) in enumerate(fields)))


class Read(unittest.TestCase):
    def setUp(self):
        self.p = posting.read(page())

    def test_reads_the_ad_id(self):
        self.assertEqual(self.p.job_id, 'fb20-0001-shk-2026')
        self.assertIn('<p><b>Ausschreibungs-ID: fb20-0001-shk-2026</b></p>', self.p.html)

    def test_field_box_becomes_a_table_of_labels_over_values(self):
        self.assertIn('<table><tr><th>Eintrittstermin:</th><th>Bewerbungsfrist:</th><th>Entgeltgruppe:</th>'
                      '<th>Befristung:</th><th>Umfang:</th></tr><tr><td>nächstmöglich</td><td>29.11.2026</td>'
                      '<td>SHK-Vergütung</td><td>1 Jahr</td><td>40 Std./Monat</td></tr></table>', self.p.html)
        # The ID line comes before the box, and the box before the text.
        h = self.p.html
        self.assertLess(h.index('Ausschreibungs-ID'), h.index('<table>'))
        self.assertLess(h.index('</table>'), h.index('Am Fachbereich Medizin'))

    def test_keeps_only_the_ad_text_and_plain_tags(self):
        h = self.p.html
        for kept in ('<h1>Studentische Hilfskraft</h1>', '<h2>Ihre Aufgaben:</h2>',
                     '<li>Unterstützung bei Studien</li>', 'Pflege von Webseiten', 'alice@example.org'):
            self.assertIn(kept, h)
        for dropped in ('Navigation', 'Impressum', 'Zurück zur', 'Jetzt bewerben', 'tracking', 'color: red',
                        '01.01.2000', 'b-ite.com', 'example.org/', '<img', '<a', '<script', '<style',
                        '<button', 'onclick', 'style=', 'class=', 'href=', 'src='):
            self.assertNotIn(dropped, h)

    def test_text_is_escaped(self):
        p = posting.read(page(extra='&lt;script&gt;alert(1)&lt;/script&gt; &amp; mehr'))
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt; &amp; mehr', p.html)
        self.assertNotIn('<script>', p.html)

    def test_hash_ignores_layout_but_follows_the_content(self):
        same = posting.read(page(banner='ffff', icon='eeee').replace('padding-top: 2px', 'margin: 0')
                            .replace('<p>zu besetzen', '<p>\n   zu   besetzen'))
        self.assertEqual(same.hash, self.p.hash)
        self.assertRegex(self.p.hash, r'^[0-9a-f]{16}$')
        self.assertNotEqual(posting.read(page(extra='Neu: auch remote.')).hash, self.p.hash)
        later = [(l, '06.12.2026' if l == 'Bewerbungsfrist' else v) for l, v in FIELDS]
        self.assertNotEqual(posting.read(page(fields=later)).hash, self.p.hash)

    def test_refuses_pages_without_an_ad(self):
        with self.assertRaisesRegex(ValueError, 'not a job posting'):
            posting.read('<html><body><h1>Seite nicht gefunden</h1></body></html>')
        with self.assertRaisesRegex(ValueError, 'no text'):
            posting.read('<div class="__bjp-jobofferWrapper"><img src="x.png"><script>x()</script></div>')

    def test_page_without_box_or_id_still_reads(self):
        p = posting.read('<div class="__bjp-jobofferWrapper"><h1>Hilfskraft</h1><p>Text</p></div>')
        self.assertEqual(p.job_id, '')
        self.assertNotIn('<table>', p.html)
        self.assertIn('<h1>Hilfskraft</h1><p>Text</p>', p.html)


class PlainPdf(unittest.TestCase):
    def test_extract_reads_every_field_of_the_plain_pdf(self):
        p = posting.read(page())
        data = posting.plain_pdf(p)
        self.assertTrue(data.startswith(b'%PDF'))
        self.assertEqual(posting.plain_pdf(p), data)  # same posting, same bytes
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'ad.pdf')
            with open(path, 'wb') as f:
                f.write(data)
            fields = extract.extract(path)
        self.assertEqual(fields['job_id'], 'fb20-0001-shk-2026')
        self.assertEqual(fields['position_start_date'], 'nächstmöglich')
        self.assertEqual(fields['application_deadline'], '29.11.2026')
        self.assertEqual(fields['pay'], 'SHK-Vergütung')
        self.assertEqual(fields['duration_of_contract'], '1 Jahr')
        self.assertEqual(fields['workload'], '40 Std./Monat')
        self.assertEqual(fields['position_title'], 'Studentische Hilfskraft')
        self.assertFalse(fields['needs_review'])


class FakeBrowser:
    """Stands in for subprocess.Popen: writes `output` to the --print-to-pdf path."""

    def __init__(self, output=b'', code=0, hang=False):
        self.output, self.code, self.hang = output, code, hang
        self.commands = []

    def __call__(self, cmd, **kwargs):
        self.commands.append(cmd)
        self.kwargs = kwargs
        out = next(a.split('=', 1)[1] for a in cmd if a.startswith('--print-to-pdf='))
        if self.output is not None:
            with open(out, 'wb') as f:
                f.write(self.output)
        return FakeProcess(self)


class FakeProcess:
    pid = 4242

    def __init__(self, browser):
        self.browser = browser
        self.returncode = None

    def wait(self, timeout=None):
        if self.browser.hang and timeout is not None:
            raise subprocess.TimeoutExpired('chrome', timeout)
        self.returncode = self.browser.code
        return self.returncode


@mock.patch('os.killpg')
class PrintPdf(unittest.TestCase):
    def test_prints_with_the_sandbox_on_in_a_fresh_profile(self, killpg):
        browser = FakeBrowser(b'%PDF-1.7 printed')
        self.assertEqual(posting.print_pdf('/usr/bin/chrome', URL, run=browser), b'%PDF-1.7 printed')
        cmd = browser.commands[0]
        self.assertEqual(cmd[0], '/usr/bin/chrome')
        self.assertEqual(cmd[-1], URL)
        for flag in ('--headless', '--lang=de-DE', '--disable-extensions', '--no-pdf-header-footer'):
            self.assertIn(flag, cmd)
        self.assertFalse(any('sandbox' in a for a in cmd))
        self.assertTrue(any(a.startswith('--user-data-dir=') for a in cmd))
        self.assertTrue(browser.kwargs['start_new_session'])
        killpg.assert_called_once_with(4242, mock.ANY)  # helper processes are cleaned up

    def test_refuses_non_university_urls_without_starting_the_browser(self, killpg):
        browser = FakeBrowser(b'%PDF')
        for url in ('https://example.org/jobposting/1', 'file:///etc/passwd', 'http://stellenangebote.uni-marburg.de/x'):
            with self.assertRaisesRegex(ValueError, 'non-university'):
                posting.print_pdf('/usr/bin/chrome', url, run=browser)
        self.assertEqual(browser.commands, [])

    def test_failures(self, killpg):
        cases = [(FakeBrowser(b'%PDF', code=1), RuntimeError, 'exited with code 1'),
                 (FakeBrowser(None), RuntimeError, 'wrote no PDF'),
                 (FakeBrowser(b'<html>error</html>'), RuntimeError, 'not a PDF'),
                 (FakeBrowser(b'%PDF', hang=True), TimeoutError, 'did not finish')]
        for browser, error, message in cases:
            with self.assertRaisesRegex(error, message):
                posting.print_pdf('/usr/bin/chrome', URL, timeout=5, run=browser)
        self.assertEqual(killpg.call_count, len(cases))  # a hung browser is killed too


class FindBrowser(unittest.TestCase):
    def test_chrome_path_chooses_the_browser(self):
        with mock.patch.dict(os.environ, {'CHROME_PATH': sys.executable}):
            self.assertEqual(posting.find_browser(), sys.executable)
        with mock.patch.dict(os.environ, {'CHROME_PATH': '/nonexistent/chrome'}):
            self.assertIsNone(posting.find_browser())

    def test_prefers_the_headless_shell(self):
        found = {'google-chrome': '/usr/bin/google-chrome', 'chrome-headless-shell': '/opt/shell'}
        with mock.patch.dict(os.environ, {'CHROME_PATH': ''}), \
                mock.patch('shutil.which', side_effect=found.get):
            self.assertEqual(posting.find_browser(), '/opt/shell')
        with mock.patch.dict(os.environ, {'CHROME_PATH': ''}), mock.patch('shutil.which', return_value=None):
            self.assertIsNone(posting.find_browser())


class Saver(unittest.TestCase):
    def setUp(self):
        self.p = posting.read(page())
        self.lines = []

    def saver(self, browser='/usr/bin/chrome'):
        return posting.Saver(self.lines.append, browser=lambda: browser)

    def test_uses_the_print_when_it_shows_the_ad(self):
        printed = posting.plain_pdf(self.p)  # any PDF that shows the ad ID
        with mock.patch.object(posting, 'print_pdf', return_value=printed) as print_pdf:
            self.assertEqual(self.saver().pdf(URL, self.p), (printed, 'printed'))
        print_pdf.assert_called_once_with('/usr/bin/chrome', URL)

    def test_plain_pdf_when_printing_fails(self):
        with mock.patch.object(posting, 'print_pdf', side_effect=RuntimeError('the browser exited with code 1')):
            data, how = self.saver().pdf(URL, self.p)
        self.assertEqual((data, how), (posting.plain_pdf(self.p), 'plain'))
        self.assertIn('failed (the browser exited with code 1)', self.lines[-1])

    def test_plain_pdf_when_the_print_shows_another_page(self):
        other = posting.plain_pdf(posting.read('<div class="__bjp-jobofferWrapper"><p>Wartungsarbeiten</p></div>'))
        with mock.patch.object(posting, 'print_pdf', return_value=other):
            self.assertEqual(self.saver().pdf(URL, self.p)[1], 'plain')
        self.assertIn('does not show the ad ID', self.lines[-1])

    def test_stops_printing_after_a_timeout(self):
        saver = self.saver()
        with mock.patch.object(posting, 'print_pdf', side_effect=TimeoutError('the browser did not finish')) as p:
            self.assertEqual(saver.pdf(URL, self.p)[1], 'plain')
            self.assertEqual(saver.pdf(URL, self.p)[1], 'plain')
        self.assertEqual(p.call_count, 1)

    def test_keeps_printing_after_other_failures(self):
        saver = self.saver()
        with mock.patch.object(posting, 'print_pdf', side_effect=RuntimeError('crash')) as p:
            saver.pdf(URL, self.p)
            saver.pdf(URL, self.p)
        self.assertEqual(p.call_count, 2)

    def test_without_a_browser_saves_plain_pdfs_and_says_so_once(self):
        saver = self.saver(browser=None)
        with mock.patch.object(posting, 'print_pdf') as p:
            self.assertEqual(saver.pdf(URL, self.p)[1], 'plain')
            self.assertEqual(saver.pdf(URL, self.p)[1], 'plain')
        p.assert_not_called()
        self.assertEqual(len(self.lines), 1)
        self.assertIn('no browser found', self.lines[0])


if __name__ == '__main__':
    unittest.main()
