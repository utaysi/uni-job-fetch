"""PDF field extraction for Uni Marburg job ads.

Uses PyMuPDF (fitz) for coordinate-aware extraction. The standard university
template lays the core fields out as a labelled box (a row of labels, with each
value in the column beneath its label). We read those values by position, which
survives the cases where plain text extraction collapses the table into an
unlabelled row. Anything we cannot place falls back to regex over the full text.

Every extractor returns plain strings (empty string when not found). Date fields
additionally return a normalized ISO date when one is detectable.
"""

import re

import fitz

import deadline

# Core labelled box. The standard template prints these in a single row, each
# value sitting in the column directly beneath its label.
BOX_LABELS = ['Eintrittstermin', 'Bewerbungsfrist', 'Entgeltgruppe', 'Befristung', 'Umfang']

# Maps the visible label to our field key.
BOX_FIELD = {
    'Eintrittstermin': 'position_start_date',
    'Bewerbungsfrist': 'application_deadline',
    'Entgeltgruppe': 'pay',
    'Befristung': 'duration_of_contract',
    'Umfang': 'workload',
}

STANDARD_FINGERPRINT = 'Die 1527 gegründete Philipps-Universität'

EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
# German phone numbers: +49 / 0 followed by digits, spaces, slashes, dashes, parens.
PHONE_RE = re.compile(r'(?:\+49|0)[\d\s/\-()]{6,}\d')
DATE_RE = re.compile(r'(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})')


def get_words(doc):
    """All words across pages as (page, x0, y0, x1, y1, text)."""
    words = []
    for pno, page in enumerate(doc):
        for w in page.get_text('words'):
            words.append((pno, w[0], w[1], w[2], w[3], w[4]))
    return words


def full_text(doc):
    return '\n'.join(page.get_text() for page in doc)


