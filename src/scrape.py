"""Scraping for Uni Marburg student/research job ads.

Discovers PDF links on the main page and the department subpages, resolving each
ad's department (subpage name, or the main-page table cell) and its original
remote PDF basename. Downloads are returned as raw bytes for hashing/storage.
"""

import html
import http.client
import os
import re
import ssl
import urllib.parse

MAIN_URL = ('https://www.uni-marburg.de/de/universitaet/administration/verwaltung/'
            'dezernat2/personalabteilung/bewerber/stud-und-wiss-hilfskraftstellen')

SUBPAGES = [
    ('https://www.uni-marburg.de/de/fb01/fachbereich/karriere/stellenausschreibungen', 'Department 01 Law'),
    ('https://www.uni-marburg.de/de/fb02/studium/karriere/career-center/ausschreibungen-fb02', 'Department 02 Economics'),
    ('https://www.uni-marburg.de/de/fb03/fachbereich/kontakt/stellenangebote', 'Department 03 Social Sciences and Philosophy'),
    ('https://www.uni-marburg.de/de/fb04/fachbereich/personen/stellenangebote', 'Department 04 Psychology'),
    ('https://www.uni-marburg.de/de/fb05/stellenausschreibungen', 'Department 05 Protestant Theology'),
    ('https://www.uni-marburg.de/de/fb06/ausschreibungen-stud-mitarbeiter-innen', 'Department 06 History and Cultural Studies'),
    ('https://www.uni-marburg.de/de/fb09/stellenausschreibungen', 'Department 09 German Studies and Art History'),
    ('https://www.uni-marburg.de/de/fb10/fachbereich/stellenausschreibungen', 'Department 10 Foreign Language Philologies'),
    ('https://www.uni-marburg.de/de/fb12/fachbereich/dekanat/wirtschaftsverwaltung/ausschreibungen-fuer-hilfskraefte', 'Department 12 Mathematics and Computer Science'),
    ('https://www.uni-marburg.de/de/fb13/fachbereich/dekanat/wpv/ausschreibungen-des-fb-physik', 'Department 13 Physics'),
    ('https://www.uni-marburg.de/de/fb15/fachbereich/dekanat-verwaltung/aktuelle-stellenausschreibungen', 'Department 15 Chemistry'),
    ('https://www.uni-marburg.de/de/fb16/bewerbung', 'Department 16 Pharmacy'),
    ('https://www.uni-marburg.de/de/fb17/fachbereich/personen/stellenangebote', 'Department 17 Biology'),
    ('https://www.uni-marburg.de/de/fb19/fachbereich/stellenangebote', 'Department 19 Geography'),
    ('https://www.uni-marburg.de/de/fb21/fachbereich/personen/stellenausschreibungen', 'Department 21 Educational Sciences'),
    ('https://www.uni-marburg.de/de/cnms/centrum/stellenangebote', 'Center for Near and Middle Eastern Studies (CNMS)'),
    ('https://www.uni-marburg.de/de/ub/ueber-uns/karriere-und-ausbildung/studentische-hilfskraftstellen', 'University Library'),
    ('https://www.uni-marburg.de/de/hrz/aktuelles/nachrichten/2025/shk-hrz-2025-02', 'University Computing Centre'),
    ('https://www.uni-marburg.de/grk1782/offenestellen', 'Research Training Group Functionalization of Semiconductors'),
    ('https://www.uni-marburg.de/en/synmikro/jobs-1', 'Center for Synthetic Microbiology'),
    ('https://www.uni-marburg.de/de/fotomarburg/ueberuns/stellenangebote', 'Image archive Photo Marburg'),
    ('https://www.uni-marburg.de/de/genderzukunft/zentrum/stellen', 'Center for Gender Studies and Feminist Futures Research'),
    ('https://www.uni-marburg.de/botgart/aktuelles/news/', 'Botanical garden'),
    ('https://www.uni-marburg.de/de/zfl/stellenausschreibungen', 'Center for Teacher Education'),
    ('https://www.uni-marburg.de/de/konfliktforschung/zentrum/profil/stellenauschreibungen', 'Center for Conflict Research'),
    ('https://www.uni-marburg.de/de/icwc/zentrum/stellenausschreibungen', 'International Centre for the Study of War Crimes Trials (ICWC)'),
    ('https://www.uni-marburg.de/en/microcosm-earth/about-us/join-us', 'Future Center Microcosm Earth'),
    ('https://www.uni-marburg.de/de/mcdci/zentrum/stellenangebote', 'Marburg Center for Digital Culture and Infrastructure (MCDCI)'),
    ('https://www.uni-marburg.de/de/mcaw/aktuelles/nachrichten/eine-stelle-als-studentische-hilfskraft-zu-besetzen-20-std-monat-nachwuchsgruppe_september', 'Marburg Center for the Ancient World (MCAW)'),
]

PDF_LINK_RE = re.compile(r'href=["\x27]([^"\x27]*\.pdf)["\x27]')


# Only ever download from the university's own servers, and never more than
# these many bytes per response, so a hostile page or file cannot make the
# fetcher read local files, hit other hosts, or exhaust memory.
ALLOWED_DOMAIN = 'uni-marburg.de'
MAX_PAGE_BYTES = 5 * 1024 * 1024
MAX_PDF_BYTES = 25 * 1024 * 1024


HEADERS = {'User-Agent': 'Mozilla/5.0'}
REDIRECT_CODES = {301, 302, 303, 307, 308}
MAX_REDIRECTS = 10


class HTTPStatusError(Exception):
    """The final answer was not a success, for example 403 for a protected PDF."""

    def __init__(self, status, reason, url):
        super().__init__(f'HTTP Error {status}: {reason}')
        self.status = status
        self.url = url


