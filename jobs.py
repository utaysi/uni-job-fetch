#!/usr/bin/env python3
"""Uni Marburg student job fetcher (Windows port).

Single CLI consolidating the former shell scripts:
  fetch          scrape main + department pages, download PDFs, search them for a name
  view           list saved jobs across fetches, or open one
  generate-data  aggregate all fetches into jobs_data.json for the dashboard
  serve          regenerate data and serve the dashboard on http://localhost:8080
"""

import argparse
import glob
import html
import http.server
import json
import logging
import os
import re
import shutil
import sys
import urllib.request
from datetime import datetime

from pypdf import PdfReader

# pypdf logs noisy "Ignoring wrong pointing object" warnings for malformed PDFs.
logging.getLogger('pypdf').setLevel(logging.ERROR)

MAIN_URL = "https://www.uni-marburg.de/de/universitaet/administration/verwaltung/dezernat2/personalabteilung/bewerber/stud-und-wiss-hilfskraftstellen"
DEFAULT_NAME = "Matthias"
JOBS_ROOT = "jobs"  # all timestamped fetch folders live under here

# Subpages to also fetch, with their display names.
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


def make_filename(source, title):
    safe_source = re.sub(r'[^\w\s\-()]', '', source)
    safe_source = re.sub(r'\s+', '_', safe_source.strip())
    safe_title = re.sub(r'[^\w\s\-()]', '', title)
    safe_title = re.sub(r'\s+', '_', safe_title.strip())
    return f'{safe_source}__{safe_title}.pdf'


def fetch_page(url, log):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        log(f'  WARNING: Could not fetch {url}: {e}')
        return None


def extract_main_page_jobs(content):
    jobs = []
    seen_names = {}
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', content, re.DOTALL)
    for row in rows:
        pdf_match = PDF_LINK_RE.search(row)
        if not pdf_match:
            continue
        pdf_href = pdf_match.group(1)
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        if len(cells) < 2:
            continue
        dept_cell = cells[0]
        dept_cell = re.sub(r'<br\s*/?>', ' | ', dept_cell)
        dept_cell = re.sub(r'<[^>]+>', '', dept_cell)
        dept_cell = html.unescape(dept_cell).strip()
        dept_cell = re.sub(r'\s+', ' ', dept_cell)
        date_cell = cells[-1] if len(cells) >= 3 else ''
        date_cell = re.sub(r'<[^>]+>', '', date_cell).strip()
        title = dept_cell.strip(' |').replace(' | ', ' - ')
        if title in seen_names:
            seen_names[title] += 1
            title = f'{title} ({seen_names[title]})'
        else:
            seen_names[title] = 1
        jobs.append({
            'title': title,
            'pdf_href': pdf_href,
            'date': date_cell,
            'source': 'Main Page',
            'filename': make_filename('Main Page', title),
        })
    return jobs


def extract_subpage_jobs(content, source_name, page_url):
    jobs = []
    seen_names = {}
    for pdf_href in PDF_LINK_RE.findall(content):
        anchor_pattern = re.escape(pdf_href).replace(r'\.', r'[.]')
        anchor_match = re.search(r'href=["\x27]' + anchor_pattern + r'["\x27][^>]*>([^<]*)', content)
        link_text = ''
        date_str = ''
        if anchor_match:
            link_text = html.unescape(anchor_match.group(1).strip())
            link_text = re.sub(r'\s+', ' ', link_text)
            start = anchor_match.start()
            context = content[max(0, start - 500):min(len(content), start + 500)]
            date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', context)
            if date_match:
                date_str = date_match.group(1)

        if link_text:
            title = link_text
        else:
            title = os.path.basename(pdf_href).replace('.pdf', '').replace('_', ' ')

        if title in seen_names:
            seen_names[title] += 1
            title = f'{title} ({seen_names[title]})'
        else:
            seen_names[title] = 1

        jobs.append({
            'title': title,
            'pdf_href': pdf_href,
            'date': date_str,
            'source': source_name,
            'filename': make_filename(source_name, title),
        })
    return jobs


def download_pdf(url, filepath):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    with open(filepath, 'wb') as f:
        f.write(data)


