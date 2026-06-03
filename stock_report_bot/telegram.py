"""Отправка сообщения в Telegram.

КРИТИЧНО: явный charset=utf-8 в Content-Type. Без него кириллица ломается при
прохождении через socat-proxy на VPS (как было на сайте — заявки приходили
с «???»). ensure_ascii=False даёт нативный UTF-8 в теле запроса.

Надёжность на VPS: связь до Telegram нестабильна (часть TCP-коннектов отваливается
по timeout). Поэтому переиспользуем одно keep-alive соединение (Session) на все
сообщения отчёта и повторяем неудачную отправку (connect-timeout = сообщение не
ушло, повтор безопасен).
"""
import json
import logging
import time

import requests

from stock_report_bot.config import TELEGRAM_API_URL, TELEGRAM_BOT_TOKEN

logger = logging.getLogger(__name__)

# Один keep-alive коннект на все чанки отчёта — меньше рискованных handshake'ов.
_session = requests.Session()


def send_telegram(text, chat_id, retries=4, timeout=30):
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        logger.warning('send_telegram: не задан токен или chat_id')
        return False
    base = TELEGRAM_API_URL.rstrip('/')
    url = f'{base}/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    payload = json.dumps(
        {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'},
        ensure_ascii=False,
    ).encode('utf-8')
    for attempt in range(1, retries + 1):
        try:
            resp = _session.post(
                url,
                data=payload,
                headers={'Content-Type': 'application/json; charset=utf-8'},
                timeout=timeout,
            )
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.warning('Telegram попытка %d/%d не удалась: %s', attempt, retries, exc)
            if attempt < retries:
                time.sleep(3)
    logger.error('Telegram send окончательно не удалось после %d попыток', retries)
    return False
