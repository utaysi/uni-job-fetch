"""Tests for contract duration and hours per month. The cases are taken from
real ads on the board (2026-11-19 analysis), plus phrases that must not be read
as a contract length.

Run with: .venv/bin/python -m unittest discover -s tests
"""

import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import terms  # noqa: E402

SEEN = date(2026, 11, 16)


def dur(value='', text='', start='', seen=SEEN, **kw):
    return terms.duration(value, text, start, seen, **kw)


class StatedDuration(unittest.TestCase):
    def check(self, value, months, estimate=False):
        d = dur(value)
        self.assertEqual((d.months, d.estimate, d.permanent), (months, estimate, False), d)
        self.assertIn(value, d.basis)

    def test_months_and_years(self):
        self.check('12 Monate', 12)
        self.check('1 Monat', 1)
        self.check('1 Jahr', 12)
        self.check('ein Jahr', 12)
        self.check('zunächst für 12 Monate', 12)
        self.check('mindestens 6 Monate', 6)
        self.check('1 Jahr ab Einstellung', 12)

    def test_period_wins_over_semester_end(self):
        self.check('6 Monate zum Semesterende', 6)

    def test_box_read_in_the_wrong_order(self):
        self.check('Monate 23', 23)

    def test_range_takes_the_longer_as_estimate(self):
        self.check('3-6 Monate', 6, estimate=True)

    def test_permanent(self):
        d = dur('unbefristet')
        self.assertTrue(d.permanent)
        self.assertIsNone(d.months)


class EndDates(unittest.TestCase):
    def test_counted_from_the_start_date(self):
        d = dur('31.07.2027', start='01.08.2026')
        self.assertEqual((d.months, d.estimate), (12, False))
        self.assertEqual(dur('31.12.2027', start='15.02.2027').months, 10.5)
        self.assertEqual(dur('15.01.2028', start='15.01.2027').months, 12)
        self.assertEqual(dur('31.10.2027', start='01.11.2026 nächstmöglich').months, 12)

    def test_both_dates_in_the_value(self):
        d = dur('01.12.2026 - 31.12.2028', start='01.12.2026')
        self.assertEqual((d.months, d.estimate), (25, False))

    def test_vague_start_counts_from_first_seen_as_estimate(self):
        d = dur('31.03.2027', start='nächstmöglich')
        self.assertEqual((d.months, d.estimate), (4.5, True))
        self.assertIn('first seen (16 Nov 2026)', d.basis)

    def test_end_before_start_gives_nothing(self):
        d = dur('31.03.2024', start='nächstmöglich')
        self.assertIsNone(d.months)
        self.assertIn('Could not read', d.basis)


class Semesters(unittest.TestCase):
    def test_named_semester_uses_official_dates(self):
        d = dur('Wintersemester 2026/27', start='Wintersemester 2026/27')
        self.assertEqual((d.months, d.estimate), (6, True))
        self.assertIn('1 Oct 2026 to 31 Mar 2027', d.basis)

    def test_semester_end_from_first_seen(self):
        d = dur('Semesterende', seen=date(2026, 6, 24))
        self.assertEqual((d.months, d.estimate), (3.2, True))
        self.assertIn('30 Sep 2026', d.basis)

    def test_end_date_after_a_semester_start(self):
        self.assertEqual(dur('31.03.2027', start='Wintersemester 2026/27').months, 6)