def download_all(outdir, jobs):
    total = len(jobs)
    for i, job in enumerate(jobs, 1):
        href = job['pdf_href']
        if href.startswith('http'):
            pdf_url = href
        elif href.startswith('/'):
            pdf_url = 'https://www.uni-marburg.de' + href
        else:
            pdf_url = href

        filename = job['filename']
        filepath = os.path.join(outdir, filename)

        print(f"  [{i}/{total}] [{job.get('source', 'Unknown')}] {job['title']}")
        if job.get('date'):
            print(f"         Deadline: {job['date']}")
        print(f'         -> {filename}')

        try:
            download_pdf(pdf_url, filepath)
        except Exception as e:
            print(f'         ERROR downloading: {e}')
            continue

        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            with open(filepath, 'rb') as f:
                header = f.read(4)
            if header != b'%PDF':
                print('         WARNING: Downloaded file may not be a valid PDF')
        else:
            print('         WARNING: Downloaded file is empty or missing')
    print()


def search_pdfs(outdir, name):
    matches = []
    name_l = name.lower()
    for fn in sorted(os.listdir(outdir)):
        if not fn.lower().endswith('.pdf'):
            continue
        path = os.path.join(outdir, fn)
        try:
            reader = PdfReader(path)
        except Exception:
            continue
        for pno, page in enumerate(reader.pages, 1):
            try:
                text = page.extract_text() or ''
            except Exception:
                continue
            low = text.lower()
            if name_l in low:
                idx = low.find(name_l)
                snippet = text[max(0, idx - 40):idx + len(name) + 40]
                snippet = re.sub(r'\s+', ' ', snippet).strip()
                matches.append(f'{fn} (page {pno}): ...{snippet}...')
    return matches


def notify_ntfy(topic, title, body):
    req = urllib.request.Request(
        f'https://ntfy.sh/{topic}',
        data=body.encode('utf-8'),
        headers={
            'Title': title,
            'Priority': 'high',
            'Tags': 'briefcase',
        },
    )
    urllib.request.urlopen(req, timeout=30)


def cmd_fetch(args):
    name = args.name
    cleanup = args.cleanup
    if args.keep_hourly and datetime.now().strftime('%M') != '00':
        cleanup = True

    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    outdir = os.path.join(JOBS_ROOT, f'jobs_{timestamp}')
    os.makedirs(outdir, exist_ok=True)

    print('=== Uni Marburg Job Fetcher ===')
    print(f'Output directory: {outdir}')
    print(f'Search term: {name}')
    print()

    log_lines = []

    def log(msg=''):
        print(msg)
        log_lines.append(msg)

    all_jobs = []

    log('Fetching Main Page...')
    main_html = fetch_page(MAIN_URL, log)
    if main_html:
        main_jobs = extract_main_page_jobs(main_html)
        all_jobs.extend(main_jobs)
        log(f'  Found {len(main_jobs)} job(s) on Main Page')

    for url, source in SUBPAGES:
        log(f'Fetching {source}...')
        page = fetch_page(url, log)
        if page:
            sub_jobs = extract_subpage_jobs(page, source, url)
            all_jobs.extend(sub_jobs)
            log(f'  Found {len(sub_jobs)} job(s)')

    log(f'Total jobs found: {len(all_jobs)}')

    with open(os.path.join(outdir, '_jobs.json'), 'w', encoding='utf-8') as f:
        json.dump(all_jobs, f, indent=2, ensure_ascii=False)
    with open(os.path.join(outdir, '_fetch.log'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_lines) + '\n')

    print()
    print(f'Found {len(all_jobs)} job listing(s) total.')
    print()

    if not all_jobs:
        print('No jobs found. The page structure may have changed.')
        return 1

    download_all(outdir, all_jobs)
    print(f'All PDFs downloaded to: {outdir}/')
    print()

    print(f'=== Searching PDFs for "{name}" ===')
    print()
    matches = search_pdfs(outdir, name)
    if matches:
        body = '\n'.join(matches)
        print(body)
        print()
        if args.notify:
            print(f'Sending ntfy notification to topic: {args.notify}')
            try:
                notify_ntfy(args.notify, f'Uni Job Match: {name}', body)
            except Exception as e:
                print(f'  WARNING: notification failed: {e}')
    else:
        print(f'(No matches found for "{name}")')
    print()

    if cleanup:
        print(f'Cleaning up: removing {outdir}')
        shutil.rmtree(outdir, ignore_errors=True)

    print('Done.')
    return 0


def load_all_jobs():
    # Fetch directories live under JOBS_ROOT. Normalise to forward slashes so the
    # stored _dir works as a URL path in the dashboard even on Windows.
    pattern = os.path.join(JOBS_ROOT, 'jobs_*')
    dirs = sorted(d.replace(os.sep, '/') for d in glob.glob(pattern) if os.path.isdir(d))
    all_jobs = []
    for d in dirs:
        jpath = f'{d}/_jobs.json'
        if os.path.exists(jpath):
            with open(jpath, encoding='utf-8') as f:
                jobs = json.load(f)
            for job in jobs:
                job['_dir'] = d
            all_jobs.extend(jobs)
    return dirs, all_jobs


