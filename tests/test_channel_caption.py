"""Тесты подписи-прайса для канала (channel_caption.py). Чистые функции — без БД/сети."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_report_bot import channel_caption as cc
from stock_report_bot.menu import marked_price
from stock_report_bot.report import _fmt_price


class SizeFromBtuTests(unittest.TestCase):
    def test_btu_scale(self):
        self.assertEqual(cc.size_from_btu(7000), 7)
        self.assertEqual(cc.size_from_btu(9000), 9)
        self.assertEqual(cc.size_from_btu(12000), 12)
        self.assertEqual(cc.size_from_btu(24000), 24)

    def test_already_in_thousands(self):
        self.assertEqual(cc.size_from_btu(9), 9)
        self.assertEqual(cc.size_from_btu(18), 18)

    def test_near_value_snaps(self):
        self.assertEqual(cc.size_from_btu(9200), 9)

    def test_invalid_values(self):
        for v in (None, 0, -5, 'abc', ''):
            self.assertIsNone(cc.size_from_btu(v), v)


def _pos(btu, price, title='Model', source='daichi'):
    return {'source': source, 'nc_code': None, 'btu_calc': btu,
            'price_wholesale': price, 'price_base': None, 'title': title}


class BuildCaptionTests(unittest.TestCase):
    def test_header_and_markup_and_order(self):
        positions = [_pos(18000, 60000), _pos(7000, 30000), _pos(9000, 40000)]
        cap = cc.build_channel_caption(positions, 10, 'Daichi', 'Bravo', 'daichi')
        self.assertTrue(cap.startswith('<blockquote>') and cap.endswith('</blockquote>'))
        self.assertIn('❄️ Daichi', cap)
        self.assertIn('Bravo', cap)
        # наценка применена и цены отсортированы по типоразмеру (7 → 9 → 18)
        p7 = _fmt_price(marked_price(30000, 10))
        p9 = _fmt_price(marked_price(40000, 10))
        p18 = _fmt_price(marked_price(60000, 10))
        self.assertIn(p7, cap)
        self.assertLess(cap.index(p7), cap.index(p9))
        self.assertLess(cap.index(p9), cap.index(p18))
        self.assertNotEqual(p7, '30 000 ₽')   # цена с наценкой, не опт

    def test_inverter_header_toggle(self):
        on = cc.build_channel_caption([_pos(9000, 40000)], 5, 'X', 'Y', 'daichi', inverter=True)
        off = cc.build_channel_caption([_pos(9000, 40000)], 5, 'X', 'Y', 'daichi', inverter=False)
        self.assertIn('инвертор', on)
        self.assertNotIn('инвертор', off)

    def test_unknown_btu_falls_back_to_model_name(self):
        positions = [_pos(None, 50000, title='Daichi SuperModel ABC'), _pos(9000, 40000)]
        cap = cc.build_channel_caption(positions, 5, 'Daichi', 'Bravo', 'daichi')
        self.assertIn('SuperModel ABC', cap)            # запасное имя (бренд срезан)
        # известный размер идёт раньше позиции без размера
        self.assertLess(cap.index(_fmt_price(marked_price(40000, 5))),
                        cap.index('SuperModel'))

    def test_position_without_price_skipped(self):
        cap = cc.build_channel_caption([_pos(9000, None)], 5, 'X', 'Y', 'daichi')
        self.assertIn('❄️ X', cap)                      # заголовок есть
        self.assertNotIn('₽', cap)                      # ценовых строк нет


if __name__ == '__main__':
    unittest.main()
