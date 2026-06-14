"""Тесты блока характеристик (specs.py). Чистые функции — без БД и сети.

Значения в кейсах взяты из реального дампа БД сайта (catalog_producttech),
чтобы отбор/нормализация были устойчивы к «сырым» данным поставщиков.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_report_bot import specs


def _tr(title, value):
    return {'title': title, 'value': value}


class NormalizeTests(unittest.TestCase):
    def test_affirmative(self):
        for v in ('да', 'Да', 'ДА', 'Y', '1', 'есть', 'Wi-Fi Ready', 'Доп.опция', 'Встроенный'):
            self.assertTrue(specs._affirm(v), v)
        for v in ('нет', 'Нет', 'No', 'N', '0', '-', '—', '', 'отсутствует'):
            self.assertFalse(specs._affirm(v), v)

    def test_min_number(self):
        self.assertEqual(specs._min_num('-15 ~ +24'), '-15')
        self.assertEqual(specs._min_num('-15~18'), '-15')
        self.assertEqual(specs._min_num('18,5/25/29/32'), '18.5')
        self.assertEqual(specs._min_num('34/30/22'), '22')
        self.assertIsNone(specs._min_num('—'))

    def test_energy_class(self):
        self.assertEqual(specs._class('A+++'), 'A+++')
        self.assertEqual(specs._class('8,50 / A+++'), 'A+++')
        self.assertEqual(specs._class('3,61    A'), 'A')
        self.assertIsNone(specs._class('8,50'))

    def test_clean_utp(self):
        raw = '&#9679; Стильный дизайн;<br>\r\n&#9679; Турбо-режим;<br>'
        self.assertEqual(specs._clean_utp(raw), ['Стильный дизайн', 'Турбо-режим'])
        self.assertEqual(specs._clean_utp('Wi-Fi модуль;Авторестарт'),
                         ['Wi-Fi модуль', 'Авторестарт'])
        # Реальный формат Бриз API — ДВОЙНОЙ HTML-эскейп (&amp;#9679;, &lt;br&gt;).
        real = '&amp;#9679; Современный дизайн&lt;br&gt;\n&amp;#9679; Пульт на корпусе&lt;br&gt;'
        self.assertEqual(specs._clean_utp(real), ['Современный дизайн', 'Пульт на корпусе'])


class BuildBreezeTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            _tr('Класс энергоэффективности EER (охлаждение)', 'A+++'),
            _tr('Инверторная технология', 'да'),
            _tr('Марка компрессора', 'GMCC'),
            _tr('Рабочие температурные границы наружного воздуха (нагрев)', '-15 ~ +24'),
            _tr('Минимальный уровень шума внутреннего блока', '19'),
            _tr('Срок гарантии', '36'),
            _tr('Управление c мобильного приложения по Wi-Fi', 'да'),
            _tr('Ионизатор воздуха', 'да'),
            _tr('Плазменная очистка воздуха', 'да'),
            _tr('Ультрафиолетовое обеззараживание', 'Нет'),     # пропустить
        ]

    def test_lines_and_order(self):
        text = '\n'.join(specs.build_specs_message(self.rows, 'Hisense', 'AKOYA', 'breeze'))
        self.assertIn('💡 Hisense AKOYA', text)
        self.assertIn('<blockquote>', text)
        for needle in ('Класс энергоэффективности A+++', 'Инверторная технология',
                       'Компрессор GMCC', 'Работа на обогрев до −15 °C',
                       'Уровень шума от 19 дБ', 'Гарантия 36 мес',
                       'Wi-Fi управление', 'Ионизация воздуха', 'Плазменная очистка'):
            self.assertIn(needle, text)
        self.assertNotIn('УФ-обеззараживание', text)           # значение «Нет» → пропуск
        # порядок: класс → инвертор → компрессор → обогрев → шум → гарантия → Wi-Fi
        self.assertLess(text.index('A+++'), text.index('Компрессор'))
        self.assertLess(text.index('Компрессор'), text.index('обогрев'))
        self.assertLess(text.index('Гарантия'), text.index('Wi-Fi'))

    def test_no_supplier_leak(self):
        text = '\n'.join(specs.build_specs_message(self.rows, 'Hisense', 'AKOYA', 'breeze'))
        self.assertNotIn('Бриз', text)
        self.assertNotIn('breeze', text)


class BuildRusklimatTests(unittest.TestCase):
    def test_voice_and_utp_extras(self):
        rows = [
            _tr('ЭНЕРГОЭФФЕКТИВНОСТЬ', 'A++'),
            _tr('Инверторная технология', 'Да'),
            _tr('Мин. рабочая температура воздуха для внешнего блока', '-15'),
            _tr('Уровень шума внутр. блока', '19'),
            _tr('Гарантийный срок', '3 года'),
            _tr('Управление c мобильного приложения по Wi-Fi', 'Да'),
            _tr('Работает с Алисой', 'Да'),
            _tr('Функция ионизации воздуха', 'Да'),
            _tr('Режим автоочистки', 'Да'),
            _tr('Режим SLEEP', 'Да'),
            _tr('Авторестарт при отключении питания', 'Да'),
            _tr('УТП', 'Wi-Fi модуль;Стильный дизайн;Турбо-режим;Авторестарт;Защита Gold Fin'),
        ]
        text = '\n'.join(specs.build_specs_message(rows, 'Ballu', 'Platinum', 'rusklimat'))
        self.assertIn('Класс энергоэффективности A++', text)
        self.assertIn('Работа на обогрев до −15 °C', text)
        self.assertIn('Гарантия 3 года', text)
        self.assertIn('Управление голосом (Алиса)', text)
        self.assertIn('Самоочистка', text)
        self.assertIn('Ночной режим', text)
        self.assertIn('Авторестарт после отключения', text)
        # УТП-экстра: дубли (Wi-Fi, Авторестарт) выкинуты, новое — оставлено
        self.assertIn('Стильный дизайн', text)
        self.assertIn('Турбо-режим', text)
        self.assertIn('Защита Gold Fin', text)
        self.assertEqual(text.count('Авторестарт'), 1)   # не задвоено из УТП


class BuildDaichiTests(unittest.TestCase):
    def test_full_dc_inverter_and_noise_min(self):
        rows = [
            _tr('Технология работы', 'Full DC Inverter'),
            _tr('Класс энергоэффективности, охлаждение', 'A'),
            _tr('Диапазон рабочих температур, нагрев, °C', '-15~18'),
            _tr('Облачные кондиционеры', 'Y'),
            _tr('Уровень звукового давления, ВБ, охлаждение, дБ(А)', '34/30/22'),
        ]
        text = '\n'.join(specs.build_specs_message(rows, 'Kentatsu', 'Bravo', 'daichi'))
        self.assertIn('Класс энергоэффективности A', text)
        self.assertIn('Инверторная технология', text)
        self.assertIn('до −15 °C', text)
        self.assertIn('Wi-Fi управление', text)
        self.assertIn('от 22 дБ', text)

    def test_onoff_not_shown_as_inverter(self):
        rows = [_tr('Технология работы', 'On/Off')]
        text = '\n'.join(specs.build_specs_message(rows, 'X', 'Y', 'daichi'))
        self.assertNotIn('Инверторная технология', text)


class InverterTitleFallbackTests(unittest.TestCase):
    def test_inverter_from_title_when_no_tech_field(self):
        # У части позиций Русклимата нет tech-поля инвертора, но оно есть в названии.
        rows = [_tr('Уровень шума внутр. блока', '35')]
        text = '\n'.join(specs.build_specs_message(
            rows, 'Ballu', 'BLCI', 'rusklimat',
            titles=['Сплит-система Ballu BLCI инверторной серии комплект']))
        self.assertIn('Инверторная технология', text)

    def test_title_does_not_override_explicit_no(self):
        rows = [_tr('Инверторная технология', 'нет')]
        text = '\n'.join(specs.build_specs_message(
            rows, 'X', 'Y', 'breeze', titles=['X inverter model']))
        self.assertNotIn('Инверторная технология', text)


class BuildEmptyTests(unittest.TestCase):
    def test_empty_rows(self):
        text = '\n'.join(specs.build_specs_message([], 'X', 'Y', 'breeze'))
        self.assertIn('уточняются', text)
        self.assertNotIn('<blockquote>', text)


class BuildForCardTests(unittest.TestCase):
    """build_specs_for_card — plain-text список для промпта фотоген-агента."""

    def setUp(self):
        self.rows = [
            _tr('Класс энергоэффективности EER (охлаждение)', 'A+++'),
            _tr('Инверторная технология', 'да'),
            _tr('Минимальный уровень шума внутреннего блока', '19'),
            _tr('Управление c мобильного приложения по Wi-Fi', 'да'),
        ]

    def test_returns_plain_list(self):
        lines = specs.build_specs_for_card(self.rows, 'Hisense', 'AKOYA', 'breeze')
        self.assertIsInstance(lines, list)
        self.assertTrue(all(isinstance(s, str) for s in lines))
        joined = '\n'.join(lines)
        # plain text: ни HTML-обёртки, ни шапки блока
        self.assertNotIn('<blockquote>', joined)
        self.assertNotIn('💡', joined)
        self.assertIn('Класс энергоэффективности A+++', joined)
        self.assertIn('Wi-Fi управление', joined)

    def test_empty_rows_empty_list(self):
        self.assertEqual(specs.build_specs_for_card([], 'X', 'Y', 'breeze'), [])

    def test_lines_match_block(self):
        # Те же пункты, что попадают в build_specs_block (цитата) — без задвоений логики.
        lines = specs.build_specs_for_card(self.rows, 'Hisense', 'AKOYA', 'breeze')
        block = specs.build_specs_block(self.rows, 'Hisense', 'AKOYA', 'breeze')
        for ln in lines:
            self.assertIn(ln, block)


if __name__ == '__main__':
    unittest.main()
