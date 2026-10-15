import unittest
from unittest.mock import Mock,MagicMock,patch
from stock_report_bot import telegram,catalog_menu
from stock_report_bot.supplier_catalog import plain

class PhotoTest(unittest.TestCase):
    def test_failed_url_uploads_photo_bytes_with_same_caption(self):
        download=MagicMock()
        download.__enter__.return_value=download
        content=b'\xff\xd8\xffactual jpg'
        download.iter_content.return_value=[content]
        upload=Mock(ok=True)
        upload.json.return_value={'ok':True,'result':{'message_id':123,'photo':[{}]}}
        with patch.object(telegram,'TELEGRAM_BOT_TOKEN','test'),patch.object(telegram,'_post',return_value=None) as direct, \
             patch.object(telegram.requests,'get',return_value=download),patch.object(telegram._session,'post',return_value=upload) as post:
            result=telegram.send_photo(1,'https://daichi.business/test.jpg','<b>Kentatsu</b>')
            self.assertEqual(result['message_id'],123)
            self.assertEqual(direct.call_args.kwargs['retries'],1)
            self.assertEqual(post.call_args.kwargs['files']['photo'][1],content)
            self.assertEqual(post.call_args.kwargs['data']['caption'],'<b>Kentatsu</b>')
            self.assertEqual(post.call_args.kwargs['data']['parse_mode'],'HTML')

    def test_direct_success_does_not_download(self):
        with patch.object(telegram,'TELEGRAM_BOT_TOKEN','test'),patch.object(telegram,'_post',return_value={'message_id':1}), \
             patch.object(telegram.requests,'get') as get:
            self.assertEqual(telegram.send_photo(1,'https://example.com/a.jpg')['message_id'],1)
            get.assert_not_called()

    def test_non_image_response_is_not_uploaded(self):
        download=MagicMock(); download.__enter__.return_value=download
        download.iter_content.return_value=[b'<html>forbidden</html>']
        with patch.object(telegram,'TELEGRAM_BOT_TOKEN','test'),patch.object(telegram,'_post',return_value=None), \
             patch.object(telegram.requests,'get',return_value=download),patch.object(telegram._session,'post') as post:
            self.assertIsNone(telegram.send_photo(1,'https://example.com/a.jpg'))
            post.assert_not_called()

    def test_failure_is_visible_and_text_is_not_lost(self):
        with patch.object(catalog_menu,'send_photo',return_value=None),patch.object(catalog_menu,'send_message') as send:
            catalog_menu.send_payload(1,['<b>Kentatsu</b>','Мощность: 24 кВт'],'https://example.com/a.jpg')
            texts=[c.args[1] for c in send.call_args_list]
            self.assertTrue(any('Фото не удалось' in t for t in texts))
            self.assertTrue(any('24 кВт' in t for t in texts))

    def test_supplier_escaped_units_are_readable(self):
        self.assertEqual(plain('м&amp;lt;sup&amp;gt;3&amp;lt;/sup&amp;gt;/ч'),'м³/ч')
        p={'title':'Котёл','supplier':'daichi','brand':'Kentatsu','series':'Nobby',
           'specs':[{'title':'Расход','value':'2,59 м&amp;lt;sup&amp;gt;3&amp;lt;/sup&amp;gt;/ч'}]}
        self.assertIn('м³/ч','\n'.join(catalog_menu.compact_specs(p)))
        self.assertNotIn('&lt;','\n'.join(catalog_menu.compact_specs(p)))

if __name__=='__main__': unittest.main()
