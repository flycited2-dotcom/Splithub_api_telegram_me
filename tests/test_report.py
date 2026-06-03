import os
import sys
import unittest
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_report_bot.report import build_report_chunks


def _row(source, title, price, crimea, nc_code=None, brand=None):
    return {
        'source': source, 'title': title, 'price_wholesale': price,
        'crimea_qty': crimea, 'nc_code': nc_code, 'brand': brand,
    }


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            _row('rusklimat', 'AS-09HR4', Decimal('28500'), 3, brand='Hisense'),
            _row('daichi', 'DA25', Decimal('33900'), 1, brand='Daichi'),
            _row('breeze', 'BSWI-09', Decimal('41200'), 5, brand='Ballu'),
            _row('breeze', 'NoCrimea', Decimal('15000'), 0, brand='Ballu'),  # нет Крыма → отфильтр.
            _row('rusklimat', 'NoPrice', None, 2, brand='Royal Clima'),
        ]

    def test_grouping_by_supplier(self):
        text = '\n'.join(build_report_chunks(self.rows, today=date(2026, 6, 2)))
        self.assertIn('<b>Русклимат</b>', text)
        self.assertIn('<b>Бриз</b>', text)
        self.assertIn('<b>Daichi</b>', text)

    def test_brand_prefixed_and_crimea_qty(self):
        text = '\n'.join(build_report_chunks(self.rows, today=date(2026, 6, 2)))
        self.assertIn('Hisense AS-09HR4 — 28 500 ₽ — 3 шт.', text)   # бренд впереди + крымский остаток
        self.assertIn('Ballu BSWI-09 — 41 200 ₽ — 5 шт.', text)
        self.assertIn('Royal Clima NoPrice — — — 2 шт.', text)        # цена None → «—»

    def test_no_crimea_stock_excluded(self):
        text = '\n'.join(build_report_chunks(self.rows, today=date(2026, 6, 2)))
        self.assertNotIn('NoCrimea', text)   # остаток в Крыму 0 → не показываем

    def test_breeze_price_from_breez_base_with_fallback(self):
        rows = [
            _row('breeze', 'Inverter A', Decimal('41200'), 5, nc_code='НС-1', brand='Ballu'),  # есть в breez_base
            _row('breeze', 'Inverter B', Decimal('39000'), 2, nc_code='НС-2', brand='Ballu'),  # нет → откат на БД
            _row('rusklimat', 'Model X', Decimal('28500'), 3, nc_code='НС-1', brand='Hisense'),  # не Бриз → из БД
        ]
        text = '\n'.join(build_report_chunks(
            rows, breez_base={'НС-1': 30000.0}, today=date(2026, 6, 2)))
        self.assertIn('Ballu Inverter A — 30 000 ₽ — 5 шт.', text)   # base из Бриз API, не 41 200
        self.assertIn('Ballu Inverter B — 39 000 ₽ — 2 шт.', text)   # откат на price_wholesale
        self.assertIn('Hisense Model X — 28 500 ₽ — 3 шт.', text)    # rusklimat игнорирует breez_base

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
