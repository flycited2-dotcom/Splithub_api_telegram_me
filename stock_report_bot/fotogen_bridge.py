"""Отправка задачи на генерацию рекламной карточки товара в фотоген-агент.

Вызывается из bot.py при нажатии «🎨 Создать карточку». Скачивает фото товара по URL
(из БД сайта) и шлёт multipart-запрос на /api/submit-job фотоген-агента. Синхронный —
stock-бот не использует asyncio; сеть через requests (как и весь проект).
"""
import io
import logging

import requests

from stock_report_bot.config import FOTOGEN_API_URL, FOTOGEN_API_TOKEN

log = logging.getLogger('stock_report_bot.fotogen_bridge')

_TIMEOUT = 20   # сек на скачивание фото и на отправку задачи


def submit_card(photo_url, brand, model, specs_lines, chat_id, caption=''):
    """Поставить задачу генерации карточки в фотоген-агент.

    Args:
        photo_url:   URL фото товара из БД сайта (image_url позиции серии)
        brand:       Бренд (напр. «Samsung»)
        model:       Серия/модель (короткое имя, напр. «WindFree»)
        specs_lines: Список строк-преимуществ для {{SPECS}} промпта (plain text)
        chat_id:     Telegram chat_id владельца — куда фотоген отправит результат
        caption:     Готовая HTML-подпись-прайс для публикации в канал (фотоген хранит
                     её и ставит подписью к фото при «Опубликовать»). Пусто — без подписи.

    Returns:
        (True, 'ok') при успехе; (False, 'текст ошибки') при сбое. В сеть не ходит,
        если URL/токен не заданы.
    """
    if not FOTOGEN_API_URL or not FOTOGEN_API_TOKEN:
        return False, 'FOTOGEN_API_URL или FOTOGEN_API_TOKEN не задан в .env'

    try:
        r = requests.get(
            photo_url,
            headers={'User-Agent': 'SplithubStockBot/1.0'},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        photo_bytes = r.content
    except Exception as exc:
        log.warning('submit_card: не удалось скачать фото %s: %s', photo_url, exc)
        return False, f'Не удалось скачать фото товара: {exc}'

    specs_text = '\n'.join(specs_lines) if specs_lines else ''
    fname = f"{brand}_{model}.jpg".replace(' ', '_')

    try:
        resp = requests.post(
            f"{FOTOGEN_API_URL.rstrip('/')}/api/submit-job",
            headers={'x-agent-token': FOTOGEN_API_TOKEN},
            data={
                'mode': 'conditioner',
                'specs': specs_text,
                'brand': brand or '',
                'model': model or '',
                'chat_id': str(chat_id),
                'caption': caption or '',
            },
            files={'photo': (fname, io.BytesIO(photo_bytes), 'image/jpeg')},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        log.info('submit_card OK: %s %s → задача поставлена', brand, model)
        return True, 'ok'
    except Exception as exc:
        log.warning('submit_card: ошибка запроса к фотоген API: %s', exc)
        return False, f'Ошибка отправки в фотоген: {exc}'
