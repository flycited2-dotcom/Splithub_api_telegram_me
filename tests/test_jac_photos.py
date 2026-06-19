import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_report_bot.jac_photos import (
    normalize_series, load_photos, photo_ref, resolve_photo,
)

_SAMPLE = {
    'MDV': {'INTEGRA PRO': 'https://mdv-aircond.ru/upload/iblock/x/a.png'},
    'THAICON': {'BALANCE INVERTER': 'THAICON__BALANCE_INVERTER.png'},
}


class NormalizeTests(unittest.TestCase):
    def test_upper_collapse(self):
        self.assertEqual(normalize_series('Integra  Pro '), 'INTEGRA PRO')
        self.assertEqual(normalize_series(None), '')


class LoadTests(unittest.TestCase):
    def test_empty_and_missing(self):
        self.assertEqual(load_photos(''), {})
        self.assertEqual(load_photos('/no/such/jac_photos_x.json'), {})


class PhotoRefTests(unittest.TestCase):
    def test_hit_url(self):
        self.assertEqual(photo_ref(_SAMPLE, 'MDV', 'integra pro'),
                         'https://mdv-aircond.ru/upload/iblock/x/a.png')

    def test_hit_local(self):
        self.assertEqual(photo_ref(_SAMPLE, 'THAICON', 'Balance Inverter'),
                         'THAICON__BALANCE_INVERTER.png')

    def test_miss_brand_and_series(self):
        self.assertIsNone(photo_ref(_SAMPLE, 'EUROKLIMAT', 'ALBA'))
        self.assertIsNone(photo_ref(_SAMPLE, 'MDV', 'NO SUCH'))


class ResolveTests(unittest.TestCase):
    def test_url_passthrough(self):
        u = 'https://mdv-aircond.ru/x.png'
        self.assertEqual(resolve_photo(u), u)

    def test_local_joins_photos_dir(self):
        got = resolve_photo('a.png', json_path='/opt/app/data/jac_photos_latest.json')
        self.assertEqual(got.replace('\\', '/'), '/opt/app/data/photos/a.png')

    def test_none(self):
        self.assertIsNone(resolve_photo(None))