def cmd_view(args):
    dirs, all_jobs = load_all_jobs()
    if not dirs:
        print('No jobs_* directories found.')
        return 0

    if args.latest:
        latest_dir = dirs[-1]
        all_jobs = [j for j in all_jobs if j['_dir'] == latest_dir]
    if args.source:
        all_jobs = [j for j in all_jobs if args.source.lower() in j.get('source', '').lower()]
    if args.date:
        all_jobs = [j for j in all_jobs if args.date in j.get('date', '')]
    if args.search:
        s = args.search.lower()
        all_jobs = [j for j in all_jobs
                    if s in j.get('title', '').lower() or s in j.get('source', '').lower()]

    if args.open is not None:
        idx = args.open - 1
        if 0 <= idx < len(all_jobs):
            job = all_jobs[idx]
            filepath = os.path.join(job['_dir'], job.get('filename', ''))
            if os.path.exists(filepath):
                os.startfile(filepath)  # Windows
                print(f'Opened: {filepath}')
            else:
                print(f'PDF not found: {filepath}')
        else:
            print(f'Invalid job number: {args.open} (total: {len(all_jobs)})')
        return 0

    print(f'=== Saved Jobs ({len(all_jobs)} total from {len(dirs)} fetches) ===')
    print()
    for i, job in enumerate(all_jobs, 1):
        print(f"  [{i:3d}] [{job.get('source', 'Unknown')}]")
        print(f"         {job['title']}")
        if job.get('date'):
            print(f"         Deadline: {job['date']}")
        print(f"         Fetch: {job['_dir']}")
        print()
    return 0


def cmd_generate_data(args):
    dirs, all_jobs = load_all_jobs()
    if not dirs:
        print('No jobs_* directories found.')
        return 1
    with open('jobs_data.json', 'w', encoding='utf-8') as f:
        json.dump(all_jobs, f, indent=2, ensure_ascii=False)
    print(f'Aggregated {len(all_jobs)} jobs from {len(dirs)} fetches into jobs_data.json')
    return 0


def cmd_serve(args):
    print('=== Generating jobs data ===')
    cmd_generate_data(args)

    print()
    print('=== Starting dashboard server ===')
    print('Open http://localhost:8080 in your browser')
    print()

    httpd = http.server.ThreadingHTTPServer(('', 8080), http.server.SimpleHTTPRequestHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
    finally:
        httpd.server_close()
    return 0


def main():
    parser = argparse.ArgumentParser(prog='jobs.py', description='Uni Marburg student job fetcher')
    sub = parser.add_subparsers(dest='command', required=True)

    p_fetch = sub.add_parser('fetch', help='Scrape, download, and search job PDFs')
    p_fetch.add_argument('--name', default=DEFAULT_NAME, help='Name to search for inside the PDFs')
    p_fetch.add_argument('--notify', metavar='TOPIC', help='ntfy.sh topic to notify on a match')
    p_fetch.add_argument('--cleanup', action='store_true', help='Remove the output directory when done')
    p_fetch.add_argument('--keep-hourly', dest='keep_hourly', action='store_true',
                         help='For scheduled runs: keep top-of-hour fetches, clean up the rest')
    p_fetch.set_defaults(func=cmd_fetch)

    p_view = sub.add_parser('view', help='List or open saved jobs')
    p_view.add_argument('--source', help="Filter by source (e.g. 'Main Page', 'Psychology')")
    p_view.add_argument('--date', help="Filter by deadline date (e.g. '05.04.2026')")
    p_view.add_argument('--search', help='Search in job titles and sources')
    p_view.add_argument('--open', type=int, metavar='NUM', help='Open the PDF for job #NUM')
    p_view.add_argument('--latest', action='store_true', help='Show only the most recent fetch')
    p_view.set_defaults(func=cmd_view)

    p_gen = sub.add_parser('generate-data', help='Aggregate fetches into jobs_data.json')
    p_gen.set_defaults(func=cmd_generate_data)

    p_serve = sub.add_parser('serve', help='Generate data and serve the dashboard on :8080')
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    # Operate relative to the script's own folder so fetches, data, and the dashboard
    # all live together regardless of where the command (or scheduler) was launched.
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    sys.exit(args.func(args) or 0)


if __name__ == '__main__':
    main()
