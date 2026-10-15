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
from urllib.parse import urlsplit

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
            logger.warning('Telegram попытка %d/%d не удалась: %s', attempt, retries, type(exc).__name__)
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
            code=getattr(getattr(exc,'response',None),'status_code',None)
            logger.warning('Telegram %s попытка %d/%d: %s HTTP %s', method, attempt, retries, type(exc).__name__, code)
            if attempt < retries:
                time.sleep(2)
    return None


def get_updates(offset=None, timeout=25):
    """Long-poll getUpdates. Возвращает список updates (или [])."""
    payload = {'timeout': timeout, 'allowed_updates': ['message', 'callback_query']}
    if offset is not None:
        payload['offset'] = offset
    # (connect, read): связь VPS→Telegram бывает залипает на коннекте — быстрый
    # connect-timeout (10с) даёт переподключиться вместо ожидания 40с; read должен
    # быть больше long-poll timeout, чтобы успел вернуться апдейт.
    result = _post('getUpdates', payload, timeout=(10, timeout + 15), retries=1)
    return result or []


def set_my_commands(commands):
    """setMyCommands — наполняет нативную кнопку «☰ Menu» рядом с полем ввода
    (список команд, напр. /menu). Идемпотентно, зовём при старте бота."""
    return _post('setMyCommands', {'commands': commands})


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


def send_photo(chat_id, photo, caption=None):
    """Try URL once; supplier CDNs often block Telegram, so upload bytes as fallback."""
    if not TELEGRAM_BOT_TOKEN: return None
    payload = {'chat_id': chat_id, 'photo': photo}
    if caption:
        payload['caption'] = caption
        payload['parse_mode'] = 'HTML'
    result=_post('sendPhoto', payload, retries=1)
    if result: return result
    if not isinstance(photo,str) or urlsplit(photo).scheme not in ('http','https'):
        return None
    try:
        limit=10*1024*1024
        with requests.get(photo,headers={'User-Agent':'SplithubStockBot/1.0'},
                          timeout=(10,30),stream=True) as response:
            response.raise_for_status()
            chunks=[]; size=0
            for chunk in response.iter_content(65536):
                size+=len(chunk)
                if size>limit:
                    logger.warning('Supplier photo exceeds Telegram upload limit')
                    return None
                chunks.append(chunk)
            content=b''.join(chunks)
        if content.startswith(b'\xff\xd8\xff'): name,mime='product.jpg','image/jpeg'
        elif content.startswith(b'\x89PNG\r\n\x1a\n'): name,mime='product.png','image/png'
        elif content.startswith(b'RIFF') and content[8:12]==b'WEBP': name,mime='product.webp','image/webp'
        else:
            logger.warning('Supplier did not return a supported photo')
            return None
        data={'chat_id':chat_id}
        if caption: data.update(caption=caption,parse_mode='HTML')
        result=_session.post(_api_url('sendPhoto'),data=data,
            files={'photo':(name,content,mime)},timeout=(15,60))
        if result.ok:
            body=result.json()
            if body.get('ok'):
                logger.info('Supplier photo delivered by multipart upload')
                return body.get('result')
        logger.warning('Telegram photo upload failed: HTTP %s',result.status_code)
    except (requests.RequestException,ValueError) as exc:
        logger.warning('Supplier photo upload failed: %s',type(exc).__name__)
    return None


def send_document(chat_id, path, caption=''):
    """One multipart upload; caller can safely report a failed delivery."""
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return False
    try:
        with open(path, 'rb') as stream:
            response = _session.post(_api_url('sendDocument'),
                data={'chat_id': chat_id, 'caption': caption},
                files={'document': (str(path).replace('\\', '/').split('/')[-1], stream,
                       'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},
                timeout=(15, 90))
        return response.ok and response.json().get('ok') is True
    except (requests.RequestException, ValueError):
        logger.error('Telegram document upload failed')
        return False
