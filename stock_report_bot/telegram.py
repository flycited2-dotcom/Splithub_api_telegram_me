"""Отправка сообщения в Telegram.

КРИТИЧНО: явный charset=utf-8 в Content-Type. Без него кириллица ломается при
прохождении через socat-proxy на VPS (как было на сайте — заявки приходили
с «???»). ensure_ascii=False даёт нативный UTF-8 в теле запроса.
"""
import json
import logging

import requests

from stock_report_bot.config import TELEGRAM_API_URL, TELEGRAM_BOT_TOKEN

logger = logging.getLogger(__name__)


def send_telegram(text, chat_id):
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        logger.warning('send_telegram: не задан токен или chat_id')
        return False
    base = TELEGRAM_API_URL.rstrip('/')
    payload = json.dumps(
        {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'},
        ensure_ascii=False,
    ).encode('utf-8')
    try:
        resp = requests.post(
            f'{base}/bot{TELEGRAM_BOT_TOKEN}/sendMessage',
            data=payload,
            headers={'Content-Type': 'application/json; charset=utf-8'},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.error('Telegram send failed: %s', exc)
        return False
