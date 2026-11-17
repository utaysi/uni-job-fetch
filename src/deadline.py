"""Application deadline detection.

Plain text logic with no PDF library, shared by the extractor (new ads), the
fetch (re-checks every stored ad, so improvements here reach old ads too) and
the dashboard data (server.jobs_payload).

detect() looks at the value read from the ad's labelled box first, then at the
ad's full text, and returns a Deadline of one of these kinds:

  date      a fixed date ("15.09.2026", "25. Oktober 2026", "October 25, 2026")
  relative  a period after the ad was posted ("mind. 2 Wochen"); the dashboard
            estimates the date from when the ad was first seen
  rolling   no deadline: applications are taken any time ("laufend",
            "jederzeit", "Dauerausschreibung", "in den kommenden Wochen")
  none      the ad gives no deadline at all
  unknown   the PDF has no text layer (a scanned image), so nothing can be read
  text      a manual correction (Excel) that is not a date; shown as written

Order of precedence: a date in the box, a labelled date in the text
("Bewerbungsfrist: ..."), a date in the application sentence ("... senden Sie
bitte bis zum ..."), a period in the box or text, a rolling keyword in the box
or text. A concrete date always wins, because several ads say "2 Wochen" in the
box but give the actual date in the text.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta

MONTHS = {
    'januar': 1, 'jänner': 1, 'january': 1, 'jan': 1,
    'februar': 2, 'february': 2, 'febr': 2, 'feb': 2,
    'märz': 3, 'maerz': 3, 'march': 3, 'mär': 3, 'mrz': 3, 'mar': 3,
    'april': 4, 'apr': 4,
    'mai': 5, 'may': 5,
    'juni': 6, 'june': 6, 'jun': 6,
    'juli': 7, 'july': 7, 'jul': 7,
    'august': 8, 'aug': 8,
    'september': 9, 'sept': 9, 'sep': 9,
    'oktober': 10, 'october': 10, 'okt': 10, 'oct': 10,
    'november': 11, 'nov': 11,
    'dezember': 12, 'december': 12, 'dez': 12, 'dec': 12,
}
_MONTH = '|'.join(sorted(MONTHS, key=len, reverse=True))  # longest first

# Each pattern yields (day, month, year) groups; year may be missing or two digits.
_DATE_PATTERNS = [
    # 2026-09-15
    (re.compile(r'(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)'), 'ymd'),
    # 15.09.2026, 15. 09. 2026, 15.09.26
    (re.compile(r'(?<![\d.])(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4}|\d{2})(?!\d)'), 'dmy'),
    # 25. Oktober 2026, 1. Sept. 2026, 25th October 2026, 25 Oktober (year inferred)
    (re.compile(rf'(?<!\d)(\d{{1,2}})(?:\.|st|nd|rd|th)?\s*(?:of\s+)?({_MONTH})\b\.?(?:\s*,?\s*(\d{{4}})(?!\d))?',
                re.I), 'd_name_y'),
    # October 25, 2026
    (re.compile(rf'\b({_MONTH})\b\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})(?!\d)', re.I), 'name_d_y'),
    # 15.09. (year inferred)
    (re.compile(r'(?<![\d.])(\d{1,2})\.\s?(\d{1,2})\.(?!\s?\d)'), 'dm'),
]

_NUMBER_WORDS = {
    'ein': 1, 'eine': 1, 'einer': 1, 'zwei': 2, 'drei': 3, 'vier': 4, 'fünf': 5, 'sechs': 6,
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
}
_UNIT_DAYS = {'w': 7, 't': 1, 'd': 1, 'm': 30}
_PERIOD = (r'(\d{1,2}|ein(?:e|er)?|zwei|drei|vier|fünf|sechs|one|two|three|four|five|six)\s*'
           r'(wochen?|tagen?|monat(?:e|en)?|weeks?|days?|months?)\b')
# In the box any period is the deadline ("mind. 2 Wochen", "2 Wochen", "14 Tage").
_PERIOD_IN_BOX = re.compile(r'(?:(?:mind(?:estens|\.)?|at least)\s*)?' + _PERIOD, re.I)
# In the text only a period tied to the publication, so "Praktikum von mindestens
# 6 Wochen" is not mistaken for a deadline.
_PERIOD_IN_TEXT = re.compile(
    r'(?:(?:mind(?:estens|\.)?|at least)\s*)?' + _PERIOD +
    r'\s*(?:nach\s+(?:der\s+|dem\s+)?(?:Veröffentlichung|Erscheinen|Ausschreibung)|after\s+(?:publication|posting))',
    re.I)

# A box value that means "no deadline".
_ROLLING_VALUE = re.compile(
    r'\b(?:fort)?laufend\b|\bjederzeit\b|dauerausschreibung|\bdauerhaft\b|\bbis auf weiteres\b|'
    r'\bbis zur (?:stellen)?besetzung\b|\boffen\b|\bkeine?\b|\bohne\b|\b(?:ab )?sofort\b|'
    r'\bkommenden wochen\b|\bimmer wieder\b|\bnach bedarf\b|\bongoing\b|\brolling\b|\bopen\b|'
    r'\bany ?time\b|\buntil filled\b', re.I)

# Phrases in the text that mean "no deadline". The value stored is the phrase
# itself (or a short form of it), which _ROLLING_VALUE recognizes on the next run.
_ROLLING_TEXT = [
    (re.compile(r'\bDauerausschreibung\b', re.I), None),
    (re.compile(r'(?:bewerb|unterlagen)[^.!?]{0,120}?\b(jederzeit|fortlaufend|laufend|bis auf Weiteres|'
                r'in den kommenden Wochen)\b', re.I), None),
    (re.compile(r'\bfortlaufend\b', re.I), None),
    (re.compile(r'\bimmer wieder\b[^.!?]{0,160}?\bgesucht\b', re.I), 'immer wieder'),
    (re.compile(r'zum Zeitpunkt des Bedarfs vorliegenden Bewerbungen', re.I), 'nach Bedarf'),
    (re.compile(r'(?:applications?|apply)[^.!?]{0,80}?\b(on a rolling basis|any ?time|until (?:the position is )?filled)\b',
                re.I), None),
]

# A label that introduces the deadline in running text.
_DEADLINE_LABEL = re.compile(
    r'(?:Ende der Bewerbungsfrist|Bewerbungsfrist|Bewerbungsschluss|Bewerbungsende|Einsendeschluss|'
    r'Einsendefrist|Application deadline|Closing date|Deadline)\b\s*[:\-–]?\s*'
    r'(?:(?:ist|endet|läuft|am|der|den|zum|bis|spätestens|on|is)\s+)*', re.I)

# "bis", "bis zum", "spätestens am", "until", "by" right before a date.
_UNTIL = re.compile(
    r'\b(?:bis(?:\s+(?:zum|spätestens(?:\s+(?:zum|am))?|einschließlich|einschl\.))?|'
    r'spätestens(?:\s+(?:am|zum|bis(?:\s+zum)?))?|until|by)\s+', re.I)
# The sentence must be about applying ...
_APPLY_CUE = re.compile(r'bewerb|unterlagen|einsend|einreich|apply|application', re.I)
# ... and the words right before "bis" must not describe the contract period.
_NOT_DEADLINE = re.compile(r'befrist|laufzeit|vertrag|\bvom\b|zwischen|zunächst|dauer', re.I)
# Sentence ends, ignoring common abbreviations such as "o. g." or "z. B.".
_SENTENCE_END = re.compile(r'(?<!\bo)(?<!\bg)(?<!\bz)(?<!\bd)(?<!\bu)(?<!\bca)(?<!\bDr)(?<!\bNr)[.!?]\s+(?=[A-ZÄÖÜ])')

# Fewer words than this means the PDF is a scanned image without a text layer.
_MIN_WORDS = 20


@dataclass
class Deadline:
    kind: str          # date, relative, rolling, none, unknown, text
    value: str = ''    # what the ad says; stored as application_deadline
    iso: str = ''      # YYYY-MM-DD for kind "date"
    days: int = 0      # period after posting for kind "relative"
    source: str = ''   # "box" or "text": where it was found


def _flatten(text):
    """One line of text: join words split at line ends, collapse whitespace."""
    text = (text or '').replace('\xa0', ' ').replace('', ' ').replace('­', '')
    text = re.sub(r'(\w)-\s*\n\s*(?=[a-zäöüß])', r'\1', text)  # "Bewerbungs-\nfrist"
    return re.sub(r'\s+', ' ', text).strip()


def _infer_year(day, month, ref):
    """Year for a date written without one: the occurrence closest to a month after ref."""
    target = ref + timedelta(days=30)
    best = None
    for year in (ref.year - 1, ref.year, ref.year + 1):
        try:
            d = date(year, month, day)
        except ValueError:
            continue
        if best is None or abs(d - target) < abs(best - target):
            best = d
    return best


def find_dates(text, ref=None):
    """All dates in text as (start, end, date, matched text), in order, without overlaps."""
    ref = ref or date.today()
    found = []
    for pattern, shape in _DATE_PATTERNS:
        for m in pattern.finditer(text):
            g = m.groups()
            try:
                if shape == 'ymd':
                    d = date(int(g[0]), int(g[1]), int(g[2]))
                elif shape == 'dmy':
                    year = int(g[2]) + (2000 if len(g[2]) == 2 else 0)
                    d = date(year, int(g[1]), int(g[0]))
                elif shape == 'd_name_y':
                    month = MONTHS[g[1].lower()]
                    d = date(int(g[2]), month, int(g[0])) if g[2] else _infer_year(int(g[0]), month, ref)
                elif shape == 'name_d_y':
                    d = date(int(g[2]), MONTHS[g[0].lower()], int(g[1]))
                else:  # dm
                    d = _infer_year(int(g[0]), int(g[1]), ref)
            except (ValueError, KeyError):
                continue
            if d and 2000 <= d.year <= 2100:
                found.append((m.start(), m.end(), d, m.group(0).strip(' ,')))
    # Keep the longest match where matches overlap ("25. Oktober 2026" over "25. Okt").
    found.sort(key=lambda f: (f[0], -(f[1] - f[0])))
    out = []
    for f in found:
        if out and f[0] < out[-1][1]:
            continue
        out.append(f)
    return out


def _date_at(text, pos, ref, slack=3):
    """The date starting at pos (allowing a few characters of slack), or None."""
    for start, end, d, raw in find_dates(text[pos:pos + 60], ref):
        if start <= slack:
            return d, raw
        break
    return None


def _period(match):
    n, unit = match.group(1).lower(), match.group(2).lower()
    count = int(n) if n.isdigit() else _NUMBER_WORDS.get(n, 0)
    return count * _UNIT_DAYS.get(unit[0], 0)


def _sentence_before(text, pos, limit=220):
    before = text[max(0, pos - limit):pos]
    ends = list(_SENTENCE_END.finditer(before))
    return before[ends[-1].end():] if ends else before


def _date_in_text(flat, ref):
    """A deadline date in running text: after a label, or in the application sentence."""
    for m in _DEADLINE_LABEL.finditer(flat):
        hit = _date_at(flat, m.end(), ref)
        if hit:
            return hit
    for m in _UNTIL.finditer(flat):
        hit = _date_at(flat, m.end(), ref, slack=1)
        if not hit:
            continue
        sentence = _sentence_before(flat, m.start())
        if not _APPLY_CUE.search(sentence):
            continue
        near = flat[max(0, m.start() - 40):m.start()]
        if _NOT_DEADLINE.search(near):
            continue
        if find_dates(flat[max(0, m.start() - 25):m.start()], ref):
            continue  # a range such as "30. April bis 06. Mai"
        return hit
    return None


def _rolling_in_text(flat):
    for pattern, label in _ROLLING_TEXT:
        m = pattern.search(flat)
        if m:
            return label or (m.group(1) if m.groups() else m.group(0))
    return None


def detect(box_value, text, ref=None, trust_box=False):
    """Classify an ad's application deadline.

    box_value: the value read from the ad's labelled box (or a manual correction).
    text: the ad's full text. ref: the date the ad was first seen, used to complete
    dates written without a year. trust_box: the value is a manual correction, so
    the text is not searched.
    """
    value = _flatten(box_value)
    flat = '' if trust_box else _flatten(text)

    dates = find_dates(value, ref)
    if dates:
        d, raw = dates[0][2], dates[0][3]
        return Deadline('date', raw, d.isoformat(), source='box')

    if flat:
        hit = _date_in_text(flat, ref)
        if hit:
            return Deadline('date', hit[1], hit[0].isoformat(), source='text')

    m = _PERIOD_IN_BOX.search(value)
    if m and _period(m):
        return Deadline('relative', value, days=_period(m), source='box')
    if flat:
        m = _PERIOD_IN_TEXT.search(flat)
        if m and _period(m):
            return Deadline('relative', m.group(0), days=_period(m), source='text')

    if _ROLLING_VALUE.search(value):
        return Deadline('rolling', value, source='box')
    if flat:
        phrase = _rolling_in_text(flat)
        if phrase:
            return Deadline('rolling', phrase, source='text')

    if trust_box:
        return Deadline('text', value, source='box') if value else Deadline('none')
    if len(flat.split()) < _MIN_WORDS:
        return Deadline('unknown')
    return Deadline('none')
