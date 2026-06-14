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


# ── интерактивный режим (long-polling + кнопки) ────────────────────────────
# Те же требования VPS: charset=utf-8, keep-alive Session, ретраи. Используются
# ботом меню (stock_report_bot.bot); суточный отчёт их не задействует.
def _api_url(method):
    return f'{TELEGRAM_API_URL.rstrip("/")}/bot{TELEGRAM_BOT_TOKEN}/{method}'


def _post(method, payload, timeout=30, retries=3):
    """POST к Bot API с charset=utf-8 и ретраями. Возвращает result или None."""
    if not TELEGRAM_BOT_TOKEN:
        return None
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    for attempt in range(1, retries + 1):
        try:
            resp = _session.post(
                _api_url(method), data=body,
                headers={'Content-Type': 'application/json; charset=utf-8'},
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json().get('result')
        except Exception as exc:
            logger.warning('Telegram %s попытка %d/%d: %s', method, attempt, retries, exc)
            if attempt < retries:
                time.sleep(2)
    return None


def get_updates(offset=None, timeout=25):
    """Long-poll getUpdates. Возвращает список updates (или [])."""
    payload = {'timeout': timeout, 'allowed_updates': ['message', 'callback_query']}
    if offset is not None:
        payload['offset'] = offset
    # HTTP-timeout должен быть больше long-poll timeout.
    result = _post('getUpdates', payload, timeout=timeout + 15, retries=1)
    return result or []


def send_message(chat_id, text, reply_markup=None):
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML',
               'disable_web_page_preview': True}
    if reply_markup is not None:
        payload['reply_markup'] = reply_markup
    return _post('sendMessage', payload)


def edit_message_text(chat_id, message_id, text, reply_markup=None):
    payload = {'chat_id': chat_id, 'message_id': message_id, 'text': text,
               'parse_mode': 'HTML', 'disable_web_page_preview': True}
    if reply_markup is not None:
        payload['reply_markup'] = reply_markup
    return _post('editMessageText', payload)


def answer_callback_query(callback_query_id, text=None):
    payload = {'callback_query_id': callback_query_id}
    if text:
        payload['text'] = text
    return _post('answerCallbackQuery', payload)


def send_photo(chat_id, photo, caption=None, reply_markup=None):
    """sendPhoto по URL (картинку забирает сам Telegram). caption ≤ 1024 символов,
    HTML. None, если не удалось (URL недоступен Telegram) — caller откатывается на текст."""
    payload = {'chat_id': chat_id, 'photo': photo}
    if caption:
        payload['caption'] = caption
        payload['parse_mode'] = 'HTML'
    if reply_markup is not None:
        payload['reply_markup'] = reply_markup
    return _post('sendPhoto', payload)
