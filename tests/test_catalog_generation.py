import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from stock_report_bot import catalog_generation as g, catalog_menu as m, catalog

def sample(model='RC-VN22HN'):
    return dict(id=model,sku=model,model=model,title='Сплит-система '+model,brand='ROYAL CLIMA',
        series='Классические сплит-системы серии VELA NUOVA',supplier='breez',
        group_name='Кондиционирование',kind='Бытовые сплит-системы',purchase_price='20000',
        currency='RUB',quantity=4,images=['https://example.com/vela.jpg'],
        specs=[{'title':'Класс энергоэффективности','value':'A'}],utp='',warehouse='Бриз Крым',updated_at='2026-10-16')

class GenerationTest(unittest.TestCase):
    def test_previous_caption_with_all_models_and_no_private_price(self):
        p=sample(); q=sample('RC-VN28HN')
        with patch.object(catalog,'products',return_value=[p,q]):
            payload=g.payload(p,5)
        self.assertEqual(payload['photo_url'],p['images'][0])
        self.assertEqual(payload['model'],'VELA NUOVA')
        self.assertIn('<blockquote>',payload['caption'])
        self.assertIn('21 090',payload['caption'])
        self.assertNotIn('Бриз',payload['caption'])
        self.assertNotIn('20000',payload['caption'])
        self.assertNotIn('инвертор',payload['caption'])

    def test_generation_preview_never_submits(self):
        p=sample()
        with patch.object(catalog,'product',return_value=p),patch.object(catalog,'products',return_value=[p]), \
             patch.object(m,'show') as show,patch.object(g.fotogen_bridge,'submit_card') as submit:
            m.handle(1,2,'cat:q:'+p['id']+':5')
            submit.assert_not_called()
            self.assertIn('MCP',show.call_args.args[2])
            self.assertIn('Графитовый фон',show.call_args.args[2])
            buttons=[b for row in show.call_args.args[3] for b in row]
            self.assertTrue(any(b['callback_data'].startswith('cat:j:') for b in buttons))

    def test_double_tap_submits_only_once(self):
        p=sample()
        with tempfile.TemporaryDirectory() as d,patch.object(catalog,'db_path',return_value=Path(d)/'catalog.sqlite'), \
             patch.object(catalog,'products',return_value=[p]),patch.object(g.fotogen_bridge,'submit_card',return_value=(True,'ok')) as submit:
            self.assertEqual(g.submit(p,5,1,2),(True,'submitted'))
            self.assertEqual(g.submit(p,5,1,2),(False,'duplicate'))
            submit.assert_called_once()
            self.assertEqual(submit.call_args.kwargs['chat_id'],1)

    def test_unconfirmed_request_is_not_automatically_repeated(self):
        p=sample()
        with tempfile.TemporaryDirectory() as d,patch.object(catalog,'db_path',return_value=Path(d)/'catalog.sqlite'), \
             patch.object(catalog,'products',return_value=[p]),patch.object(g.fotogen_bridge,'submit_card',return_value=(False,'timeout')) as submit:
            self.assertEqual(g.submit(p,5,1,2),(False,'unconfirmed'))
            self.assertEqual(g.submit(p,5,1,2),(False,'duplicate'))
            submit.assert_called_once()

    def test_missing_photo_never_submits(self):
        p=dict(sample(),images=[])
        with patch.object(catalog,'products',return_value=[p]),patch.object(g.fotogen_bridge,'submit_card') as submit:
            self.assertEqual(g.submit(p,5,1,2),(False,'no_photo'))
            submit.assert_not_called()

    def test_client_payload_includes_price_and_features(self):
        p=sample()
        with patch.object(catalog,'products',return_value=[p]),patch.object(m,'compact_specs',return_value=['Класс A','Гарантия 3 года']), \
             patch.object(m,'send_payload') as send:
            m.send_series(1,p,5)
            text='\n'.join(send.call_args.args[1])
            self.assertIn('21 090',text)
            self.assertIn('Гарантия 3 года',text)
            self.assertEqual(send.call_args.args[2],p['images'][0])

    def test_group_navigation_is_not_generation(self):
        p=sample()
        with patch.object(catalog,'products',return_value=[p]),patch.object(catalog,'product') as lookup, \
             patch.object(m,'edit_message_text') as edit:
            m.handle(1,2,'cat:g:'+m.token('Кондиционеры'))
            lookup.assert_not_called()
            self.assertIn('Выберите поставщика',edit.call_args.args[2])

if __name__=='__main__': unittest.main()
