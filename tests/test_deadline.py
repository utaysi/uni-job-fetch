"""Tests for deadline detection. Each case is modelled on a real ad that was
misread before (2026-11-17 analysis) or on a phrase that must not be mistaken
for a deadline.

Run with: .venv/bin/python -m unittest discover -s tests
"""

import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import deadline  # noqa: E402

# Ads have far more than 20 words; shorter texts count as scanned PDFs.
FILLER = ' '.join(['Text'] * 30) + '. '
REF = date(2026, 11, 17)


def detect(box='', text='', **kw):
    return deadline.detect(box, FILLER + text, ref=kw.pop('ref', REF), **kw)


class Dates(unittest.TestCase):
    def check(self, box, text, iso, value=None, source=None):
        dl = detect(box, text)
        self.assertEqual((dl.kind, dl.iso), ('date', iso), dl)
        if value is not None:
            self.assertEqual(dl.value, value)
        if source is not None:
            self.assertEqual(dl.source, source)

    def test_numeric_box_date(self):
        self.check('15.11.2026', '', '2026-11-15', '15.11.2026', 'box')

    def test_box_date_with_neighbouring_text(self):
        self.check('15.11.2026 E 13', '', '2026-11-15', '15.11.2026')
        self.check('Datum: 15.09.2026', '', '2026-09-15', '15.09.2026')

    def test_german_month_names(self):
        self.check('07. Juli 2026', '', '2026-07-07', '07. Juli 2026')
        self.check('25. Oktober 2026', '', '2026-10-25')
        self.check('3. März 2026', '', '2026-03-03')
        self.check('1. Sept. 2026', '', '2026-09-01')
        self.check('30 Juni 2026', '', '2026-06-30')

    def test_english_dates(self):
        self.check('October 25, 2026', '', '2026-10-25')
        self.check('25th October 2026', '', '2026-10-25')
        self.check('2026-10-25', '', '2026-10-25')

    def test_two_digit_year(self):
        self.check('15.09.26', '', '2026-09-15')

    def test_year_inferred_from_first_seen(self):
        dl = detect('', 'Ihre Bewerbungsunterlagen senden Sie bitte bis zum 15.09. an uns.', ref=date(2026, 8, 20))
        self.assertEqual(dl.iso, '2026-09-15')
        dl = detect('', 'Bewerbungen bitte bis zum 15. Januar an uns.', ref=date(2026, 12, 20))
        self.assertEqual(dl.iso, '2027-01-15')

    def test_text_date_beats_period_in_box(self):
        # Box said "mind. 2 Wochen" / "2 Wochen", the text gave the real date.
        self.check('mind. 2 Wochen', 'Ihre Bewerbungsunterlagen senden Sie bitte bis zum 25.02.2026 unter '
                   'Angabe der o. g. Ausschreibungs-ID.', '2026-02-25', source='text')
        self.check('2 Wochen', 'Ihre Bewerbungsunterlagen senden Sie bitte bis zum 02.12.2026 unter Angabe.',
                   '2026-12-02')

    def test_labelled_date_in_text_when_box_is_wrong(self):
        # The box reader picked up the line below the label instead of the value beside it.
        self.check('Bitte nutzen Sie unser  Onlineverfahren.',
                   'Jetzt bewerben! Kennziffer: e25065 Bewerbungsfrist: 25. August 2025 Bitte nutzen Sie unser '
                   'Onlineverfahren.', '2025-08-25', '25. August 2025', 'text')

    def test_label_split_over_two_lines(self):
        self.check('', 'Bewerbungs-\nfrist: 30.06.2026', '2026-06-30')

    def test_application_sentence_without_zum(self):
        self.check('', 'Ihre Bewerbungsunterlagen senden Sie bitte bis 15.09.2026 unter Angabe der o. g. '
                   'Ausschreibungs-ID in einer PDF-Datei.', '2026-09-15')

    def test_date_at_sentence_end(self):
        self.check('', 'Bewerbungen richten Sie bitte bis zum 25.02.2026.', '2026-02-25')

    def test_ab_sofort_bis(self):
        self.check('', 'Bewerbungen sind ab sofort bis zum 15.09.2026 möglich.', '2026-09-15')

    def test_spaetestens(self):
        self.check('', 'Bitte senden Sie Ihre Bewerbung spätestens am 3. Dezember 2026.', '2026-12-03')

    def test_english_application_sentence(self):
        self.check('', 'Please send your application by 30 November 2026 to the address below.', '2026-11-30')


class NotADeadline(unittest.TestCase):
    def assertKind(self, kind, box='', text=''):
        dl = detect(box, text)
        self.assertEqual(dl.kind, kind, dl)

    def test_contract_period(self):
        self.assertKind('none', text='Am Fachbereich ist zum nächstmöglichen Zeitpunkt befristet bis 31.10.2026 '
                        'eine Stelle zu besetzen. Ihre Bewerbungsunterlagen senden Sie bitte an uns.')

    def test_contract_period_in_application_sentence(self):
        self.assertKind('none', text='Bewerbungen für die Stelle, befristet bis 31.12.2026, bitte per E-Mail.')

    def test_date_range(self):
        self.assertKind('none', text='Ausbildungsseminar, 30. April bis 06. Mai 2026. Bewerbung: Schicke deine '
                        'Bewerbung an uns.')

    def test_letter_date(self):
        self.assertKind('none', text='Marburg, 14.01.2026 Werkstudent:in gesucht. Bewerbungen bitte per E-Mail.')

    def test_internship_length_is_not_a_period(self):
        self.assertKind('none', text='Wir freuen uns auf Praktikant:innen für mindestens 6 Wochen. Bewerbungen bitte '
                        'an uns.')

    def test_running_studies_is_not_rolling(self):
        self.assertKind('none', text='Laufendes Masterstudium. Einbindung in laufende Forschungsprojekte. Bewerbung '
                        'bitte per E-Mail.')

    def test_jederzeit_outside_the_application_sentence(self):
        self.assertKind('none', text='Falls ja, freuen wir uns auf Deine Bewerbung (Anschreiben, Lebenslauf). Für '
                        'weitere Fragen stehen wir jederzeit gerne zur Verfügung.')


