"""Excel export/import for the job-ad repository.

The DB is authoritative; Excel is a round-trip view. `export_excel` writes one row
per ad; `import_excel` folds edited fields and Needs Review back into the DB as
overrides (matched by the hidden Hash column). Notes are not part of the Excel
round-trip; they live in the hosted dashboard.

Date columns emit a real date-typed cell when the value parses as a date, so Excel
sorts them chronologically; unparseable values ("ab sofort") stay as text and
cluster separately. A user can hand-edit a text cell into a real date.
"""

import datetime as dt

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

import extract
import store

EXCEL_FILE = 'job_ads.xlsx'
LIST_SEP = '\n'

# (header, field_key, kind). kind drives cell typing and round-trip handling.
#   meta      - read-only DB metadata (not imported back)
#   text      - overridable text field
#   list      - overridable JSON-array field (emails/phones)
#   date      - overridable date-or-text field
#   review    - the needs_review flag
#   pdf       - hyperlink to the PDF file
COLUMNS = [
    ('Hash', 'hash', 'meta'),
    ('Status', 'status', 'meta'),
    ('First Seen', 'first_seen', 'meta'),
    ('Last Seen', 'last_seen', 'meta'),
    ('Department', 'department', 'text'),
    ('Job-ID', 'job_id', 'text'),
    ('Position Title', 'position_title', 'text'),
    ('Working Group', 'working_group', 'text'),
    ('Position Start Date', 'position_start_date', 'date'),
    ('Application Deadline', 'application_deadline', 'date'),
    ('Duration of Contract', 'duration_of_contract', 'text'),
    ('Pay', 'pay', 'text'),
    ('Workload', 'workload', 'text'),
    ('Contact Name', 'contact_name', 'text'),
    ('Emails', 'emails', 'list'),
    ('Phones', 'phones', 'list'),
    ('Needs Review', 'needs_review', 'review'),
    ('Original PDF Name', 'original_pdf_name', 'meta'),
    ('PDF', 'pdf', 'pdf'),
]

PDF_DIR = 'data/pdfs'


def _date_or_text(value):
    """Return a date object if value parses as dd.mm.yyyy, else the raw text."""
    iso = extract.normalize_date(value or '')
    if iso:
        try:
            return dt.date.fromisoformat(iso)
        except ValueError:
            return value
    return value


def export_excel(conn, path=EXCEL_FILE, overwrite=False):
    """Write the DB to an Excel file. Refuses to clobber unless overwrite=True."""
    import os
    if os.path.exists(path) and not overwrite:
        raise FileExistsError(
            f'{path} already exists. Re-run with overwrite to replace it '
            f'(make sure you have run import-excel on any edits first).')

    wb = Workbook()
    ws = wb.active
    ws.title = 'Job Ads'

    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill('solid', fgColor='305496')
    review_fill = PatternFill('solid', fgColor='FFF2CC')

    for col, (header, _key, _kind) in enumerate(COLUMNS, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill

    rows = store.all_jobs(conn)
    for r, row in enumerate(rows, 2):
        needs_review = bool(row['needs_review'])
        for c, (_header, key, kind) in enumerate(COLUMNS, 1):
            cell = ws.cell(row=r, column=c)
            if kind == 'meta':
                cell.value = row[key] if key in row.keys() else ''
            elif kind == 'text':
                cell.value = store.effective(row, key)
            elif kind == 'list':
                cell.value = LIST_SEP.join(store.effective(row, key))
            elif kind == 'date':
                val = _date_or_text(store.effective(row, key))
                cell.value = val
                if isinstance(val, dt.date):
                    cell.number_format = 'YYYY-MM-DD'
            elif kind == 'review':
                cell.value = 'yes' if needs_review else 'no'
            elif kind == 'pdf':
                fname = row['pdf_filename']
                if fname:
                    cell.value = row['original_pdf_name'] or fname
                    cell.hyperlink = f'{PDF_DIR}/{fname}'
                    cell.font = Font(color='0000FF', underline='single')
            if needs_review and kind not in ('meta', 'pdf'):
                cell.fill = review_fill

    # Hide the hash column (round-trip key, not for human eyes).
    ws.column_dimensions['A'].hidden = True
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = f'A1:{get_column_letter(len(COLUMNS))}{len(rows) + 1}'

    for c, (header, _key, kind) in enumerate(COLUMNS, 1):
        letter = get_column_letter(c)
        width = max(len(header) + 2, 14)
        if kind in ('text', 'list'):
            width = 28
        if kind == 'meta' and header == 'Hash':
            width = 12
        ws.column_dimensions[letter].width = min(width, 45)

    wb.save(path)
    return len(rows)


def _cell_to_text(value):
    if value is None:
        return ''
    if isinstance(value, dt.datetime):
        return value.strftime('%d.%m.%Y')
    if isinstance(value, dt.date):
        return value.strftime('%d.%m.%Y')
    return str(value).strip()


def import_excel(conn, path=EXCEL_FILE):
    """Read an edited Excel back into the DB as overrides. Returns count updated."""
    wb = load_workbook(path)
    ws = wb['Job Ads'] if 'Job Ads' in wb.sheetnames else wb.active

    headers = [c.value for c in ws[1]]
    index = {h: i for i, h in enumerate(headers)}
    if 'Hash' not in index:
        raise ValueError('Excel is missing the Hash column; cannot match rows.')

    updated = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        hash_ = _cell_to_text(row[index['Hash']])
        if not hash_:
            continue
        new_values = {}
        for header, key, kind in COLUMNS:
            if kind == 'text' or kind == 'date':
                new_values[key] = _cell_to_text(row[index[header]])
            elif kind == 'list':
                raw = _cell_to_text(row[index[header]])
                items = [p.strip() for p in raw.replace(';', '\n').splitlines() if p.strip()]
                new_values[key] = items
        review_val = _cell_to_text(row[index['Needs Review']]).lower() if 'Needs Review' in index else ''
        needs_review = review_val in ('yes', 'true', '1', 'y') if review_val else None
        if store.apply_overrides(conn, hash_, new_values, needs_review=needs_review):
            updated += 1
    conn.commit()
    return updated