def _https_connection(host, port, timeout):
    return http.client.HTTPSConnection(host, port, timeout=timeout,
                                       context=ssl.create_default_context())


class KeepAliveClient:
    """GET requests that reuse one open HTTPS connection per host.

    urllib opens a new connection for every request. The university's servers hold
    back new connections that arrive in quick succession (1 to 5 seconds each), so a
    fetch of about 100 pages and PDFs took 2 to 6 minutes on GitHub. Over one open
    connection the same requests take a few seconds.

    Every URL, including each redirect target, is checked with is_allowed_url before
    it is requested, and every response body is capped at max_bytes.
    """

    def __init__(self, connect=_https_connection):
        self._connect = connect
        self._conns = {}

    def get(self, url, timeout, max_bytes):
        if not is_allowed_url(url):
            raise ValueError(f'refusing to fetch non-university URL: {url}')
        for _ in range(MAX_REDIRECTS + 1):
            status, reason, location, data = self._get_once(url, timeout, max_bytes)
            if status in REDIRECT_CODES and location:
                target = urllib.parse.urljoin(url, location)
                if not is_allowed_url(target):
                    raise ValueError(f'redirected to non-university URL: {target}')
                url = target
                continue
            if not 200 <= status < 300:
                raise HTTPStatusError(status, reason, url)
            return data
        raise ValueError(f'too many redirects: {url}')

    def close(self):
        for key in list(self._conns):
            self._drop(key)

    def _get_once(self, url, timeout, max_bytes):
        parts = urllib.parse.urlsplit(url)
        key = (parts.hostname, parts.port or 443)
        target = (parts.path or '/') + (f'?{parts.query}' if parts.query else '')
        for attempt in (1, 2):
            conn = self._conns.get(key)
            if conn is None:
                conn = self._conns[key] = self._connect(key[0], key[1], timeout)
            reused = conn.sock is not None
            conn.timeout = timeout
            if reused:
                conn.sock.settimeout(timeout)
            try:
                conn.request('GET', target, headers=HEADERS)
                resp = conn.getresponse()
                data = resp.read(max_bytes + 1)
            except (ConnectionError, http.client.BadStatusLine):
                self._drop(key)
                if reused and attempt == 1:
                    continue  # the server closed the idle connection; ask once more on a new one
                raise
            except Exception:
                self._drop(key)
                raise
            if not resp.isclosed():
                self._drop(key)  # part of the body is still unread, so the connection is unusable
            if len(data) > max_bytes:
                raise ValueError(f'response larger than {max_bytes} bytes: {url}')
            return resp.status, resp.reason, resp.getheader('Location'), data

    def _drop(self, key):
        conn = self._conns.pop(key, None)
        if conn is not None:
            conn.close()


_client = KeepAliveClient()


def _read_capped(url, timeout, max_bytes):
    return _client.get(url, timeout, max_bytes)


def close():
    """Close the open connections (call when the fetch is done)."""
    _client.close()


def fetch_page(url, log):
    try:
        return _read_capped(url, 30, MAX_PAGE_BYTES).decode('utf-8', errors='replace')
    except Exception as e:
        log(f'  WARNING: could not fetch {url}: {e}')
        return None


def is_allowed_url(url):
    """True for https URLs on uni-marburg.de or one of its subdomains."""
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or '').lower()
    return (parts.scheme == 'https'
            and (host == ALLOWED_DOMAIN or host.endswith('.' + ALLOWED_DOMAIN)))


def absolute_url(href):
    """Resolve an ad link to an https university URL, or None to skip it."""
    if href.startswith('/') and not href.startswith('//'):
        href = 'https://www.uni-marburg.de' + href
    parts = urllib.parse.urlsplit(href)
    if parts.scheme == 'http':
        href = urllib.parse.urlunsplit(('https',) + tuple(parts[1:]))
    return href if is_allowed_url(href) else None


def original_name(href):
    """Remote PDF basename without extension, e.g. 'fb04-023-shk-2026'."""
    base = os.path.basename(href.split('?')[0])
    return re.sub(r'\.pdf$', '', base, flags=re.IGNORECASE)


def discover_main_page(content):
    """Ads on the main page, with department taken from each table row's cell."""
    ads = []
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', content, re.DOTALL):
        m = PDF_LINK_RE.search(row)
        if not m:
            continue
        href = m.group(1)
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        dept = ''
        if cells:
            dept = re.sub(r'<br\s*/?>', ' ', cells[0])
            dept = re.sub(r'<[^>]+>', '', dept)
            dept = re.sub(r'\s+', ' ', html.unescape(dept)).strip(' |')
        ads.append({'href': href, 'department': dept or 'Main Page',
                    'original_name': original_name(href)})
    return ads


def discover_subpage(content, department):
    ads = []
    for href in PDF_LINK_RE.findall(content):
        ads.append({'href': href, 'department': department,
                    'original_name': original_name(href)})
    return ads


def discover_all(log):
    """Return a list of ad dicts {href, department, original_name}, deduped by URL."""
    ads = []
    seen_urls = set()

    def add(items):
        for it in items:
            url = absolute_url(it['href'])
            if url is None:
                log(f"  skipped non-university link: {it['href']}")
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)
            it['url'] = url
            ads.append(it)

    log('Fetching main page...')
    main = fetch_page(MAIN_URL, log)
    if main:
        found = discover_main_page(main)
        add(found)
        log(f'  found {len(found)} ad(s)')

    for url, dept in SUBPAGES:
        log(f'Fetching {dept}...')
        page = fetch_page(url, log)
        if page:
            found = discover_subpage(page, dept)
            add(found)
            log(f'  found {len(found)} ad(s)')

    return ads


def download(url):
    return _read_capped(url, 60, MAX_PDF_BYTES)
