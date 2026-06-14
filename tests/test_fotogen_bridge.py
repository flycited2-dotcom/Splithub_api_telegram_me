"""Тест HTTP-моста к фотоген-агенту. Проверяем guard-ветку без сети: если URL/токен
не заданы, submit_card возвращает (False, …) и НЕ обращается ни к каким requests."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_report_bot import fotogen_bridge


class GuardTests(unittest.TestCase):
    def setUp(self):
        # Сохранить и обнулить конфиг на время теста (модуль читает константы при импорте).
        self._url, self._token = fotogen_bridge.FOTOGEN_API_URL, fotogen_bridge.FOTOGEN_API_TOKEN
        fotogen_bridge.FOTOGEN_API_URL = ''
        fotogen_bridge.FOTOGEN_API_TOKEN = ''
        # Если в сеть всё-таки полезут — взорвём тест (сети в юнит-тестах быть не должно).
        self._get, self._post = fotogen_bridge.requests.get, fotogen_bridge.requests.post

        def _boom(*a, **k):
            raise AssertionError('submit_card не должен ходить в сеть при пустом конфиге')

        fotogen_bridge.requests.get = _boom
        fotogen_bridge.requests.post = _boom

    def tearDown(self):
        fotogen_bridge.FOTOGEN_API_URL, fotogen_bridge.FOTOGEN_API_TOKEN = self._url, self._token
        fotogen_bridge.requests.get, fotogen_bridge.requests.post = self._get, self._post

    def test_no_config_returns_false_without_network(self):
        ok, msg = fotogen_bridge.submit_card(
            photo_url='http://example/x.jpg', brand='Samsung', model='WindFree',
            specs_lines=['⚡ A++'], chat_id=1264067528)
        self.assertFalse(ok)
        self.assertIn('не задан', msg)


if __name__ == '__main__':
    unittest.main()
