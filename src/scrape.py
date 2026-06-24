"""Scraping for Uni Marburg student/research job ads.

Discovers PDF links on the main page and the department subpages, resolving each
ad's department (subpage name, or the main-page table cell) and its original
remote PDF basename. Downloads are returned as raw bytes for hashing/storage.
"""

import html
import os
import re
import urllib.request

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
    ('http://www.uni-marburg.de/grk1782/offenestellen', 'Research Training Group Functionalization of Semiconductors'),
    ('https://www.uni-marburg.de/en/synmikro/jobs-1', 'Center for Synthetic Microbiology'),
    ('https://www.uni-marburg.de/de/fotomarburg/ueberuns/stellenangebote', 'Image archive Photo Marburg'),
    ('https://www.uni-marburg.de/de/genderzukunft/zentrum/stellen', 'Center for Gender Studies and Feminist Futures Research'),
    ('http://www.uni-marburg.de/botgart/aktuelles/news/', 'Botanical garden'),
    ('https://www.uni-marburg.de/de/zfl/stellenausschreibungen', 'Center for Teacher Education'),
    ('https://www.uni-marburg.de/de/konfliktforschung/zentrum/profil/stellenauschreibungen', 'Center for Conflict Research'),
    ('https://www.uni-marburg.de/de/icwc/zentrum/stellenausschreibungen', 'International Centre for the Study of War Crimes Trials (ICWC)'),
    ('https://www.uni-marburg.de/en/microcosm-earth/about-us/join-us', 'Future Center Microcosm Earth'),
    ('https://www.uni-marburg.de/de/mcdci/zentrum/stellenangebote', 'Marburg Center for Digital Culture and Infrastructure (MCDCI)'),
    ('https://www.uni-marburg.de/de/mcaw/aktuelles/nachrichten/eine-stelle-als-studentische-hilfskraft-zu-besetzen-20-std-monat-nachwuchsgruppe_september', 'Marburg Center for the Ancient World (MCAW)'),
]

PDF_LINK_RE = re.compile(r'href=["\x27]([^"\x27]*\.pdf)["\x27]')


def fetch_page(url, log):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        log(f'  WARNING: could not fetch {url}: {e}')
        return None


def absolute_url(href):
    if href.startswith('http'):
        return href
    if href.startswith('/'):
        return 'https://www.uni-marburg.de' + href
    return href


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
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()
