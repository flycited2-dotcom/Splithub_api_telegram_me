import os
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_report_bot import menu


def _row(source, title, price, crimea, brand=None, series=None, nc_code=None,
         price_base=None, image_url=None):
    return {
        'source': source, 'title': title, 'price_wholesale': price,
        'price_base': price_base, 'crimea_qty': crimea, 'nc_code': nc_code,
        'brand': brand, 'series': series, 'image_url': image_url,
    }


class SeriesOfTests(unittest.TestCase):
    def test_uses_series_field_when_present(self):
        r = _row('breeze', 'Ballu BSWI-09', Decimal('1'), 1, brand='Ballu', series='Olympio')
        self.assertEqual(menu.series_of(r), 'Olympio')

    def test_rusklimat_parsed_from_title(self):
        cases = [
            ('Сплит-система Ballu Olympio Edge BSO-07HN8_22Y комплект', 'Ballu', 'Olympio Edge'),
            ('Сплит-система SHUFT Berg SFTO-07HN1_24Y комплект', 'SHUFT', 'Berg'),
            ('Кондиционер мобильный Ballu Aura BPAC-07 CP/N1_24Y', 'Ballu', 'Aura'),
            ('Сплит-система Royal Thermo Barocco RTB-09HN8_V2 комплект', 'Royal Thermo', 'Barocco'),
        ]
        for title, brand, expected in cases:
            r = _row('rusklimat', title, Decimal('1'), 1, brand=brand, series='')
            self.assertEqual(menu.series_of(r), expected, title)

    def test_rusklimat_no_series_word(self):
        r = _row('rusklimat', 'Сплит-система инверторного типа AC ELECTRIC ACEMI-07HN8 комплект',
                 Decimal('1'), 1, brand='AC ELECTRIC', series='')
        self.assertEqual(menu.series_of(r), menu.EMPTY_SERIES)


class MarkedPriceTests(unittest.TestCase):
    def test_rounds_up_to_90(self):
        self.assertEqual(menu.marked_price(26404, 5), 27790)     # 27 724.2 → 27 790
        self.assertEqual(menu.marked_price(Decimal('26404'), 5), 27790)
        self.assertEqual(menu.marked_price(10000, 10), 11090)    # 11 000 → 11 090
        self.assertEqual(menu.marked_price(9991, 1), 10190)      # 10 090.91 > …090 → …190

    def test_negative_markup_discount(self):
        # −5% от опта 26 404 = 25 083.8 → округл. вверх до …90 = 25 090
        self.assertEqual(menu.marked_price(26404, -5), 25090)

    def test_none(self):
        self.assertIsNone(menu.marked_price(None, 5))


class HierarchyTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            _row('daichi', 'Kentatsu Kanami KSGAA35', Decimal('1'), 3, brand='Kentatsu', series='Kanami'),
            _row('daichi', 'Kentatsu Kanami KSGAA09', Decimal('1'), 2, brand='Kentatsu', series='Kanami'),
            _row('daichi', 'Kentatsu Aska KSGA12', Decimal('1'), 1, brand='Kentatsu', series='Aska'),
            _row('breeze', 'Ballu BSWI-09', Decimal('1'), 5, brand='Ballu', series='Olympio'),
            _row('breeze', 'NoCrimea', Decimal('1'), 0, brand='Ballu', series='Olympio'),  # отфильтр.
            _row('rusklimat', 'Сплит-система SHUFT Berg SFTO-07HN1 комплект', Decimal('1'), 1,
                 brand='SHUFT', series=''),
        ]

    def test_suppliers_present_in_order(self):
        self.assertEqual(menu.suppliers_present(self.rows), ['breeze', 'rusklimat', 'daichi'])

    def test_brands_and_series(self):
        self.assertEqual(menu.brands_for(self.rows, 'daichi'), ['Kentatsu'])
        self.assertEqual(menu.series_for(self.rows, 'daichi', 'Kentatsu'), ['Aska', 'Kanami'])
        self.assertEqual(menu.series_for(self.rows, 'rusklimat', 'SHUFT'), ['Berg'])

    def test_positions_excludes_no_crimea(self):
        pos = menu.positions_for(self.rows, 'breeze', 'Ballu', 'Olympio')
        self.assertEqual(len(pos), 1)
        self.assertEqual(pos[0]['title'], 'Ballu BSWI-09')

    def test_series_image_first_nonempty(self):
        rows = [
            _row('daichi', 'Kentatsu A', Decimal('1'), 1, brand='Kentatsu', series='Kanami', image_url=None),
            _row('daichi', 'Kentatsu B', Decimal('1'), 1, brand='Kentatsu', series='Kanami',
                 image_url='https://x/img.jpg'),
        ]
        self.assertEqual(menu.series_image(rows, 'daichi', 'Kentatsu', 'Kanami'), 'https://x/img.jpg')
        self.assertIsNone(menu.series_image(rows, 'daichi', 'Kentatsu', 'Нет'))


