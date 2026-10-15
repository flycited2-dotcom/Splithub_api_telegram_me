import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from unittest.mock import patch
from stock_report_bot import catalog
from stock_report_bot.catalog_excel import export_xlsx
from stock_report_bot.supplier_catalog import parse_breez, parse_daichi, quantity

class CatalogTest(unittest.TestCase):
    def sample(self,sku='001',price='120.50'):
        return dict(sku=sku,title='Товар',model='=HYPERLINK("evil")',group_name='Комплектующие',
                    kind='Трубы',brand='Бренд',quantity=2,purchase_price=price,currency='RUB',
                    warehouse='Бриз Крым',images=[],specs=[])

    def test_atomic_replace_and_supplier_ids(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'db.sqlite'
            catalog.replace_supplier('breez',[self.sample()],path)
            before=catalog.products(path)
            with self.assertRaises(Exception):
                catalog.replace_supplier('breez',[self.sample(),self.sample()],path)
            self.assertEqual(catalog.products(path),before)
            catalog.replace_supplier('daichi',[self.sample()],path)
            self.assertEqual(len({p['id'] for p in catalog.products(path)}),2)
            catalog.replace_supplier('breez',[],path)
            self.assertEqual(len(catalog.products(path)),1)

    def test_breez_local_only_includes_accessories_and_missing_metadata(self):
        stock={'001':{'stocks':[{'stock':'Бриз Крым','quantity':'>50'},
                               {'stock':'Ростов','quantity':999}], 'price':[{'ric':500}]}}
        rows=parse_breez(stock,{}, {}, {})
        self.assertEqual(rows[0]['quantity'],50)
        self.assertTrue(rows[0]['quantity_lower_bound'])
        self.assertIsNone(rows[0]['purchase_price'])
        self.assertEqual(rows[0]['sku'],'001')

    def test_daichi_warehouse_mismatch_rejected(self):
        p={'XML_ID':'1','STORE':{'XML_ID':'moscow','NAME':'Москва','STORE_AMOUNT':100}}
        with self.assertRaises(ValueError): parse_daichi({'p':p},{},'crimea')
        p['STORE']={'XML_ID':'crimea','NAME':'Симферопль','STORE_AMOUNT':2,'WAITING_AMOUNT':50}
        p['PARAMS']={'ATTR_L_GOODGROUP':'Котлы'}
        rows=parse_daichi({'p':p},{},'crimea')
        self.assertEqual(rows[0]['quantity'],2)
        self.assertEqual(rows[0]['group_name'],'Котлы')

    def test_xlsx_typed_prices_and_no_formula_injection(self):
        with tempfile.TemporaryDirectory() as d:
            p=dict(self.sample(),supplier='breez',updated_at='2026-10-15T08:00:00Z')
            path=export_xlsx([p],Path(d)/'stock.xlsx')
            with ZipFile(path) as z:
                for name in z.namelist(): ET.fromstring(z.read(name))
                data=z.read('xl/worksheets/sheet2.xml').decode()
                self.assertNotIn('<f>',data)
                self.assertIn('120.5',data)
                self.assertIn('HYPERLINK',data)
                self.assertIn('autoFilter',data)

    def test_quantity(self):
        self.assertEqual(quantity('>50'),(50,True))
        self.assertEqual(quantity('-4'),(0,False))
        self.assertEqual(quantity('нет'),(0,False))

    def test_category_pagination_and_callback_size(self):
        from stock_report_bot import catalog_menu
        rows=[dict(self.sample(str(i)),group_name=f'Группа {i}') for i in range(40)]
        with patch.object(catalog_menu.catalog,'products',return_value=rows), \
             patch.object(catalog_menu.catalog,'status',return_value=[]), \
             patch.object(catalog_menu,'send_message') as send:
            catalog_menu.root(1)
            kb=send.call_args.args[2]['inline_keyboard']
            self.assertLessEqual(len(kb),10)
            for line in kb:
                for b in line: self.assertLessEqual(len(b['callback_data'].encode()),64)

    def test_client_card_does_not_expose_supplier_or_purchase(self):
        from stock_report_bot.catalog_menu import description
        p=dict(self.sample(price='12345.67'),supplier='breez',updated_at='2026-10-15')
        text='\n'.join(description(p,True,10))
        self.assertNotIn('12345.67',text)
        self.assertNotIn('breez',text)
        self.assertNotIn('Остаток',text)
        self.assertIn('Цена:',text)

if __name__=='__main__': unittest.main()
