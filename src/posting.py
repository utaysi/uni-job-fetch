"""Job ads that are web pages instead of PDFs: the university's central job board.

The central board (the university's applicant system, made by BITE) publishes each
ad as a page on stellenangebote.uni-marburg.de, with no PDF. To keep the convention
of the PDF ads (our own copy, read by the same extractor, still there after the ad
goes offline), each page is saved as a PDF:

- printed by a headless Chrome, which gives the university's own layout, or
- when no browser is found or printing fails, a plain PDF made from the page text
  with PyMuPDF, laid out so that extract.py reads the fields the same way.

An ad is identified by a hash of its cleaned content (ad ID, field box and text,
without scripts, images or attributes), not of the PDF: a browser print differs on
every run, and a PyMuPDF update could change the plain PDF.
"""

import hashlib
import html
import html.parser
import io
import os
import re
import shutil
import signal
import subprocess
import tempfile
from dataclasses import dataclass

import fitz

import scrape

# Tags kept in the cleaned page, without any attributes. Text inside other tags
# (links, spans of the layout) is kept; the tags themselves are dropped.
KEEP_TAGS = {'h1', 'h2', 'h3', 'h4', 'p', 'ul', 'ol', 'li', 'b', 'strong', 'em', 'i', 'br', 'div'}
# Tags dropped with everything inside them.
DROP_TAGS = {'script', 'style', 'noscript', 'svg', 'template', 'iframe', 'object',
             'footer', 'button', 'form', 'select', 'textarea'}
VOID_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}

WRAPPER_CLASS = '__bjp-jobofferWrapper'   # the ad itself, without page header and footer
FIELD_CLASS = '__bjp-content--block-20'   # one field of the box: Eintrittstermin, Bewerbungsfrist, ...
ID_CLASS = 'id'                           # the paragraph with "Ausschreibungs-ID: ..."
BOX_MARK = '<!--box-->'


@dataclass
class Posting:
    html: str      # cleaned page, ready for the plain PDF
    job_id: str    # the "Ausschreibungs-ID", or '' if the page has none
    hash: str      # identifies the ad; changes only when its content changes