class CallbackTests(unittest.TestCase):
    def test_pack_unpack(self):
        self.assertEqual(menu.cb_pack('g', 'b', 1, 2, 5), 'g|b|1|2|5')
        self.assertEqual(menu.cb_unpack('g|b|1|2|5'), ['g', 'b', '1', '2', '5'])

    def test_callback_data_short(self):
        self.assertLess(len(menu.cb_pack('g', 'r', 99, 99, 10).encode()), 64)


class KeyboardTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            _row('daichi', 'Kentatsu Kanami KSGAA35', Decimal('1'), 3, brand='Kentatsu', series='Kanami'),
            _row('breeze', 'Ballu BSWI-09', Decimal('1'), 5, brand='Ballu', series='Olympio'),
        ]

    def test_kb_suppliers(self):
        kb = menu.kb_suppliers(self.rows)
        datas = [b['callback_data'] for row in kb['inline_keyboard'] for b in row]
        self.assertIn('b|b|0', datas)   # breeze
        self.assertIn('b|d|0', datas)   # daichi

    def test_kb_brands_has_back(self):
        kb = menu.kb_brands(self.rows, 'daichi')
        flat = [b for row in kb['inline_keyboard'] for b in row]
        self.assertTrue(any(b['callback_data'] == 's|d|0|0' for b in flat))  # бренд[0]→серии
        self.assertTrue(any(b['callback_data'] == 'm' for b in flat))        # назад в корень

    def test_kb_markup_buttons(self):
        kb = menu.kb_markup('daichi', 0, 0)
        datas = [b['callback_data'] for row in kb['inline_keyboard'] for b in row
                 if b['callback_data'].startswith('g|')]
        self.assertEqual(len(datas), 14)        # 4 скидки + 10 наценок
        self.assertIn('g|d|0|0|5', datas)       # +5%
        self.assertIn('g|d|0|0|-5', datas)      # −5% (скидка от опта)
        self.assertIn('g|d|0|0|-1', datas)

    def test_pagination(self):
        rows = [_row('breeze', f'Br{i} M', Decimal('1'), 1, brand=f'Br{i:02d}', series='S')
                for i in range(20)]
        kb = menu.kb_brands(rows, 'breeze', page=0)
        # 8 пунктов + ряд навигации + назад
        item_btns = [b for row in kb['inline_keyboard'] for b in row
                     if b['callback_data'].startswith('s|')]
        self.assertEqual(len(item_btns), menu.PAGE_SIZE)
        nav = [b['callback_data'] for row in kb['inline_keyboard'] for b in row]
        self.assertTrue(any(d.startswith('b|b|1') for d in nav))  # ▶ на стр.1