class Periods(unittest.TestCase):
    def test_period_in_box(self):
        dl = detect('mind. 2 Wochen', 'Ihre Bewerbungsunterlagen senden Sie bitte an uns.')
        self.assertEqual((dl.kind, dl.days, dl.value), ('relative', 14, 'mind. 2 Wochen'))
        self.assertEqual(detect('14 Tage').days, 14)
        self.assertEqual(detect('drei Wochen').days, 21)

    def test_period_after_publication_in_text(self):
        dl = detect('', 'Ihre Bewerbungsunterlagen senden Sie bitte bis zum [mindestens 2 Wochen nach '
                    'Veröffentlichung] an uns.')
        self.assertEqual((dl.kind, dl.days), ('relative', 14))


class Rolling(unittest.TestCase):
    def check(self, box, text, value):
        dl = detect(box, text)
        self.assertEqual((dl.kind, dl.value), ('rolling', value), dl)

    def test_box_keywords(self):
        self.check('laufend', '', 'laufend')
        self.check('jederzeit', '', 'jederzeit')
        self.check('bis zur Besetzung der Stelle', '', 'bis zur Besetzung der Stelle')

    def test_standing_vacancy(self):
        self.check('', 'Semesterbeginn Dauerausschreibung SHK-Vergütung bis Semesterende', 'Dauerausschreibung')

    def test_any_time_in_application_sentence(self):
        self.check('', 'Ihre Bewerbungsunterlagen senden Sie bitte jederzeit unter Angabe der o. g. ID an uns.',
                   'jederzeit')

    def test_coming_weeks(self):
        self.check('', 'Ihre Bewerbung senden Sie bitte in den kommenden Wochen per E-Mail an uns.',
                   'in den kommenden Wochen')

    def test_recurring_search(self):
        self.check('', 'In der Arbeitsgruppe werden immer wieder, auch kurzfristig, Studentische Hilfskräfte '
                   'gesucht.', 'immer wieder')
        self.check('', 'Die Auswahl erfolgt auf Basis der zum Zeitpunkt des Bedarfs vorliegenden Bewerbungen.',
                   'nach Bedarf')

    def test_continuous_offer(self):
        self.check('', 'Wir bieten fortlaufend eine Praktikumsstelle an.', 'fortlaufend')

    def test_english(self):
        self.check('', 'Applications are reviewed on a rolling basis.', 'on a rolling basis')


class Other(unittest.TestCase):
    def test_scanned_pdf_is_unknown(self):
        self.assertEqual(deadline.detect('', '', ref=REF).kind, 'unknown')
        self.assertEqual(deadline.detect('', 'Praktikum im Regionalmanagement', ref=REF).kind, 'unknown')

    def test_no_deadline_stated(self):
        dl = detect('', 'Ihre Bewerbungsunterlagen senden Sie bitte per E-Mail an uns.')
        self.assertEqual((dl.kind, dl.value), ('none', ''))

    def test_manual_correction_is_trusted(self):
        text = FILLER + 'Bewerbungsfrist: 25.08.2025'
        self.assertEqual(deadline.detect('laufend', text, REF, trust_box=True).kind, 'rolling')
        self.assertEqual(deadline.detect('', text, REF, trust_box=True).kind, 'none')
        dl = deadline.detect('nach Absprache', text, REF, trust_box=True)
        self.assertEqual((dl.kind, dl.value), ('text', 'nach Absprache'))
        self.assertEqual(deadline.detect('01.12.2026', text, REF, trust_box=True).iso, '2026-12-01')

    def test_invalid_dates_are_ignored(self):
        self.assertEqual(detect('31.02.2026').kind, 'none')

    def test_stored_value_gives_the_same_result(self):
        # The fetch re-runs detection on the stored value, so it must be stable.
        cases = [
            ('mind. 2 Wochen', 'Ihre Bewerbungsunterlagen senden Sie bitte bis zum 25.02.2026 an uns.'),
            ('', 'Semesterbeginn Dauerausschreibung SHK-Vergütung'),
            ('', 'In der Arbeitsgruppe werden immer wieder Studentische Hilfskräfte gesucht.'),
            ('', 'Die Auswahl erfolgt auf Basis der zum Zeitpunkt des Bedarfs vorliegenden Bewerbungen.'),
            ('Bitte nutzen Sie unser Onlineverfahren.', 'Bewerbungsfrist: 25. August 2025'),
            ('mind. 2 Wochen', 'Bewerbung bitte an uns.'),
            ('', 'Bewerbung bitte an uns.'),
        ]
        for box, text in cases:
            first = detect(box, text)
            again = detect(first.value, text)
            self.assertEqual((first.kind, first.value, first.iso, first.days),
                             (again.kind, again.value, again.iso, again.days), (box, text))


if __name__ == '__main__':
    unittest.main()
