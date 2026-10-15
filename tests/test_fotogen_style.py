import unittest
from unittest.mock import Mock,patch
from stock_report_bot import fotogen_bridge as bridge
from integrations.fotogen_publish_mode import publication_mode

class StyleTest(unittest.TestCase):
    def test_render_style_is_separate_from_channel_destination(self):
        for mode in ('mcp','kbt'):
            with patch.object(bridge,'FOTOGEN_CARD_MODE',mode),patch.object(bridge,'FOTOGEN_API_URL','http://localhost:8765'), \
                 patch.object(bridge,'FOTOGEN_API_TOKEN','test-key'),patch.object(bridge.requests,'get',return_value=Mock(content=b'photo')), \
                 patch.object(bridge.requests,'post',return_value=Mock()) as post:
                self.assertTrue(bridge.submit_card('https://example.com/p.jpg','Brand','Series',['A'],1,caption='price')[0])
                data=post.call_args.kwargs['data']
                self.assertEqual(data['mode'],mode)
                self.assertEqual(data['publish_mode'],'conditioner')
                self.assertEqual(data['caption'],'price')

    def test_old_wave_style_cannot_be_selected(self):
        with patch.object(bridge,'FOTOGEN_CARD_MODE','conditioner'),patch.object(bridge,'FOTOGEN_API_URL','http://localhost:8765'), \
             patch.object(bridge,'FOTOGEN_API_TOKEN','test-key'),patch.object(bridge.requests,'post') as post:
            self.assertFalse(bridge.submit_card('https://example.com/p.jpg','Brand','Series',[],1)[0])
            post.assert_not_called()

    def test_render_mcp_keeps_original_channel_and_approval(self):
        self.assertEqual(publication_mode({'mode':'mcp','publish_mode':'conditioner'}),'conditioner')
        self.assertEqual(publication_mode({'mode':'kbt','publish_mode':'conditioner'}),'conditioner')

    def test_existing_photogen_jobs_keep_their_destinations(self):
        self.assertEqual(publication_mode({'mode':'conditioner'}),'conditioner')
        self.assertEqual(publication_mode({'mode':'mcp'}),'mcp')
        self.assertEqual(publication_mode({'mode':'mcp','publish_mode':None}),'mcp')

if __name__=='__main__': unittest.main()
