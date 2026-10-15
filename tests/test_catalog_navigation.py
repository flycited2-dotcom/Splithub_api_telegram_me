import unittest
from unittest.mock import patch
from stock_report_bot import catalog_menu as m

def product(sku,**fields):
    return dict(id=sku,sku=sku,model=sku,title='Модель '+sku,brand='Kentatsu',series='Kanami',
                supplier='daichi',group_name='Бытовые сплит-системы',kind='Бытовой кондиционер',
                quantity=3,purchase_price='10000',currency='RUB',images=['https://example.com/photo.jpg'],
                specs=[{'title':'Площадь','value':'25 м²'}],updated_at='2026-10-15',warehouse='Симферопль',**fields)

class NavigationTest(unittest.TestCase):
    def test_shared_group_and_supplier_step(self):
        p=product('1'); b=dict(p,id='2',supplier='breez',group_name='Кондиционирование',kind='Бытовые сплит-системы')
        self.assertEqual(m.group_of(p),m.group_of(b)); self.assertEqual(m.kind_of(p),m.kind_of(b))
        with patch.object(m.catalog,'products',return_value=[p,b]),patch.object(m,'edit_message_text') as edit:
            m.root(1,2,'cat:g:'+m.token('Кондиционеры'))
            buttons=[b for row in edit.call_args.args[3]['inline_keyboard'] for b in row]
            self.assertTrue(any('Breez' in b['text'] for b in buttons))
            self.assertTrue(any('Daichi' in b['text'] for b in buttons))

    def test_series_keeps_supplier_brand_type_and_all_models(self):
        p=product('1'); q=product('2'); other=dict(q,id='3',supplier='breez')
        indoor=dict(q,id='4',kind='Внутренний блок кондиционера')
        with patch.object(m.catalog,'products',return_value=[p,q,other,indoor]):
            self.assertEqual([r['id'] for r in m.series_positions(p)],['1','2'])
            text='\n'.join(m.series_lines(p,10))
            self.assertIn('1',text); self.assertIn('2',text); self.assertNotIn('breez',text)
            self.assertIn('11 090 ₽',text)

    def test_series_without_name_is_single_product(self):
        p=dict(product('1'),series='')
        self.assertEqual(m.series_positions(p),[p])

    def test_photo_caption_includes_specs(self):
        p=product('1')
        with patch.object(m,'send_photo',return_value=True) as photo,patch.object(m,'send_message'):
            m.send_payload(1,['<b>Модель</b>','Площадь: 25 м²'],'https://example.com/photo.jpg')
            self.assertIn('25 м²',photo.call_args.args[2])
            self.assertLessEqual(len(photo.call_args.args[2]),1024)

    def test_photo_long_caption_does_not_drop_remainder(self):
        lines=['<b>Модель</b>']+['Характеристика '+str(n)+' '+('x'*80) for n in range(40)]
        with patch.object(m,'send_photo',return_value=True) as photo,patch.object(m,'send_message') as send:
            m.send_payload(1,lines,'https://example.com/photo.jpg')
            joined=photo.call_args.args[2]+'\n'+'\n'.join(c.args[1] for c in send.call_args_list)
            for line in lines: self.assertIn(line,joined)

    def test_all_navigation_callbacks_fit_and_have_return(self):
        p=product('1')
        data=[f'cat:g:{m.token(m.group_of(p))}',f'cat:v:{m.token(m.group_of(p))}:daichi:0',
              f'cat:l:{m.token(m.group_of(p))}:daichi:{m.token(m.kind_of(p))}:0']
        with patch.object(m.catalog,'products',return_value=[p]),patch.object(m,'edit_message_text') as edit:
            for callback in data:
                m.root(1,2,callback)
                buttons=[b for row in edit.call_args.args[3]['inline_keyboard'] for b in row]
                self.assertTrue(any('Назад' in b['text'] or 'Группы' in b['text'] for b in buttons))
                self.assertTrue(any(b['callback_data']=='cat:home' for b in buttons))
                self.assertTrue(all(len(b['callback_data'].encode())<=64 for b in buttons))

    def test_home_download_is_blue_and_search_separate(self):
        with patch.object(m,'send_message') as send:
            m.home(1)
            buttons=[b for row in send.call_args.args[2]['inline_keyboard'] for b in row]
            download=next(b for b in buttons if b['callback_data']=='cat:x')
            self.assertEqual(download['style'],'primary')
            self.assertTrue(any(b['callback_data']=='cat:find' for b in buttons))
            self.assertTrue(any(b['callback_data']=='cat:old' for b in buttons))

    def test_search_includes_model_and_source(self):
        p=product('KSGA26')
        with patch.object(m.catalog,'products',return_value=[p]),patch.object(m,'send_message') as send:
            m.search(1,'ksga26')
            self.assertIn('Найдено: 1',send.call_args.args[1])

if __name__=='__main__': unittest.main()