def clean(text):
    """Collapse all whitespace (including newlines) to single spaces."""
    text = text.replace('\xa0', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def normalize_date(text):
    """Return an ISO date string if a dd.mm.yyyy date is present, else ''."""
    m = DATE_RE.search(text)
    if not m:
        return ''
    day, month, year = (int(x) for x in m.groups())
    try:
        from datetime import date
        return date(year, month, day).isoformat()
    except ValueError:
        return ''


def read_box_values(words):
    """Read the labelled box by position.

    Returns a dict of field_key -> value string for any label found. For each
    label, the value is every word sitting below the label and horizontally
    within that label's column, ordered top-to-bottom, stopping before the next
    label row or a large vertical gap.
    """
    # Locate each label word.
    labels = {}
    for (pno, x0, y0, x1, y1, text) in words:
        key = text.rstrip(':')
        if key in BOX_LABELS:
            labels[key] = (pno, x0, y0, x1, y1)

    if not labels:
        return {}

    # Column boundaries: midpoints between adjacent label left-edges on the row.
    placed = sorted(labels.items(), key=lambda kv: kv[1][1])  # by x0
    bounds = {}
    for i, (name, box) in enumerate(placed):
        left = box[1] - 8
        right = placed[i + 1][1][1] - 8 if i + 1 < len(placed) else box[1] + 200
        bounds[name] = (box[0], box[2], left, right)  # page, label_y0, x_left, x_right

    out = {}
    for name, (pno, label_y, xl, xr) in bounds.items():
        col_words = []
        for (wp, x0, y0, x1, y1, text) in words:
            if wp != pno:
                continue
            if y0 <= label_y + 1:
                continue  # at or above the label row
            cx = (x0 + x1) / 2
            if xl <= cx < xr:
                col_words.append((y0, x0, text))
        # Keep only the contiguous block right under the label (stop at a big gap).
        col_words.sort()
        value_parts = []
        prev_y = label_y
        for (y0, x0, text) in col_words:
            if y0 - prev_y > 28:  # gap too large; value block ended
                break
            value_parts.append(text)
            prev_y = y0
        out[BOX_FIELD[name]] = clean(' '.join(value_parts))
    return out


def read_deadline_box(pdf_path):
    """The raw Bewerbungsfrist value from the labelled box ('' if there is none)."""
    doc = fitz.open(pdf_path)
    try:
        return read_box_values(get_words(doc)).get('application_deadline', '')
    finally:
        doc.close()


def read_ausschreibungs_id(words, text):
    """Job-ID. Prefer the labelled value (right of or below the label)."""
    for (pno, x0, y0, x1, y1, w) in words:
        if w.rstrip(':') in ('Ausschreibungs-ID', 'AusschreibungsID'):
            # Collect words to the right on the same line, then the line below.
            same_line = [ww for ww in words
                         if ww[0] == pno and abs(ww[2] - y0) < 4 and ww[1] > x1]
            if same_line:
                same_line.sort(key=lambda ww: ww[1])
                return _clean_id(' '.join(ww[5] for ww in same_line))
            below = [ww for ww in words
                     if ww[0] == pno and 0 < ww[2] - y1 < 32 and abs(ww[1] - x0) < 90]
            if below:
                below.sort(key=lambda ww: (ww[2], ww[1]))
                return _clean_id(' '.join(ww[5] for ww in below))
    # Regex fallback over assorted ID labels.
    m = re.search(
        r'(?:Ausschreibungs[- ]?ID|Kennziffer|Referenznummer|Referenz|Job[- ]?ID|Stellennummer|ID)'
        r'\s*[:\-]?\s*([A-Za-zÄÖÜäöü0-9][A-Za-zÄÖÜäöü0-9\-/_.]+)',
        text)
    return _clean_id(m.group(1)) if m else ''


def _clean_id(raw):
    """Normalize a job id: join wrapped pieces, drop stray spaces around dashes."""
    val = clean(raw)
    val = val.strip(' -[](){}.,')
    val = re.sub(r'\s*-\s*', '-', val)
    return val.strip(' -[](){}.,')


def extract_working_group(text):
    """The working group from the 'Am Fachbereich ...' opening sentence.

    Handles both 'Am Fachbereich X, Arbeitsgruppe Y (Prof. ...)' and
    'Am Fachbereich X in der Arbeitsgruppe Y'. We capture from the AG/Institut
    marker up to the clause end ('ist'/'sind'), staying within the sentence.
    """
    flat = re.sub(r'\s+', ' ', text)
    m = re.search(
        r'(?:Arbeitsgruppe|AG|Institut|Studiendekanat|Dekanat|Praktik\w*|Hörsaalvorbereitung)\b'
        r'(.+?)\b(?:ist|sind)\b',
        flat)
    if m:
        wg = clean(m.group(0))
        wg = re.sub(r'\b(ist|sind)\s*$', '', wg).strip(' ,')
        if 0 < len(wg) <= 120:
            return wg
    return ''


def department_from_pdf(text):
    """Fallback department from the PDF's 'Am Fachbereich X' opener."""
    m = re.search(r'Am Fachbereich\s+([A-Za-zÄÖÜäöüß /-]+?)[,.]', text)
    if m:
        return 'Fachbereich ' + clean(m.group(1))
    return ''


def extract_position_title(text):
    """The standalone role line between '... als' and 'zu besetzen'."""
    m = re.search(r'\bals\s*\n+\s*(.+?)\s*\n+\s*zu besetzen', text, re.DOTALL)
    if m:
        title = clean(re.sub(r'\s+', ' ', m.group(1)))
        if 0 < len(title) <= 80:
            return title
    # Common explicit titles.
    m = re.search(r'(Studentische Hilfskräfte|Studentische Hilfskraft|'
                  r'Wissenschaftliche Hilfskraft|Wissenschaftliche Mitarbeiter[a-zäöü*:]*)', text)
    return clean(m.group(1)) if m else ''


def extract_contacts(words, text):
    """Contact name, emails, phones.

    Name: the line(s) after a 'Kontakt ...' label. Emails/phones: all matches.
    """
    emails = []
    for m in EMAIL_RE.findall(text):
        e = m.rstrip('.],)')
        if e not in emails:
            emails.append(e)
    phones = []
    for m in PHONE_RE.findall(text):
        p = clean(m).rstrip('].),')
        digits = re.sub(r'\D', '', p)
        if len(digits) >= 7 and p not in phones:
            phones.append(p)

    name = ''
    m = re.search(r'Kontakt[^\n]*\n+\s*([^\n]+)', text)
    if m:
        cand = clean(m.group(1))
        # Drop a line that is actually a phone/email/value row.
        if not EMAIL_RE.search(cand) and not PHONE_RE.search(cand) and len(cand) <= 80:
            name = cand
    return name, emails, phones


def regex_fallbacks(text):
    """Best-effort field values from plain text (used when the box is absent)."""
    out = {}
    out['position_start_date'] = _first(text, [
        r'(?:Eintrittstermin|Eintrittsdatum|Eintritt|Beschäftigungsbeginn|Arbeitsbeginn|Beginn)'
        r'\s*[:\-]?\s*([0-9]{1,2}\.[0-9]{1,2}\.[0-9]{2,4}|ab sofort|zum nächstmöglichen Zeitpunkt|'
        r'nächstmöglich[a-zäöü ]*|fortlaufend|Semesterbeginn)',
        r'\b(ab sofort|zum nächstmöglichen Zeitpunkt)\b',
    ])
    out['pay'] = _first(text, [
        r'\b(SHK-Vergütung)\b',
        r'\b((?:TV[- ]?L|TV[- ]?H|TVöD)(?:\s*[EG]\s?\d{1,2}[a-zA-Z]?)?)',
        r'\b(E\s?\d{1,2}[a-zA-Z]?\s*TV[- ]?[LH])',
        r'\b(Entgeltgruppe\s*\d{1,2}[a-zA-Z]?)',
    ])
    out['workload'] = _first(text, [
        r'((?:max\.\s*|bis\s*(?:zu\s*)?)?[0-9]{1,2}(?:,[0-9])?\s*Std\.?\s*/?\s*Monat)',
        r'\b(Vollzeit|Teilzeit(?:\s*\(\d{1,3}\s*%\))?)\b',
    ])
    out['duration_of_contract'] = _first(text, [
        r'befristet\s*(?:zunächst\s*)?(?:bis|für|auf|zum)\s*'
        r'([0-9]{1,2}\.[0-9]{1,2}\.[0-9]{2,4}|[0-9]+\s*(?:Monate?|Jahre?)|'
        r'(?:ein|zwei|drei|sechs)\s*(?:Monate?|Jahre?)|Semesterende|zum Semesterende)',
    ])
    return out


def _first(text, patterns):
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return clean(m.group(1))
    return ''


def extract(pdf_path):
    """Extract all fields from a PDF. Returns a dict of field -> value."""
    doc = fitz.open(pdf_path)
    try:
        words = get_words(doc)
        text = full_text(doc)
    finally:
        doc.close()

    is_standard = STANDARD_FINGERPRINT in text or bool(
        [w for w in words if w[5].rstrip(':') in BOX_LABELS])

    fields = {
        'position_start_date': '', 'application_deadline': '', 'pay': '',
        'workload': '', 'duration_of_contract': '',
    }

    box = read_box_values(words)
    fb = regex_fallbacks(text)
    for key in fields:
        fields[key] = box.get(key) or fb.get(key, '')

    fields['job_id'] = read_ausschreibungs_id(words, text)
    fields['working_group'] = extract_working_group(text)
    fields['position_title'] = extract_position_title(text)
    name, emails, phones = extract_contacts(words, text)
    fields['contact_name'] = name
    fields['emails'] = emails
    fields['phones'] = phones
    ft = text.replace('\xa0', ' ')
    ft = re.sub(r'[ \t]+', ' ', ft)
    fields['full_text'] = re.sub(r'\n{2,}', '\n', ft).strip()
    fields['template'] = 'standard' if is_standard else 'non-standard'

    fields['position_start_date_iso'] = normalize_date(fields['position_start_date'])
    # The box value is checked against the full text (see deadline.py): a date in
    # the text beats "2 Wochen" in the box, and an empty box can still be a
    # standing vacancy ("Dauerausschreibung") or give the date in a sentence.
    dl = deadline.detect(fields['application_deadline'], text)
    fields['application_deadline'] = dl.value
    fields['application_deadline_iso'] = dl.iso

    core = ['job_id', 'application_deadline', 'pay', 'workload']
    if is_standard:
        fields['needs_review'] = any(not fields[c] for c in core)
    else:
        fields['needs_review'] = True
    return fields


CORE_FIELD_ORDER = [
    'job_id', 'position_title', 'working_group',
    'position_start_date', 'application_deadline', 'duration_of_contract',
    'pay', 'workload', 'contact_name', 'emails', 'phones',
    'template', 'needs_review',
]


if __name__ == '__main__':
    import sys
    for path in sys.argv[1:]:
        print('=' * 70)
        print(path.split('__')[-1])
        f = extract(path)
        for k in CORE_FIELD_ORDER:
            print(f'  {k:22}: {f[k]!r}')