class DurationInText(unittest.TestCase):
    def check(self, text, months, estimate=False, start=''):
        d = dur('', text, start)
        self.assertEqual((d.months, d.estimate), (months, estimate), d)
        self.assertIn("Found in the ad's text", d.basis)

    def test_contract_phrases(self):
        self.check('ist zum nächstmöglichen Zeitpunkt für die Dauer von 3 Monaten eine Stelle zu besetzen.', 3)
        self.check('Stellen im Umfang von in der Regel fünf Monaten zu je 32 Std./Monat', 5)
        self.check('Vertrag im Umfang von 30 Stunden/Monat über einen Zeitraum von sechs Mo-\nnaten.', 6)
        self.check('Studierende, die für mindestens 12 Monate für uns tätig werden können.', 12)
        self.check('suchen wir ab September 2026 für 3-6 Monate eine*n Praktikant*in', 6, estimate=True)

    def test_befristet_bis_with_start_in_the_sentence(self):
        self.check('Am Fachbereich Chemie ist zum 01.12.2026 befristet bis zum 31.05.2027 eine Stelle', 6)

    def test_box_flattened_into_the_text(self):
        self.check('Eintrittstermin: 01.02.2027 Befristung: 31.01.2032 Umfang: Teilzeit (50 %)', 60,
                   start='01.02.2027')

    def test_semester_end_in_text(self):
        d = dur('', 'Es sind semesterweise befristet bis zum Semesterende Stellen zu besetzen.')
        self.assertEqual((d.months, d.estimate), (4.5, True))

    def test_permanent_post(self):
        self.assertTrue(dur('', 'Wir bieten eine unbefristete Vollzeitstelle.').permanent)

    def test_box_value_wins_over_text(self):
        self.assertEqual(dur('12 Monate', 'befristet für 6 Monate').months, 12)

    def test_not_a_contract_length(self):
        for text in ['Sie studieren mindestens im 4. Semester.',
                     'Voraussetzung sind mindestens 4 Semester Studium.',
                     'Ein Praktikum von mindestens 6 Wochen.',
                     'Kündigungsfrist 3 Monate.',
                     'Befristung: Umfang: 30 Std./Monat Ausschreibungs-ID: fb15-0025']:
            d = dur('', text)
            self.assertIsNone(d.months, text)
            self.assertFalse(d.permanent, text)

    def test_correction_does_not_search_the_text(self):
        d = dur('ja', 'befristet für 6 Monate', trust_value=True)
        self.assertIsNone(d.months)


class Hours(unittest.TestCase):
    def check(self, value, per_month, estimate=False, months=None, text=''):
        h = terms.hours(value, text, months)
        self.assertEqual((h.per_month, h.estimate), (per_month, estimate), h)
        return h

    def test_stated_per_month(self):
        self.check('40 Std./Monat', 40)
        self.check('39,5 Std./Monat', 39.5)
        self.check('64h/Monat', 64)
        self.check('40 h/Monat', 40)
        self.check('23 Std. /mtl.', 23)
        self.check('max. 30 Std./ Monat', 30)

    def test_caps_take_the_stated_number(self):
        self.check('bis zu 40 Std./Monat', 40)
        self.check('Bis 22 Std./Monat', 22)

    def test_range_takes_the_higher_as_estimate(self):
        self.check('Jeweils 30 – 37 Std./Mo.', 37, estimate=True)

    def test_box_read_in_the_wrong_order(self):
        self.check('Std./Monat 40', 40)

    def test_total_spread_over_the_duration(self):
        h = self.check('Je 88 Std. insges.', 44, estimate=True, months=2)
        self.assertEqual(h.total, 88)
        self.check('108 Std. (insgesamt)', 108, estimate=True, months=1)
        self.check('54 Std. gesamt', 27, estimate=True, months=2)

    def test_total_without_duration_keeps_the_total(self):
        h = self.check('55 Std', None, text='3 Stellen (je insg. 55 Std.) einer Studentischen Hilfskraft')
        self.assertEqual(h.total, 55)

    def test_full_and_part_time(self):
        self.check('Vollzeit', 173.3, estimate=True)
        self.check('Teilzeit (50 %)', 86.7, estimate=True)
        self.check('Teilzeit', None)

    def test_weekly(self):
        self.check('10 Std./Woche', 43.3, estimate=True)
        self.check('', 173.3, estimate=True, text='mit einer wöchentlichen Arbeitszeit von 40 Stunden vergeben.')

    def test_in_text(self):
        self.check('', 35, text='Studentische Hilfskraft (bis zu 35 Stunden monatlich)')
        self.check('', 20, text='Die Arbeitszeit beträgt zunächst 20 Stunden pro Monat, der Stundenlohn 14,20 €.')

    def test_not_hours(self):
        for text in ['Uhrzeit: jeweils 4 Stunden (vormittags und/oder nachmittags)',
                     'Projektpraktikum Naturschutz (240 - 480 Stunden)',
                     'Studierende im Vollzeitstudium',
                     'der Stundenlohn beträgt 14,20 €']:
            self.assertIsNone(terms.hours('', text).per_month, text)


if __name__ == '__main__':
    unittest.main()
