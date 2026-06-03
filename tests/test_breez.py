import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_report_bot.breez import _extract_base, _parse_leftovers


class BreezParseTests(unittest.TestCase):
    """Парсинг ответа Бриз `/leftoversnew/` — чистые функции, без сети."""

    def test_extract_base_from_price_list(self):
        price = [{'base': 30000.0, 'base_currency': 'RUB'},
                 {'ric': 41200.0, 'ric_currency': 'RUB'}]
        self.assertEqual(_extract_base(price), 30000.0)

    def test_extract_base_none_when_absent(self):
        self.assertIsNone(_extract_base([{'ric': 41200.0}]))   # есть только розница
        self.assertIsNone(_extract_base(None))

    def test_parse_format1_and_format2_equal(self):
        record = {'price': [{'base': 30000.0}, {'ric': 41200.0}]}
        format1 = {'НС-1': record}            # текущий живой формат
        format2 = [{'НС-1': record}]          # «может включить позже»
        expected = {'НС-1': 30000.0}
        self.assertEqual(_parse_leftovers(format1), expected)
        self.assertEqual(_parse_leftovers(format2), expected)

    def test_parse_flat_list(self):
        data = [{'nc': 'НС-2', 'price': [{'base': 15000.0}]}]
        self.assertEqual(_parse_leftovers(data), {'НС-2': 15000.0})

    def test_parse_skips_entries_without_base(self):
        data = {'НС-3': {'price': [{'ric': 41200.0}]}}   # нет base → позиция пропущена
        self.assertEqual(_parse_leftovers(data), {})


if __name__ == '__main__':
    unittest.main()
