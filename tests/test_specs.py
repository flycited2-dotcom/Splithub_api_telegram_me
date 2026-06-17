import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_report_bot.specs import compact_spec, spec_lines_for, load_specs
from stock_report_bot.jac import map_rows
from stock_report_bot import menu


def _ac(article, category='Бытовые сплит-системы', price=18000.0, crimea='5',
        brand='MDV', series='X', holod='2.2'):
    return {
        'article': article, 'name': article, 'category': category, 'price': price,
        'brand': brand, 'series': series,
        'attributes': {'Крым': crimea, 'Холод, кВт': holod, 'РРЦ': '30 000 ₽'},
    }


class CompactSpecTests(unittest.TestCase):
    def test_compact_spec_full(self):
        ch = {'Холод, кВт': '7.1', 'Тип хладагента': 'R410A',
              'Тип управления компрессором': 'on-off'}
        s = compact_spec(ch)
        self.assertIn('❄ 7.1 кВт', s)
        self.assertIn('R410A', s)
        self.assertIn('on-off', s)

    def test_compact_spec_empty(self):
        self.assertEqual(compact_spec({}), '')

    def test_spec_lines_filters_empty_and_missing(self):
        specs = {
            'M1': {'characteristics': {'Холод, кВт': '2.5'}},
            'M2': {'characteristics': {}},          # пусто → не попадёт
        }
        out = spec_lines_for(specs, ['M1', 'M2', 'M3'])
        self.assertIn('M1', out)
        self.assertNotIn('M2', out)
        self.assertNotIn('M3', out)

    def test_load_specs_empty_path(self):
        self.assertEqual(load_specs(''), {})


class PricedMessageWithSpecsTests(unittest.TestCase):
    def test_spec_line_appended_under_model(self):
        rows = map_rows([_ac('MDSAG-09HRN8')])
        spec_lines = {'MDSAG-09HRN8': '❄ 2.6 кВт · R32 · on-off'}
        text = '\n'.join(
            menu.build_priced_message(rows, 'jac', 'MDV', 'X', 5, None, spec_lines))
        self.assertIn('MDSAG-09HRN8', text)
        self.assertIn('❄ 2.6 кВт · R32 · on-off', text)

    def test_no_specs_still_works(self):
        rows = map_rows([_ac('MDSAG-09HRN8')])
        text = '\n'.join(menu.build_priced_message(rows, 'jac', 'MDV', 'X', 5))
        self.assertIn('MDSAG-09HRN8', text)   # без ТТХ — просто нет подписи
