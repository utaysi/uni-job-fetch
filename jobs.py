#!/usr/bin/env python3
"""Uni Marburg student job fetcher.

A unified, deduplicated repository of job-ad PDFs. Each ad is identified by the
content hash of its PDF, stored once in `pdfs/`, with structured fields extracted
into a SQLite database (jobs.db).

Run with no arguments for an interactive menu, or use a subcommand directly:
    fetch          scrape pages, download new ads, update statuses
    export-excel   write job_ads.xlsx from the database
    import-excel   fold edited job_ads.xlsx corrections back into the database
    serve          serve the dashboard at http://localhost:8080
"""

import argparse
import hashlib
import logging
import os
import re
import sys

import exporter
import extract
import scrape
import server
import store

logging.getLogger('fitz').setLevel(logging.ERROR)

PDF_DIR = 'pdfs'


def _sanitize(name):
    name = re.sub(r'[^\w\-]+', '_', name, flags=re.UNICODE)
    return name.strip('_') or 'ad'


def resolve_department(scrape_dept, pdf_text):
    """3-tier: subpage/main-page cell, else the PDF's Fachbereich line."""
    if scrape_dept and scrape_dept not in ('Main Page', ''):
        return scrape_dept
    pdf_dept = extract.department_from_pdf(pdf_text)
    return pdf_dept or scrape_dept or ''


def cmd_fetch(args):
    conn = store.connect()
    os.makedirs(PDF_DIR, exist_ok=True)

    def log(msg=''):
        print(msg)

    print('=== Uni Marburg Job Fetcher ===')
    ads = scrape.discover_all(log)
    print(f'\nDiscovered {len(ads)} ad link(s) total.\n')

    seen_hashes = set()
    new_count = 0
    updated_count = 0
    errors = 0
    seen_at = store.now_iso()

    for i, ad in enumerate(ads, 1):
        try:
            data = scrape.download(ad['url'])
        except Exception as e:
            print(f"  [{i}/{len(ads)}] ERROR downloading {ad['url']}: {e}")
            errors += 1
            continue
        if not data[:4] == b'%PDF':
            print(f"  [{i}/{len(ads)}] skipped (not a PDF): {ad['url']}")
            errors += 1
            continue

        hash_ = hashlib.sha256(data).hexdigest()[:16]
        seen_hashes.add(hash_)

        if store.exists(conn, hash_):
            store.mark_seen(conn, hash_, seen_at)
            updated_count += 1
            continue

        date_str = store.today()
        count = store.next_count_for_date(conn, date_str)
        filename = f'{date_str}_{_sanitize(ad["original_name"])}_{count}.pdf'
        path = os.path.join(PDF_DIR, filename)
        with open(path, 'wb') as f:
            f.write(data)

        try:
            fields = extract.extract(path)
        except Exception as e:
            print(f"  [{i}/{len(ads)}] extraction failed for {filename}: {e}")
            fields = {k: '' for k in store.PARSED_FIELDS}
            fields.update({'emails': [], 'phones': [], 'needs_review': True,
                           'template': 'non-standard', 'full_text': ''})

        fields['department'] = resolve_department(ad['department'], fields.get('full_text', ''))
        store.insert_job(conn, hash_, fields, ad['original_name'], count, filename, seen_at)
        new_count += 1
        flag = ' [REVIEW]' if fields.get('needs_review') else ''
        print(f"  [{i}/{len(ads)}] NEW {filename}{flag}")

    offline = store.mark_offline_missing(conn, seen_hashes)
    conn.commit()
    conn.close()

    print()
    print(f'New ads:        {new_count}')
    print(f'Still online:   {updated_count}')
    print(f'Newly offline:  {offline}')
    if errors:
        print(f'Errors/skipped: {errors}')
    print('Done.')
    return 0


def cmd_export_excel(args):
    conn = store.connect()
    try:
        n = exporter.export_excel(conn, overwrite=args.overwrite)
    except FileExistsError as e:
        print(f'Refusing to overwrite: {e}')
        return 1
    finally:
        conn.close()
    print(f'Exported {n} ad(s) to {exporter.EXCEL_FILE}')
    return 0


def cmd_import_excel(args):
    if not os.path.exists(exporter.EXCEL_FILE):
        print(f'{exporter.EXCEL_FILE} not found.')
        return 1
    conn = store.connect()
    try:
        n = exporter.import_excel(conn)
    finally:
        conn.close()
    print(f'Imported corrections for {n} ad(s) from {exporter.EXCEL_FILE}')
    return 0


def cmd_serve(args):
    server.serve()
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog='jobs.py', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command')

    p_fetch = sub.add_parser('fetch', help='Scrape, download new ads, update statuses')
    p_fetch.set_defaults(func=cmd_fetch)

    p_exp = sub.add_parser('export-excel', help='Write job_ads.xlsx from the database')
    p_exp.add_argument('--overwrite', action='store_true',
                       help='Replace an existing job_ads.xlsx (import edits first!)')
    p_exp.set_defaults(func=cmd_export_excel)

    p_imp = sub.add_parser('import-excel', help='Fold job_ads.xlsx edits back into the database')
    p_imp.set_defaults(func=cmd_import_excel)

    p_serve = sub.add_parser('serve', help='Serve the dashboard on http://localhost:8080')
    p_serve.set_defaults(func=cmd_serve)

    return parser


def main():
    # Operate relative to the script so the DB, pdfs/, and dashboard live together
    # regardless of where the command (or a scheduler) was launched.
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        import tui
        return tui.run()
    return args.func(args) or 0


if __name__ == '__main__':
    sys.exit(main())
