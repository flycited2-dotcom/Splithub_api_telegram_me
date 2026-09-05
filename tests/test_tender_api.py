import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_report_bot import tender_api
from stock_report_bot.tender_api import build_response, search_catalog


ROWS = [
    {
        "source": "breeze",
        "supplier_name": "Бриз",
        "sku": "BR-12",
        "brand": "Royal Clima",
        "series": "Attica Nero",
        "model": "RC-AN35HN",
        "name": "Royal Clima Attica Nero RC-AN35HN",
        "price_gross": 30000.0,
        "stock_quantity": 8,
        "warehouse": "Симферополь",
        "specs": {"inverter": False},
    },
    {
        "source": "daichi",
        "supplier_name": "Daichi",
        "sku": "DA-12",
        "brand": "Kentatsu",
        "series": "Kanami",
        "model": "KSGA35HFAN1",
        "name": "Kentatsu Kanami KSGA35HFAN1",
        "price_gross": 32000.0,
        "stock_quantity": 4,
        "warehouse": "Симферополь",
        "specs": {"inverter": True},
    },
    {
        "source": "jac",
        "supplier_name": "JAC",
        "sku": "MDSAG-09HRN8",
        "brand": "MDV",
        "series": "Classic Inverter",
        "model": "MDSAG-09HRN8",
        "name": "MDV Classic Inverter MDSAG-09HRN8",
        "price_gross": 25000.0,
        "stock_quantity": 11,
        "warehouse": "Симферополь",
        "specs": {"inverter": True},
    },
]


class TenderApiSearchTests(unittest.TestCase):
    def test_searches_model_and_brand(self):
        result = search_catalog(ROWS, "Kentatsu KSGA35", limit=10)
        self.assertEqual([row["sku"] for row in result], ["DA-12"])

    def test_generic_climate_query_returns_competitive_catalog(self):
        result = search_catalog(ROWS, "сплит-система кондиционер", limit=10)
        self.assertEqual(len(result), 3)

    def test_deduplicates_same_supplier_sku(self):
        result = search_catalog(ROWS + [dict(ROWS[0])], "Royal Clima", limit=10)
        self.assertEqual(len(result), 1)

    def test_response_uses_supplier_compatible_contract(self):
        response = build_response({"query": "MDV", "limit": 10}, ROWS)
        self.assertTrue(response["ok"])
        self.assertEqual(response["total"], 1)
        product = response["products"][0]
        self.assertEqual(product["source"], "jac")
        self.assertEqual(product["purchasePriceGross"], 25000.0)
        self.assertEqual(product["stockQuantity"], 11)
        self.assertTrue(product["isAvailable"])

    def test_rejects_empty_query(self):
        with self.assertRaises(ValueError):
            build_response({"query": ""}, ROWS)


if __name__ == "__main__":
    unittest.main()


class ImageUrlTests(unittest.TestCase):
    """Фотография должна доезжать до тендерного агента.

    В БД сайта у 464 позиций из 489 есть снимок карточки, и площадка РТС
    принимает его ссылкой — без этого поля пришлось бы искать фото заново.
    """

    def test_normalize_row_keeps_image_url(self):
        row = {"source": "breeze", "brand": "ECOSTAR", "title": "Мобильный кондиционер",
               "image_url": "https://images.breez.ru/catalog/a/b.png", "crimea_qty": 1,
               "nc_code": "НС-1", "price_wholesale": 15290, "price_base": 15290}
        self.assertEqual(
            tender_api._normalize_row(row, {})["image_url"],
            "https://images.breez.ru/catalog/a/b.png",
        )

    def test_api_product_exposes_image_url(self):
        row = {"source": "breeze", "supplier_name": "Бриз", "sku": "НС-1",
               "image_url": "https://images.breez.ru/catalog/a/b.png", "stock_quantity": 1}
        self.assertEqual(
            tender_api._api_product(row)["imageUrl"],
            "https://images.breez.ru/catalog/a/b.png",
        )
