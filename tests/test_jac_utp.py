import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_report_bot.jac_utp import (
    normalize_series, load_utp, utp_for, build_utp_block,
)

_SAMPLE = {
    "MDV": {"INTEGRA PRO": ["матовый корпус", "встроенный ИИ", "3D Air Flow"]},
    "THAICON": {"PHANTOM INVERTER": ["Full DC-Inverter", "4D Air Flow"]},
}


class NormalizeSeriesTests(unittest.TestCase):
    def test_upper_and_collapse_spaces(self):
        self.assertEqual(normalize_series('Integra  Pro '), 'INTEGRA PRO')

    def test_none_and_empty(self):
        self.assertEqual(normalize_series(None), '')
        self.assertEqual(normalize_series(''), '')


class LoadUtpTests(unittest.TestCase):
    def test_empty_path_returns_empty(self):
        self.assertEqual(load_utp(''), {})

    def test_missing_file_returns_empty(self):
        self.assertEqual(load_utp('/no/such/jac_utp_xyz.json'), {})

    def test_loads_valid_file(self):
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False,
                                         encoding='utf-8') as f:
            json.dump(_SAMPLE, f, ensure_ascii=False)
            path = f.name
        try:
            self.assertEqual(load_utp(path), _SAMPLE)
        finally:
            os.unlink(path)


class UtpForTests(unittest.TestCase):
    def test_hit(self):
        self.assertEqual(utp_for(_SAMPLE, 'MDV', 'INTEGRA PRO'),
                         ['матовый корпус', 'встроенный ИИ', '3D Air Flow'])

    def test_series_matched_case_insensitive_and_spaces(self):
        self.assertEqual(utp_for(_SAMPLE, 'MDV', 'integra   pro'),
                         ['матовый корпус', 'встроенный ИИ', '3D Air Flow'])

    def test_unknown_series_returns_empty(self):
        self.assertEqual(utp_for(_SAMPLE, 'MDV', 'NO SUCH'), [])

    def test_unknown_brand_returns_empty(self):
        self.assertEqual(utp_for(_SAMPLE, 'EUROKLIMAT', 'INTEGRA PRO'), [])


class BuildUtpBlockTests(unittest.TestCase):
    def test_block_has_head_and_quoted_items(self):
        block = build_utp_block('MDV', 'INTEGRA PRO', ['матовый корпус', '3D Air Flow'])
        self.assertIn('💡 MDV INTEGRA PRO — ключевые особенности:', block)
        self.assertIn('<blockquote>', block)
        self.assertIn('✓ матовый корпус', block)
        self.assertIn('✓ 3D Air Flow', block)
        self.assertTrue(block.endswith('</blockquote>'))

    def test_empty_list_returns_none(self):
        self.assertIsNone(build_utp_block('MDV', 'INTEGRA PRO', []))

    def test_html_escaped(self):
        block = build_utp_block('MDV', 'X & Y', ['a < b'])
        self.assertIn('X &amp; Y', block)
        self.assertIn('a &lt; b', block)
