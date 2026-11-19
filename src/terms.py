"""Contract duration and working hours as numbers.

Plain text logic with no PDF library, like deadline.py. The dashboard data
(server.jobs_payload) runs it for every ad on every build, so improvements here
reach older ads too.

duration() reads the "Befristung" value from the ad's labelled box and returns
the contract length in months:

  "12 Monate", "1 Jahr", "Monate 23"   stated: taken as is
  "3-6 Monate"                        a range: the upper number, as an estimate
  "01.12.2026 - 31.12.2028"           both dates: counted between them
  "31.12.2027"                        an end date: counted from the start date
                                      ("Eintrittstermin"); if the ad gives none
                                      ("nächstmöglich"), from the day it was first
                                      seen, as an estimate
  "Wintersemester 2026/27"            the official semester dates, as an estimate
  "Semesterende"                      from the start (or first seen) to the end
                                      of that semester, as an estimate
  "unbefristet"                       permanent

hours() reads the "Umfang" value and returns hours per month:

  "40 Std./Monat", "bis zu 40 Std./Monat"   stated: taken as is (the cap for "bis zu")
  "30 - 37 Std./Mo."                       a range: the upper number, as an estimate
  "10 Std./Woche"                          weekly hours times 52/12, as an estimate
  "Je 88 Std. insges."                     total hours divided by the duration, as an
                                           estimate (empty when the duration is unknown)
  "Vollzeit", "Teilzeit (50 %)"            that share of a 40-hour week, as an estimate

When the box gives nothing usable, both look for the same information in the
ad's full text, but only in phrases that clearly describe the contract
("befristet bis zum ...", "für 3-6 Monate", "20 Stunden pro Monat"), so a
requirement such as "mindestens 4 Semester" is not taken for a duration.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta

from deadline import MONTHS, find_dates, _flatten as flatten

# Semesters at Marburg: winter 1 Oct to 31 Mar, summer 1 Apr to 30 Sep.
AVG_MONTH_DAYS = 365.25 / 12
WEEKS_PER_MONTH = 52 / 12
FULL_TIME_WEEKLY = 40  # TV-H (Hessen) full-time week

_MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

_NUMBER_WORDS = {
    'ein': 1, 'eine': 1, 'einem': 1, 'einen': 1, 'einer': 1, 'zwei': 2, 'drei': 3, 'vier': 4,
    'fünf': 5, 'sechs': 6, 'sieben': 7, 'acht': 8, 'neun': 9, 'zehn': 10, 'elf': 11, 'zwölf': 12,
    'achtzehn': 18, 'vierundzwanzig': 24,
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'nine': 9, 'twelve': 12,
}
_WORDS = '|'.join(sorted(_NUMBER_WORDS, key=len, reverse=True))
_NUM = r'\d{1,3}(?:[.,]\d)?'
_COUNT = rf'(?:{_NUM}|{_WORDS})'
_RANGE_SEP = r'\s*(?:-|–|bis)\s*'

# Months per unit. Semesters only count in the box: in running text "4 Semester"
# is usually a requirement for applicants, not the contract length.
_UNIT_MONTHS = {'mon': 1, 'jah': 12, 'yea': 12, 'sem': 6}
_UNIT = r'(monat(?:e|en|s)?|mon\.|jahr(?:e|en|es)?|months?|years?|semestern?)'
_UNIT_NO_SEMESTER = r'(monat(?:e|en|s)?|mon\.|jahr(?:e|en|es)?|months?|years?)'
_PERIOD = re.compile(rf'(?<![\w.,])({_COUNT})(?:{_RANGE_SEP}({_COUNT}))?\s*{_UNIT}(?![a-zäöüß])', re.I)
# The box is sometimes read in the wrong order: "Monate 23".
_PERIOD_REVERSED = re.compile(rf'^{_UNIT}\s*(\d{{1,3}})$', re.I)
_HALF_YEAR = re.compile(r'\bhalbes\s+Jahr\b', re.I)

_PERMANENT = re.compile(r'\bunbefristet\w*', re.I)
_SEMESTER_END = re.compile(r'\bSemesterende\b', re.I)
_WINTER = re.compile(r'\b(?:Winter(?:semester)?|WiSe|WS)\s*(\d{4}|\d{2})\b', re.I)
_SUMMER = re.compile(r'\b(?:Sommer(?:semester)?|SoSe|SS)\s*(\d{4}|\d{2})\b', re.I)

_MONTH_NAME = '|'.join(sorted(MONTHS, key=len, reverse=True))
_DATE_TEXT = rf'(?:\d{{1,2}}\.\s?\d{{1,2}}\.\s?\d{{2,4}}|\d{{1,2}}\.?\s*(?:{_MONTH_NAME})\.?\s*\d{{4}})'
_PERIOD_TEXT = rf'{_COUNT}(?:{_RANGE_SEP}{_COUNT})?\s*{_UNIT_NO_SEMESTER}(?![a-zäöüß])'

# Phrases in the full text that state the contract length, tried in this order.
_DURATION_IN_TEXT = [
    # "Befristung: 31.03.2024" (the box, flattened into the text)
    re.compile(rf'\bBefristung\s*:?\s*(?P<v>{_DATE_TEXT}|{_PERIOD_TEXT}|unbefristet)', re.I),
    # "befristet bis zum 31.05.2027", "befristet für 6 Monate", "befristet bis zum Semesterende"
    re.compile(rf'\bbefristet\w*\s+(?:(?:zunächst|vorerst|bis|zum|auf|für|die|eine[nm]?|Dauer|von|'
               rf'Zeitraum)\s+){{0,4}}(?P<v>{_DATE_TEXT}|{_PERIOD_TEXT}|Semesterende)', re.I),
    # "für 3-6 Monate", "für die Dauer von drei Monaten", "in der Regel fünf Monaten"
    re.compile(rf'\b(?:für|Dauer\s+von|Laufzeit\s+von|Zeitraum\s+von|in\s+der\s+Regel|vorzugsweise)\s+'
               rf'(?:(?:die|eine[nm]?|ca\.|circa|etwa|zunächst|mindestens|von)\s+)*(?P<v>{_PERIOD_TEXT})', re.I),
]
# "zum 01.12.2026 befristet bis ...": the start date just before "befristet".
_START_BEFORE = re.compile(rf'\b(?:ab|zum|vom)\s+(?:dem\s+)?(?P<v>{_DATE_TEXT})[^.]{{0,40}}$', re.I)

_HOURS = r'(?:Std|Stunden|Stunde|h)\b\.?'
_PER = r'\s*(?:/|pro|im|je|per)?\s*'
_MONTHLY = r'(?:Monat\w*|monatl\w*|mtl\b\.?|Mo\b\.?|month\w*)'
_WEEKLY = r'(?:Woche\w*|wöchentl\w*|week\w*)'
_PER_MONTH = re.compile(rf'(?<![\d.,])({_NUM})(?:{_RANGE_SEP}({_NUM}))?\s*{_HOURS}{_PER}{_MONTHLY}', re.I)
# The box read in the wrong order: "Std./Monat 40".
_PER_MONTH_REVERSED = re.compile(rf'{_HOURS}\s*/\s*{_MONTHLY}\s*({_NUM})(?![\d.,/])', re.I)
_PER_WEEK = [
    re.compile(rf'(?<![\d.,])({_NUM})(?:{_RANGE_SEP}({_NUM}))?\s*{_HOURS}{_PER}{_WEEKLY}', re.I),
    re.compile(rf'(?<![\d.,])({_NUM})(?:{_RANGE_SEP}({_NUM}))?\s*Wochenstunden', re.I),
    re.compile(rf'\bwöchentliche\w*\s+(?:Arbeitszeit|Stundenzahl)\s+(?:von|beträgt)\s+(?:\w+\s+){{0,2}}?'
               rf'({_NUM})(?:{_RANGE_SEP}({_NUM}))?\s*{_HOURS}', re.I),
]
_TOTAL = [
    re.compile(rf'(?<![\d.,])({_NUM})\s*{_HOURS}\s*\(?\s*(?:insg\w*|gesamt|in\s+total|total)', re.I),
    re.compile(rf'\b(?:insg\w*|gesamt)\.?\s*({_NUM})\s*{_HOURS}', re.I),
]
_FULL_TIME = re.compile(r'\bVollzeit(?:stelle)?\b|\bfull[- ]time\b', re.I)
_PART_TIME_SHARE = [
    re.compile(r'\bTeilzeit\w*\s*\(?\s*(\d{1,3})\s*%', re.I),
    re.compile(r'(?<![\d.,])(\d{1,3})\s*%\s*-?\s*(?:Stelle|Teilzeit)', re.I),
]
_HALF_POST = re.compile(r'\bhalbe\s+Stelle\b', re.I)


@dataclass
class Duration:
    months: float | None = None  # contract length; None when unknown or permanent
    estimate: bool = False       # counted from a guess (first seen, semester dates, upper end of a range)
    permanent: bool = False      # "unbefristet"
    basis: str = ''              # one sentence for the dashboard tooltip: what the ad says, how it was counted


@dataclass
class Hours:
    per_month: float | None = None  # None when unknown
    estimate: bool = False          # converted (weekly, total, full or part time) or the upper end of a range
    total: float | None = None      # the ad's total hours, when it gives those instead of a monthly figure
    basis: str = ''


def _fmt(d):
    return f'{d.day} {_MON[d.month - 1]} {d.year}'


def _num(text):
    text = text.lower()
    if text in _NUMBER_WORDS:
        return _NUMBER_WORDS[text]
    return float(text.replace(',', '.'))


def _round(x):
    return round(x, 1)


def _months_between(start, end):
    """Months from start to end, both days included: 1 Aug to 31 Jul is 12.0."""
    after = end + timedelta(days=1)
    whole = (after.year - start.year) * 12 + after.month - start.month
    return whole + (after.day - start.day) / AVG_MONTH_DAYS


def _semester(d):
    """(start, end, name) of the semester a date falls in."""
    if 4 <= d.month <= 9:
        return date(d.year, 4, 1), date(d.year, 9, 30), f'summer semester {d.year}'
    year = d.year if d.month >= 10 else d.year - 1
    return date(year, 10, 1), date(year + 1, 3, 31), f'winter semester {year}/{str(year + 1)[2:]}'


def _named_semester(text):
    """(start, end, name) for "Wintersemester 2026/27", "SoSe 2027" and the like, or None."""
    for pattern, month in ((_WINTER, 10), (_SUMMER, 4)):
        m = pattern.search(text)
        if m:
            year = int(m.group(1))
            year += 2000 if year < 100 else 0
            if 2000 <= year <= 2100:
                return _semester(date(year, month, 1))
    return None


def _start(start_value, first_seen, text_start=None):
    """When the contract starts: (date, exact, description), or None.

    The ad's start date if it gives one, then a date found in the text, then the
    semester it names, then the day the ad was first seen.
    """
    dates = find_dates(start_value, first_seen)
    if dates:
        return dates[0][2], True, f'starting {_fmt(dates[0][2])}'
    if text_start:
        return text_start, True, f'starting {_fmt(text_start)}'
    sem = _named_semester(start_value)
    if sem:
        return sem[0], False, f'starting with the {sem[2]} ({_fmt(sem[0])})'
    if first_seen:
        return first_seen, False, (f'counted from the day the ad was first seen ({_fmt(first_seen)}), '
                                   'since it gives no start date')
    return None


def _period(value):
    """(months, is_range) for a stated period, or None."""
    m = _PERIOD.search(value)
    if m:
        low = _num(m.group(1))
        high = _num(m.group(2)) if m.group(2) else low
        months = max(low, high) * _UNIT_MONTHS[m.group(3)[:3].lower()]
        if months > 0:
            return months, m.group(2) is not None
    m = _PERIOD_REVERSED.search(value)
    if m:
        months = int(m.group(2)) * _UNIT_MONTHS[m.group(1)[:3].lower()]
        if months > 0:
            return months, False
    if _HALF_YEAR.search(value):
        return 6, False
    return None


def _from_value(value, said, start_value, first_seen, text_start=None):
    """Duration from one stated value (the box, or a phrase from the text), or None."""
    if _PERMANENT.search(value):
        return Duration(permanent=True, basis=f'{said} (a permanent post).')

    p = _period(value)
    if p:
        months, is_range = p
        note = ' Counted as the longer one.' if is_range else ''
        return Duration(_round(months), estimate=is_range, basis=f'{said}.{note}')

    dates = find_dates(value, first_seen)
    if len(dates) >= 2:
        start, end = dates[0][2], dates[-1][2]
        if end > start:
            return Duration(_round(_months_between(start, end)), basis=f'{said}.')
    if dates:
        end = dates[-1][2]
        start = _start(start_value, first_seen, text_start)
        if start and end > start[0]:
            return Duration(_round(_months_between(start[0], end)), estimate=not start[1],
                            basis=f'{said}, {start[2]}.')
        return None

    sem = _named_semester(value)
    if sem:
        return Duration(_round(_months_between(sem[0], sem[1])), estimate=True,
                        basis=f'{said}: the {sem[2]}, {_fmt(sem[0])} to {_fmt(sem[1])}.')

    if _SEMESTER_END.search(value):
        start = _start(start_value, first_seen, text_start)
        if start:
            end = _semester(start[0])[1]
            return Duration(_round(_months_between(start[0], end)), estimate=True,
                            basis=f'{said}: until the end of the semester ({_fmt(end)}), {start[2]}.')
    return None


def _start_in_text(flat, pos, first_seen):
    """A start date right before "befristet" ("zum 01.12.2026 befristet bis ..."), or None."""
    m = _START_BEFORE.search(flat[max(0, pos - 80):pos])
    if m:
        dates = find_dates(m.group('v'), first_seen)
        if dates:
            return dates[0][2]
    return None


def duration(value, text='', start_value='', first_seen=None, trust_value=False):
    """The contract length of an ad.

    value: the "Befristung" value from the box (or a manual correction).
    text: the ad's full text, searched when the value gives nothing.
    start_value: the "Eintrittstermin" value. first_seen: the day the ad was first
    seen, used when the ad gives no start date. trust_value: the value is a manual
    correction, so the text is not searched.
    """
    value = flatten(value)
    start_value = flatten(start_value)
    if value:
        found = _from_value(value, f'The ad says "{value}"', start_value, first_seen)
        if found:
            return found
    if not trust_value:
        flat = flatten(text)
        for pattern in _DURATION_IN_TEXT:
            for m in pattern.finditer(flat):
                phrase = m.group(0)
                found = _from_value(m.group('v'), f'Found in the ad\'s text: "{phrase}"', start_value,
                                    first_seen, _start_in_text(flat, m.start(), first_seen))
                if found:
                    return found
        if _PERMANENT.search(flat):
            return Duration(permanent=True,
                            basis=f'Found in the ad\'s text: "{_PERMANENT.search(flat).group(0)}" (a permanent post).')
    if value:
        return Duration(basis=f'Could not read a duration from "{value}". Open the PDF to check.')
    return Duration(basis='The ad does not state a contract duration.')


def _upper(m):
    low = _num(m.group(1))
    high = _num(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else low
    return max(low, high), high != low


def _hours_from(value, said, months):
    """Hours from one piece of text (the box or the full text), or None."""
    m = _PER_MONTH.search(value) or _PER_MONTH_REVERSED.search(value)
    if m:
        h, is_range = _upper(m)
        if h > 0:
            note = ' Counted as the higher one.' if is_range else ''
            return Hours(_round(h), estimate=is_range, basis=f'{said}.{note}')

    for pattern in _PER_WEEK:
        m = pattern.search(value)
        if m:
            weekly, _ = _upper(m)
            if weekly > 0:
                return Hours(_round(weekly * WEEKS_PER_MONTH), estimate=True,
                             basis=f'{said}: {weekly:g} hours a week, about {weekly * WEEKS_PER_MONTH:.0f} a month.')

    for pattern in _TOTAL:
        m = pattern.search(value)
        if m:
            total = _num(m.group(1))
            if total <= 0:
                continue
            if months:
                return Hours(_round(total / months), estimate=True, total=total,
                             basis=f'{said}: {total:g} hours in total over {months:g} month{"" if months == 1 else "s"}.')
            return Hours(total=total, basis=f'{said}: {total:g} hours in total, but no duration to divide them by.')

    share = None
    if _FULL_TIME.search(value):
        share = 100
    else:
        for pattern in _PART_TIME_SHARE:
            m = pattern.search(value)
            if m and 0 < int(m.group(1)) <= 100:
                share = int(m.group(1))
                break
        if share is None and _HALF_POST.search(value):
            share = 50
    if share:
        weekly = FULL_TIME_WEEKLY * share / 100
        what = 'a full-time post' if share == 100 else f'{share} % of a full-time post'
        return Hours(_round(weekly * WEEKS_PER_MONTH), estimate=True,
                     basis=f'{said}: {what}, {weekly:g} hours a week, about {weekly * WEEKS_PER_MONTH:.0f} a month.')
    return None


def hours(value, text='', months=None, trust_value=False):
    """Working hours per month of an ad.

    value: the "Umfang" value from the box (or a manual correction). text: the
    ad's full text, searched when the value gives nothing. months: the contract
    length, to spread total hours over. trust_value: the value is a manual
    correction, so the text is not searched.
    """
    value = flatten(value)
    if value:
        found = _hours_from(value, f'The ad says "{value}"', months)
        if found:
            return found
    if not trust_value:
        flat = flatten(text)
        # Total hours last: "(je insg. 55 Std.)" explains a bare "55 Std" in the box.
        for patterns in ([_PER_MONTH], _PER_WEEK, _TOTAL):
            for pattern in patterns:
                m = pattern.search(flat)
                if m:
                    found = _hours_from(m.group(0), f'Found in the ad\'s text: "{m.group(0)}"', months)
                    if found:
                        return found
        m = _FULL_TIME.search(flat)
        if m:
            return _hours_from(m.group(0), f'Found in the ad\'s text: "{m.group(0)}"', months)
        for pattern in _PART_TIME_SHARE:
            m = pattern.search(flat)
            if m:
                found = _hours_from(m.group(0), f'Found in the ad\'s text: "{m.group(0)}"', months)
                if found:
                    return found
    if value:
        return Hours(basis=f'Could not read hours from "{value}". Open the PDF to check.')
    return Hours(basis='The ad does not state the working hours.')
