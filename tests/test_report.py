import os
import sys
import unittest
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_report_bot.report import build_report_chunks, ITEM_DIVIDER, BRAND_DIVIDER


def _row(source, title, price, crimea, nc_code=None, brand=None):
    return {
        'source': source, 'title': title, 'price_wholesale': price,
        'crimea_qty': crimea, 'nc_code': nc_code, 'brand': brand,
    }


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            _row('rusklimat', 'AS-09HR4', Decimal('28500'), 3, brand='Hisense'),
            _row('rusklimat', 'AS-12HR4', Decimal('31000'), 2, brand='Hisense'),
            _row('rusklimat', 'NoPrice', None, 2, brand='Royal Clima'),
            _row('daichi', 'DA25', Decimal('33900'), 1, brand='Daichi'),
            _row('breeze', 'BSWI-09', Decimal('41200'), 5, brand='Ballu'),
            _row('breeze', 'NoCrimea', Decimal('15000'), 0, brand='Ballu'),  # нет Крыма → отфильтр.
        ]

    def test_supplier_headers_with_emoji_and_bold(self):
        text = '\n'.join(build_report_chunks(self.rows, today=date(2026, 6, 2)))
        self.assertIn('🟦 <b>РУСКЛИМАТ</b>', text)
        self.assertIn('🟥 <b>DAICHI</b>', text)
        self.assertIn('🟩 <b>БРИЗ</b>', text)

    def test_brand_bold_inline_and_crimea_qty(self):
        text = '\n'.join(build_report_chunks(self.rows, today=date(2026, 6, 2)))
        self.assertIn('• <b>Hisense</b> AS-09HR4 — 28 500 ₽ — 3 шт.', text)
        self.assertIn('• <b>Ballu</b> BSWI-09 — 41 200 ₽ — 5 шт.', text)
        self.assertIn('• <b>Royal Clima</b> NoPrice — — — 2 шт.', text)   # цена None → «—»

    def test_item_and_brand_dividers(self):
        # Русклимат: между двумя Hisense — тонкая полоска, между Hisense и
        # Royal Clima — двойная.
        text = '\n'.join(build_report_chunks(self.rows, today=date(2026, 6, 2)))
        self.assertIn(ITEM_DIVIDER, text)
        self.assertIn(BRAND_DIVIDER, text)

    def test_no_crimea_stock_excluded(self):
        text = '\n'.join(build_report_chunks(self.rows, today=date(2026, 6, 2)))
        self.assertNotIn('NoCrimea', text)

    def test_breez_base_for_breeze_and_rusklimat_with_fallback(self):
        # Бриз и Русклимат идут через фид Бриза (NC-namespace Бриза): опт (base)
        # берём из breez_base по nc_code, в БД у них розница. Откат на
        # price_wholesale, если NC не найден. Daichi — всегда из БД.
        rows = [
            _row('breeze', 'Inverter A', Decimal('41200'), 5, nc_code='НС-1', brand='Ballu'),   # есть в breez_base
            _row('breeze', 'Inverter B', Decimal('39000'), 2, nc_code='НС-2', brand='Ballu'),   # нет → откат на БД
            _row('rusklimat', 'Berg-07', Decimal('19888'), 3, nc_code='НС-3', brand='SHUFT'),   # есть → base (а не розница)
            _row('rusklimat', 'Berg-12', Decimal('28888'), 1, nc_code='НС-4', brand='SHUFT'),   # нет → откат на БД
            _row('daichi', 'DA25', Decimal('33900'), 1, nc_code='НС-1', brand='Daichi'),        # daichi игнорирует breez_base
        ]
        text = '\n'.join(build_report_chunks(
            rows, breez_base={'НС-1': 30000.0, 'НС-3': 13722.72}, today=date(2026, 6, 2)))
        self.assertIn('• <b>Ballu</b> Inverter A — 30 000 ₽ — 5 шт.', text)   # base из фида Бриза
        self.assertIn('• <b>Ballu</b> Inverter B — 39 000 ₽ — 2 шт.', text)   # откат на price_wholesale
        self.assertIn('• <b>SHUFT</b> Berg-07 — 13 723 ₽ — 3 шт.', text)      # Русклимат: base из фида Бриза
        self.assertIn('• <b>SHUFT</b> Berg-12 — 28 888 ₽ — 1 шт.', text)      # Русклимат без NC → откат на БД
        self.assertIn('• <b>Daichi</b> DA25 — 33 900 ₽ — 1 шт.', text)        # Daichi всегда из БД (НС-1 игнор)

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