class _Cleaner(html.parser.HTMLParser):
    """Keeps only the ad: allowlisted tags without attributes, escaped text.

    The field box (label above value, five in a row) becomes a table and the ad ID
    one line, the layout of the university's PDF ads that extract.py reads.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.depth = 0          # div depth inside the wrapper (0 = outside)
        self.found = False
        self.skip = 0           # depth inside a dropped tag
        self.fields = []        # [label, value] of each field in the box
        self.field_depth = 0    # div depth of the current field (0 = not in one)
        self.in_label = False
        self.id_text = None     # text of the ID paragraph while inside it
        self.job_id = ''

    def handle_starttag(self, tag, attrs):
        classes = (dict(attrs).get('class') or '').split()
        if self.depth == 0:
            if tag == 'div' and WRAPPER_CLASS in classes and not self.found:
                self.depth = 1
                self.found = True
            return
        if tag == 'div':
            self.depth += 1
        if self.skip:
            if tag in DROP_TAGS:
                self.skip += 1
            return
        if tag in DROP_TAGS:
            self.skip = 1
            return
        if tag == 'div' and FIELD_CLASS in classes and not self.field_depth:
            if not self.fields:
                self.out.append(BOX_MARK)
            self.field_depth = self.depth
            self.fields.append(['', ''])
            return
        if self.field_depth or self.id_text is not None:
            if tag in ('b', 'strong'):
                self.in_label = True
            return
        if tag == 'p' and ID_CLASS in classes:
            self.id_text = ''
            return
        if tag in KEEP_TAGS:
            self.out.append(f'<{tag}>')

    def handle_endtag(self, tag):
        if self.depth == 0:
            return
        if self.skip:
            if tag in DROP_TAGS:
                self.skip -= 1
        elif self.field_depth:
            if tag in ('b', 'strong'):
                self.in_label = False
            elif tag == 'div' and self.depth == self.field_depth:
                self.field_depth = 0
        elif self.id_text is not None:
            if tag == 'p':
                text = _text(self.id_text)
                self.job_id = _text(text.split(':', 1)[1]) if ':' in text else text
                self.out.append(f'<p><b>{html.escape(text)}</b></p>')
                self.id_text = None
        elif tag in KEEP_TAGS and tag not in VOID_TAGS:
            self.out.append(f'</{tag}>')
        if tag == 'div':
            self.depth -= 1

    def handle_data(self, data):
        if self.depth == 0 or self.skip:
            return
        if self.id_text is not None:
            self.id_text += data + ' '
        elif self.field_depth:
            self.fields[-1][0 if self.in_label else 1] += data + ' '
        else:
            self.out.append(html.escape(re.sub(r'\s+', ' ', data)))


def _text(s):
    return ' '.join(s.split())


def _box_table(fields):
    labels = ''.join(f'<th>{html.escape(_text(label))}</th>' for label, _ in fields)
    values = ''.join(f'<td>{html.escape(_text(value))}</td>' for _, value in fields)
    return f'<table><tr>{labels}</tr><tr>{values}</tr></table>'


def read(page):
    """Clean a posting page (str) into a Posting. ValueError if it holds no ad."""
    cleaner = _Cleaner()
    cleaner.feed(page)
    cleaner.close()
    if not cleaner.found:
        raise ValueError('not a job posting page (no ad found in it)')
    body = ''.join(cleaner.out).replace(BOX_MARK, _box_table(cleaner.fields) if cleaner.fields else '', 1)
    if not _text(re.sub(r'<[^>]+>', ' ', body)):
        raise ValueError('the job posting page has no text')
    clean = f'<html><body>{body}</body></html>'
    # Spacing around tags does not count, so a reformatted page is still the same ad.
    key = re.sub(r'\s*(<[^>]+>)\s*', r'\1', clean)
    hash_ = hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]
    return Posting(clean, cleaner.job_id, hash_)


# The plain PDF. The space under the box keeps extract.py's box reader from taking
# the first paragraph for part of the values (it stops at a gap of more than 28 pt).
PLAIN_CSS = """
* { font-family: sans-serif; font-size: 10pt; line-height: 1.35; }
h1 { font-size: 15pt; } h2 { font-size: 12pt; } h3, h4 { font-size: 11pt; }
table { width: 100%; margin-top: 6pt; margin-bottom: 32pt; }
th, td { text-align: left; vertical-align: top; padding-right: 6pt; }
p, ul, ol { margin-top: 3pt; margin-bottom: 3pt; }
"""
PAGE_MARGIN = 56  # points, about 2 cm


def plain_pdf(posting):
    """The posting as a plain A4 PDF (bytes), the same bytes for the same posting."""
    story = fitz.Story(html=posting.html, user_css=PLAIN_CSS)
    buffer = io.BytesIO()
    writer = fitz.DocumentWriter(buffer)
    page = fitz.paper_rect('a4')
    where = page + (PAGE_MARGIN, PAGE_MARGIN, -PAGE_MARGIN, -PAGE_MARGIN)
    more = True
    while more:
        device = writer.begin_page(page)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
    writer.close()
    return buffer.getvalue()


# Printing with a browser. chrome-headless-shell is Chrome's own build for printing
# and screenshots (no extensions, no first-run setup) and is tried first; GitHub's
# Ubuntu runners come with google-chrome. CHROME_PATH chooses one explicitly.
BROWSERS = ['chrome-headless-shell', 'google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser']
PRINT_TIMEOUT_S = 60


def find_browser():
    """Path of the browser to print with, or None."""
    chosen = os.environ.get('CHROME_PATH')
    if chosen:
        return chosen if os.path.isfile(chosen) and os.access(chosen, os.X_OK) else None
    for name in BROWSERS:
        path = shutil.which(name)
        if path:
            return path
    return None


def browser_command(browser, url, profile, out_path):
    """Print url to out_path: headless, German, in a fresh profile, with the sandbox on."""
    return [browser, '--headless', '--disable-gpu', '--lang=de-DE',
            '--no-first-run', '--no-default-browser-check', '--disable-extensions',
            '--disable-sync', '--disable-background-networking',
            '--no-pdf-header-footer', f'--user-data-dir={profile}', f'--print-to-pdf={out_path}', url]


def print_pdf(browser, url, timeout=PRINT_TIMEOUT_S, run=subprocess.Popen):
    """The page at url printed by the browser, as PDF bytes. Raises on any failure."""
    if not scrape.is_allowed_url(url):
        raise ValueError(f'refusing to print a non-university URL: {url}')
    with tempfile.TemporaryDirectory(prefix='uni-job-print-') as tmp:
        profile = os.path.join(tmp, 'profile')
        out_path = os.path.join(tmp, 'print.pdf')
        with open(os.path.join(tmp, 'browser.log'), 'wb') as log:
            proc = run(browser_command(browser, url, profile, out_path),
                       stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                raise TimeoutError(f'the browser did not finish within {timeout} s') from None
            finally:
                _kill_group(proc)  # also helper processes the browser left behind
        if proc.returncode != 0:
            raise RuntimeError(f'the browser exited with code {proc.returncode}')
        if not os.path.isfile(out_path):
            raise RuntimeError('the browser wrote no PDF')
        with open(out_path, 'rb') as f:
            data = f.read()
    if not data.startswith(b'%PDF'):
        raise RuntimeError('the browser wrote something that is not a PDF')
    return data


def _kill_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    proc.wait()


def check_print(data, posting):
    """Raise unless the printed PDF shows this ad (its ID, or at least some text)."""
    with fitz.open(stream=data, filetype='pdf') as doc:
        text = ''.join(page.get_text() for page in doc)
    if posting.job_id:
        if re.sub(r'\s+', '', posting.job_id) not in re.sub(r'\s+', '', text):
            raise RuntimeError('the printed PDF does not show the ad ID')
    elif not text.strip():
        raise RuntimeError('the printed PDF has no text')


class Saver:
    """Saves postings as PDFs during one fetch: printed when possible, else plain."""

    def __init__(self, log, browser=find_browser):
        self._log = log
        self._find = browser
        self._browser = None
        self._looked = False

    def browser(self):
        if not self._looked:
            self._looked = True
            self._browser = self._find()
            if self._browser:
                self._log(f'  printing central ads with {self._browser}')
            else:
                self._log('  no browser found to print central ads; saving plain PDFs instead')
        return self._browser

    def pdf(self, url, posting):
        """(PDF bytes, 'printed' or 'plain') for the posting at url."""
        browser = self.browser()
        if browser:
            try:
                data = print_pdf(browser, url)
                check_print(data, posting)
                return data, 'printed'
            except Exception as e:
                self._log(f'  WARNING: printing {url} failed ({e}); saving a plain PDF instead')
                if isinstance(e, TimeoutError):
                    self._browser = None  # do not wait that long again for every ad
        return plain_pdf(posting), 'plain'
