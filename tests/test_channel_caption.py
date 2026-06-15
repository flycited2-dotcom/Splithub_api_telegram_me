"""Тесты подписи-прайса для канала (channel_caption.py). Чистые функции — без БД/сети.

`btu_calc` сайта — уже номинал kBTU (7/9/10/12/…/60), берём как есть (без снапа).
Но у части серий btu_calc неверен (несколько разных моделей с одним размером — напр.
Ballu Olympio Legend: 3 модели 7/9/12, все помечены 7). При такой «коллизии» не
схлопываем в одну строку: размеры берём из артикула, иначе показываем по коду модели."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_report_bot import channel_caption as cc
from stock_report_bot.menu import marked_price
from stock_report_bot.report import _fmt_price


class SizeFromBtuTests(unittest.TestCase):
    def test_nominal_taken_as_is(self):
        # реальные kBTU-размеры (не площади) — как есть
        for n in (7, 9, 10, 12, 13, 14, 16, 18, 20, 22, 24, 26, 27, 36, 48):
            self.assertEqual(cc.size_from_btu(n), n, n)

    def test_area_codes_mapped_to_size(self):
        # числа-площади (м²) → типоразмер (kBTU), карта владельца (бытовые)
        for area, size in ((25, 7), (30, 9), (35, 12), (50, 18), (60, 24), (70, 24)):
            self.assertEqual(cc.size_from_btu(area, category_id=2), size, area)

    def test_semi_industrial_keeps_real_btu(self):
        # полупром (кат. 6): 60 = реальные 60 000 BTU, площадей не применяем
        self.assertEqual(cc.size_from_btu(60, category_id=6), 60)
        self.assertEqual(cc.size_from_btu(36, category_id=6), 36)
        self.assertEqual(cc.size_from_btu(48, category_id=6), 48)
        # бытовые: то же число 60 трактуем как площадь → 24
        self.assertEqual(cc.size_from_btu(60, category_id=2), 24)

    def test_legacy_full_btu_divided(self):
        self.assertEqual(cc.size_from_btu(9000), 9)
        self.assertEqual(cc.size_from_btu(12000), 12)

    def test_invalid_values(self):
        for v in (None, 0, -5, 'abc', ''):
            self.assertIsNone(cc.size_from_btu(v), v)


def _pos(btu, price, title='Model', source='daichi', category_id=2):
    return {'source': source, 'nc_code': None, 'btu_calc': btu, 'category_id': category_id,
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
        self.assertLess(cap.index(p7), cap.index(p9))   # сортировка по размеру 7→9→18
        self.assertLess(cap.index(p9), cap.index(p18))
        self.assertNotEqual(p7, '30 000 ₽')             # цена с наценкой, не опт

    def test_non_standard_sizes_not_mangled(self):
        # Размеры 10/14/20 раньше склеивались в 9/12/18 — теперь показываются точно.
        positions = [_pos(10, 40000), _pos(14, 50000), _pos(20, 70000)]
        cap = cc.build_channel_caption(positions, 5, 'Ballu', 'Olympio', 'daichi')
        body = cap.split('──')[-1]
        for n in ('10', '14', '20'):
            self.assertIn(n, body)
        self.assertNotIn('9 —', body)                   # 10 НЕ превратилось в 9

    def test_collision_recovers_sizes_from_article(self):
        # Ballu Olympio Legend: btu_calc у всех = 7 (баг сайта), но артикулы 07/09/12.
        positions = [
            _pos(7, 15890, title='Ballu Olympio Legend BSO-07HN8'),
            _pos(7, 16990, title='Ballu Olympio Legend BSO-09HN8'),
            _pos(7, 23290, title='Ballu Olympio Legend BSO-12HN8'),
        ]
        cap = cc.build_channel_caption(positions, 0, 'Ballu', 'Olympio Legend', 'daichi')
        # все три позиции на месте (не схлопнулись в одну) и в порядке 7→9→12
        self.assertIn('15 890 ₽', cap)
        self.assertIn('16 990 ₽', cap)
        self.assertIn('23 290 ₽', cap)
        self.assertLess(cap.index('15 890'), cap.index('16 990'))
        self.assertLess(cap.index('16 990'), cap.index('23 290'))

    def test_collision_without_codes_lists_by_model(self):
        # Коллизия размеров, в артикуле кода нет → показываем все по коду модели.
        positions = [_pos(9, 40000, title='X AlphaUnit'), _pos(9, 50000, title='X BetaUnit')]
        cap = cc.build_channel_caption(positions, 0, 'X', 'Y', 'daichi')
        self.assertIn('AlphaUnit', cap)
        self.assertIn('BetaUnit', cap)
        self.assertIn(_fmt_price(marked_price(40000, 0)), cap)
        self.assertIn(_fmt_price(marked_price(50000, 0)), cap)   # обе показаны, не схлопнуты

    def test_semi_industrial_series_keeps_sizes(self):
        # Полупром (кат. 6): 36/48/60 — реальные размеры, не превращаются в площади.
        positions = [_pos(36, 80000, category_id=6), _pos(48, 95000, category_id=6),
                     _pos(60, 120000, category_id=6)]
        cap = cc.build_channel_caption(positions, 0, 'Daichi', 'DA-DT', 'daichi')
        body = cap.split('──')[-1]
        for n in ('36', '48', '60'):
            self.assertIn(n, body)
        self.assertNotIn('24 —', body)        # 60 НЕ стало 24 (это полупром)

    def test_inverter_header_toggle(self):
        on = cc.build_channel_caption([_pos(9, 40000)], 5, 'X', 'Y', 'daichi', inverter=True)
        off = cc.build_channel_caption([_pos(9, 40000)], 5, 'X', 'Y', 'daichi', inverter=False)
        self.assertIn('инвертор', on)
        self.assertNotIn('инвертор', off)

    def test_unknown_btu_falls_back_to_model_name(self):
        positions = [_pos(None, 50000, title='Daichi SuperModel ABC'), _pos(9, 40000)]
        cap = cc.build_channel_caption(positions, 5, 'Daichi', 'Bravo', 'daichi')
        self.assertIn('SuperModel ABC', cap)
        self.assertLess(cap.index(_fmt_price(marked_price(40000, 5))),
                        cap.index('SuperModel'))          # размер раньше «без размера»

    def test_position_without_price_skipped(self):
        cap = cc.build_channel_caption([_pos(9, None)], 5, 'X', 'Y', 'daichi')
        self.assertIn('❄️ X', cap)
        self.assertNotIn('₽', cap)


if __name__ == '__main__':
    unittest.main()