class BuildMessageTests(unittest.TestCase):
    def test_priced_line(self):
        rows = [_row('daichi', 'Kentatsu Kanami KSGAA35', Decimal('26404'), 12,
                     brand='Kentatsu', series='Kanami')]
        text = '\n'.join(menu.build_priced_message(rows, 'daichi', 'Kentatsu', 'Kanami', 5))
        self.assertTrue(text.startswith('🏷 🟥'))    # шапка — только эмодзи
        self.assertNotIn('наценка', text)            # наценку клиенту не раскрываем
        self.assertNotIn('Daichi', text)             # поставщика не раскрываем
        self.assertIn('• <b>Kentatsu</b> Kentatsu Kanami KSGAA35 — 27 790 ₽ — 12 шт.', text)

    def test_negative_priced_line(self):
        rows = [_row('daichi', 'Kentatsu Kanami KSGAA35', Decimal('26404'), 12,
                     brand='Kentatsu', series='Kanami')]
        text = '\n'.join(menu.build_priced_message(rows, 'daichi', 'Kentatsu', 'Kanami', -5))
        self.assertIn('— 25 090 ₽ — 12 шт.', text)   # −5% от опта

    def test_extra_block_glued_one_message(self):
        rows = [_row('daichi', 'Kentatsu Kanami KSGAA35', Decimal('26404'), 12,
                     brand='Kentatsu', series='Kanami')]
        block = '💡 Kentatsu Kanami — ключевые особенности:\n<blockquote>❄️ Инверторная технология</blockquote>'
        chunks = menu.build_priced_message(rows, 'daichi', 'Kentatsu', 'Kanami', 5, extra_block=block)
        text = '\n'.join(chunks)
        self.assertEqual(len(chunks), 1)                 # список + характеристики одним сообщением
        self.assertIn('27 790 ₽', text)                  # список
        self.assertIn('<blockquote>❄️ Инверторная технология</blockquote>', text)  # цитата не разорвана


class SpecsChoiceTests(unittest.TestCase):
    def test_two_buttons_and_back(self):
        kb = menu.kb_specs_choice('breeze', 1, 2, 5)
        datas = [b['callback_data'] for row in kb['inline_keyboard'] for b in row]
        self.assertIn('gs|b|1|2|5', datas)   # с характеристиками
        self.assertIn('gp|b|1|2|5', datas)   # без характеристик
        self.assertIn('k|b|1|2', datas)      # ⬅ назад к выбору наценки


class ReplyKeyboardTests(unittest.TestCase):
    def test_main_reply_kb_persistent_menu_button(self):
        kb = menu.MAIN_REPLY_KB
        self.assertTrue(kb.get('is_persistent'))
        self.assertTrue(kb.get('resize_keyboard'))
        texts = [b['text'] for row in kb['keyboard'] for b in row]
        self.assertIn(menu.MENU_BUTTON_TEXT, texts)


class ShortSeriesTests(unittest.TestCase):
    def test_strips_breez_prefix(self):
        self.assertEqual(
            menu.short_series('Инверторные сплит-системы серии CYCLONE DC Inverter'),
            'CYCLONE DC Inverter')
        self.assertEqual(menu.short_series('Классические сплит-системы серии PROGRESS'), 'PROGRESS')
        self.assertEqual(
            menu.short_series('Классические сплит-системы кассетного типа серии KADET'), 'KADET')

    def test_keeps_names_without_prefix(self):
        self.assertEqual(menu.short_series('AKOYA Inverter'), 'AKOYA Inverter')
        self.assertEqual(menu.short_series('Breezeless E'), 'Breezeless E')
        self.assertEqual(menu.short_series('Olympio Edge'), 'Olympio Edge')

    def test_kb_series_uses_short_label(self):
        full = 'Инверторные сплит-системы серии CYCLONE DC Inverter'
        rows = [_row('breeze', 'X model', Decimal('1'), 1, brand='ZILON', series=full)]
        texts = [b['text'] for row in menu.kb_series(rows, 'breeze', 0)['inline_keyboard'] for b in row]
        self.assertIn('CYCLONE DC Inverter', texts)
        self.assertNotIn(full, texts)


if __name__ == '__main__':
    unittest.main()
