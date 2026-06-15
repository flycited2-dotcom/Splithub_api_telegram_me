"""Тесты подписи-прайса для канала (channel_caption.py). Чистые функции — без БД/сети.

ВАЖНО: `btu_calc` сайта — это УЖЕ номинал в kBTU (7/9/10/12/13/14/16/18/20/22/24/…/60),
а не полные BTU (9000). Размер берём как есть, без повторного снапа к урезанному набору
(старый баг 10→9, 14→12 давал «поплывшие»/дублирующиеся размеры)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_report_bot import channel_caption as cc
from stock_report_bot.menu import marked_price
from stock_report_bot.report import _fmt_price


class SizeFromBtuTests(unittest.TestCase):
    def test_nominal_taken_as_is(self):
        # btu_calc уже номинал — возвращаем как есть (никакого снапа к 7/9/12/18/24).
        for n in (7, 9, 10, 12, 13, 14, 16, 18, 20, 22, 24, 25, 26, 27, 30, 36, 48, 60):
            self.assertEqual(cc.size_from_btu(n), n, n)

    def test_legacy_full_btu_divided(self):
        # Подстраховка: если прилетит в полных BTU — делим на 1000.
        self.assertEqual(cc.size_from_btu(9000), 9)
        self.assertEqual(cc.size_from_btu(12000), 12)

    def test_invalid_values(self):
        for v in (None, 0, -5, 'abc', ''):
            self.assertIsNone(cc.size_from_btu(v), v)


def _pos(btu, price, title='Model', source='daichi'):
    return {'source': source, 'nc_code': None, 'btu_calc': btu,
            'price_wholesale': price, 'price_base': None, 'title': title}


class BuildCaptionTests(unittest.TestCase):
    def test_header_and_markup_and_order(self):
        positions = [_pos(18, 60000), _pos(7, 30000), _pos(9, 40000)]
        cap = cc.build_channel_caption(positions, 10, 'Daichi', 'Bravo', 'daichi')
        self.assertTrue(cap.startswith('<blockquote>') and cap.endswith('</blockquote>'))
        self.assertIn('❄️ Daichi', cap)
        self.assertIn('Bravo', cap)
        p7 = _fmt_price(marked_price(30000, 10))
        p9 = _fmt_price(marked_price(40000, 10))
        p18 = _fmt_price(marked_price(60000, 10))
        self.assertIn(p7, cap)
        self.assertLess(cap.index(p7), cap.index(p9))   # сортировка по размеру 7→9→18
        self.assertLess(cap.index(p9), cap.index(p18))
        self.assertNotEqual(p7, '30 000 ₽')             # цена с наценкой, не опт

    def test_non_standard_sizes_not_mangled(self):
        # Размеры 10/14/20 раньше склеивались в 9/12/18 — теперь показываются точно.
        positions = [_pos(10, 40000), _pos(14, 50000), _pos(20, 70000)]
        cap = cc.build_channel_caption(positions, 5, 'Ballu', 'Olympio', 'daichi')
        body = cap.split('──')[-1]
        self.assertIn('10', body)
        self.assertIn('14', body)
        self.assertIn('20', body)
        self.assertNotIn('9 —', body)                   # 10 НЕ превратилось в 9
        self.assertNotIn('12 —', body)                  # 14 НЕ превратилось в 12

    def test_dedup_same_size_min_price(self):
        # Два товара одного размера → одна строка с минимальной ценой (не «9, 9»).
        positions = [_pos(9, 50000), _pos(9, 40000)]
        cap = cc.build_channel_caption(positions, 0, 'X', 'Y', 'daichi')
        self.assertEqual(cap.count('9 —'), 1)
        self.assertIn(_fmt_price(marked_price(40000, 0)), cap)   # минимальная
        self.assertNotIn(_fmt_price(marked_price(50000, 0)), cap)

    def test_inverter_header_toggle(self):
        on = cc.build_channel_caption([_pos(9, 40000)], 5, 'X', 'Y', 'daichi', inverter=True)
        off = cc.build_channel_caption([_pos(9, 40000)], 5, 'X', 'Y', 'daichi', inverter=False)
        self.assertIn('инвертор', on)
        self.assertNotIn('инвертор', off)

    def test_unknown_btu_falls_back_to_model_name(self):
        positions = [_pos(None, 50000, title='Daichi SuperModel ABC'), _pos(9, 40000)]
        cap = cc.build_channel_caption(positions, 5, 'Daichi', 'Bravo', 'daichi')
        self.assertIn('SuperModel ABC', cap)            # запасное имя (бренд срезан)
        self.assertLess(cap.index(_fmt_price(marked_price(40000, 5))),
                        cap.index('SuperModel'))          # размер раньше «без размера»

    def test_position_without_price_skipped(self):
        cap = cc.build_channel_caption([_pos(9, None)], 5, 'X', 'Y', 'daichi')
        self.assertIn('❄️ X', cap)
        self.assertNotIn('₽', cap)


if __name__ == '__main__':
    unittest.main()
