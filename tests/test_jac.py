import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_report_bot.jac import map_rows, load_jac_rows
from stock_report_bot.report import build_report_chunks


def _p(article, category, price, crimea, holod='2.2', name=None):
    attrs = {'Крым': crimea, 'Москва (ОП АЯК - Крым)': '0', 'РРЦ': '30 000 ₽'}
    if holod is not None:
        attrs['Холод, кВт'] = holod
    return {
        'article': article, 'name': name or article, 'category': category,
        'price': price, 'stock_qty': 1, 'attributes': attrs, 'source': 'jac_b2b',
    }


SAMPLE = [
    _p('EKSA-20HN', 'Бытовые сплит-системы', 12360.0, '5'),            # ok
    _p('MDSP-12', 'Полупромышленные системы', 45000.0, 'Больше 100'),  # ok, qty=100
    _p('MULTI-3X', 'Мультисплит-системы', 90000.0, '7'),              # искл.: категория
    _p('EKA-WFX Wi-Fi', 'Аксессуары', 1710.0, '8', holod=None),       # искл.: аксессуар (нет btu)
    _p('NOBTU-09', 'Бытовые сплит-системы', 20000.0, '4', holod='0'), # искл.: btu=0
    _p('ZERO-09', 'Бытовые сплит-системы', 21000.0, '0'),             # искл.: Крым=0
    _p('Мульти-блок', 'Бытовые сплит-системы', 50000.0, '3'),         # искл.: денилист названия
]


class JacAdapterTests(unittest.TestCase):
    def test_filtering(self):
        rows = map_rows(SAMPLE)
        titles = sorted(r['title'] for r in rows)
        self.assertEqual(titles, ['EKSA-20HN', 'MDSP-12'])

    def test_row_shape_and_opt_price(self):
        rows = {r['title']: r for r in map_rows(SAMPLE)}
        r = rows['EKSA-20HN']
        self.assertEqual(r['source'], 'jac')
        self.assertEqual(r['price_wholesale'], 12360.0)   # «Ваша цена» = опт
        self.assertIsNone(r['price_base'])
        self.assertEqual(r['crimea_qty'], 5)

    def test_bolshe_n_parsed_as_number(self):
        rows = {r['title']: r for r in map_rows(SAMPLE)}
        self.assertEqual(rows['MDSP-12']['crimea_qty'], 100)   # «Больше 100» -> 100

    def test_missing_or_empty_path_returns_empty(self):
        self.assertEqual(load_jac_rows(''), [])
        self.assertEqual(load_jac_rows('/no/such/file_xyz.json'), [])

    def test_load_from_file(self):
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(SAMPLE, f, ensure_ascii=False)
            path = f.name
        try:
            rows = load_jac_rows(path)
            self.assertEqual(len(rows), 2)
        finally:
            os.unlink(path)

    def test_renders_in_report_with_jac_block(self):
        rows = map_rows(SAMPLE)
        text = '\n'.join(build_report_chunks(rows))
        self.assertIn('🟨 <b>JAC</b>', text)
        self.assertIn('EKSA-20HN — 12 360 ₽ — 5 шт.', text)
        self.assertIn('MDSP-12 — 45 000 ₽ — 100 шт.', text)


if __name__ == '__main__':
    unittest.main()
