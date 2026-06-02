import os
import sys
import unittest
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_report_bot.report import build_report_chunks


def _row(source, title, price, crimea, total):
    return {
        'source': source, 'title': title, 'price_wholesale': price,
        'crimea_qty': crimea, 'total_qty': total,
    }


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            _row('rusklimat', 'Hisense AS-09HR4', Decimal('28500'), 3, 53),   # крымское 3 (не 53)
            _row('daichi', 'Daichi DA25', Decimal('33900'), 1, 1),
            _row('breeze', 'Ballu BSWI-09', Decimal('41200'), 5, 5),
            _row('breeze', 'Breez Mainland', Decimal('15000'), 0, 30),         # материковый Бриз
            _row('rusklimat', 'NoPrice', None, 2, 2),
        ]

    def test_grouping_and_breeze_mainland_included(self):
        text = '\n'.join(build_report_chunks(self.rows, today=date(2026, 6, 2)))
        self.assertIn('<b>Русклимат</b>', text)
        self.assertIn('<b>Бриз</b>', text)
        self.assertIn('<b>Daichi</b>', text)
        self.assertIn('Breez Mainland', text)

    def test_quantity_crimea_for_others_total_for_breeze(self):
        text = '\n'.join(build_report_chunks(self.rows, today=date(2026, 6, 2)))
        self.assertIn('Hisense AS-09HR4 — 28 500 ₽ — 3 шт.', text)   # РусКлимат — крымское
        self.assertIn('Breez Mainland — 15 000 ₽ — 30 шт.', text)     # Бриз — сумма складов
        self.assertIn('NoPrice — — — 2 шт.', text)                    # цена None → «—»

    def test_chunking_respects_max_len(self):
        chunks = build_report_chunks(self.rows, max_len=120)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 120)

    def test_empty(self):
        chunks = build_report_chunks([])
        self.assertEqual(len(chunks), 1)
        self.assertIn('Остатков в наличии нет', chunks[0])


if __name__ == '__main__':
    unittest.main()
