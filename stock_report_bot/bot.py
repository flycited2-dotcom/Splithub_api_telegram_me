"""Интерактивный бот меню с наценкой (long-polling).

Запуск: `python -m stock_report_bot.bot`. Постоянный процесс (systemd), рядом с
суточным cron-отчётом. Слушает кнопки/команды ТОЛЬКО владельца, строит меню
Поставщик→Бренд→Серия→% и присылает список позиций с ценой-с-наценкой.

Сеть — через stock_report_bot.telegram (тот же charset/Session/ретраи + IPv6-форсинг
серверной обёртки). Данные — read-only из БД сайта (fetch_stock_rows), опт Бриза — из
Бриз API (кэш с TTL).
"""
import logging
import time

from stock_report_bot.config import TELEGRAM_OWNER_CHAT_ID
from stock_report_bot.breez import fetch_breez_base_by_nc
from stock_report_bot.db import fetch_stock_rows
from stock_report_bot import menu
from stock_report_bot.telegram import (
    answer_callback_query, edit_message_text, get_updates, send_message, send_photo,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('stock_report_bot.bot')

_ROWS_TTL = 120      # снапшот остатков
_BREEZ_TTL = 300     # опт Бриза из API
_cache = {'rows': (0, None), 'breez': (0, None)}


def _rows():
    ts, val = _cache['rows']
    if val is None or time.time() - ts > _ROWS_TTL:
        val = fetch_stock_rows()
        _cache['rows'] = (time.time(), val)
    return val


def _breez_base():
    ts, val = _cache['breez']
    if val is None or time.time() - ts > _BREEZ_TTL:
        val = fetch_breez_base_by_nc()
        _cache['breez'] = (time.time(), val)
    return val


def _is_owner(tg_id):
    return TELEGRAM_OWNER_CHAT_ID and str(tg_id) == str(TELEGRAM_OWNER_CHAT_ID)


def _resolve(rows, code, brand_idx=None, series_idx=None):
    """code→source, индекс бренда→имя, индекс серии→имя. Бросает IndexError/KeyError,
    если каталог изменился между нажатиями (ловим выше → просим /menu)."""
    source = menu.CODE_SRC[code]
    brand = series = None
    if brand_idx is not None:
        brand = menu.brands_for(rows, source)[int(brand_idx)]
    if series_idx is not None:
        series = menu.series_for(rows, source, brand)[int(series_idx)]
    return source, brand, series


def _send_result(chat_id, chunks, image_url):
    """Итог: фото внутреннего блока + список-подпись снизу (для пересылки клиенту).
    Подпись Telegram ≤ 1024 — если первый кусок влезает, шлём его подписью к фото,
    остальное (редко) текстом; если длинный — фото с мин. подписью + список текстом.
    Картинки нет / Telegram не смог её забрать → откат на только текст."""
    if image_url:
        cap = chunks[0] if len(chunks[0]) <= 1024 else '🏷'
        if send_photo(chat_id, image_url, caption=cap):
            rest = chunks[1:] if cap == chunks[0] else chunks
            for chunk in rest:
                send_message(chat_id, chunk)
            return
    for chunk in chunks:
        send_message(chat_id, chunk)


def _handle_callback(cb):
    cq_id = cb['id']
    from_id = cb.get('from', {}).get('id')
    msg = cb.get('message') or {}
    chat_id = msg.get('chat', {}).get('id')
    message_id = msg.get('message_id')
    data = cb.get('data') or ''
    if not _is_owner(from_id):
        answer_callback_query(cq_id)
        return
    parts = menu.cb_unpack(data)
    action = parts[0] if parts else ''
    rows = _rows()
    try:
        if action == 'noop':
            pass
        elif action == 'm':
            edit_message_text(chat_id, message_id, menu.text_suppliers(), menu.kb_suppliers(rows))
        elif action == 'b':                       # b|code|page
            code, page = parts[1], int(parts[2])
            source, _, _ = _resolve(rows, code)
            edit_message_text(chat_id, message_id, menu.text_brands(source),
                              menu.kb_brands(rows, source, page))
        elif action == 's':                       # s|code|bidx|page
            code, bidx, page = parts[1], int(parts[2]), int(parts[3])
            source, brand, _ = _resolve(rows, code, bidx)
            edit_message_text(chat_id, message_id, menu.text_series(source, brand),
                              menu.kb_series(rows, source, bidx, page))
        elif action == 'k':                       # k|code|bidx|sidx
            code, bidx, sidx = parts[1], int(parts[2]), int(parts[3])
            source, brand, series = _resolve(rows, code, bidx, sidx)
            edit_message_text(chat_id, message_id, menu.text_markup(source, brand, series),
                              menu.kb_markup(source, bidx, sidx))
        elif action == 'g':                       # g|code|bidx|sidx|pct
            code, bidx, sidx, pct = parts[1], int(parts[2]), int(parts[3]), int(parts[4])
            source, brand, series = _resolve(rows, code, bidx, sidx)
            breez_base = _breez_base() if source == 'breeze' else None
            chunks = menu.build_priced_message(rows, source, brand, series, pct, breez_base)
            image_url = menu.series_image(rows, source, brand, series)
            _send_result(chat_id, chunks, image_url)
        answer_callback_query(cq_id)
    except (IndexError, KeyError, ValueError):
        logger.warning('callback устарел/битый: %s', data)
        answer_callback_query(cq_id, 'Список обновился — откройте /menu заново')


def _handle_message(msg):
    from_id = msg.get('from', {}).get('id')
    chat_id = msg.get('chat', {}).get('id')
    text = (msg.get('text') or '').strip()
    if not _is_owner(from_id):
        return
    if text in ('/menu', '/start'):
        send_message(chat_id, menu.text_suppliers(), menu.kb_suppliers(_rows()))


def run():
    if not TELEGRAM_OWNER_CHAT_ID:
        logger.error('TELEGRAM_OWNER_CHAT_ID не задан — некого слушать')
        return 1
    logger.info('menu-bot запущен, long-polling…')
    offset = None
    while True:
        try:
            updates = get_updates(offset)
        except Exception as exc:
            logger.error('get_updates: %s', exc)
            time.sleep(5)
            continue
        for upd in updates:
            offset = upd['update_id'] + 1
            try:
                if 'callback_query' in upd:
                    _handle_callback(upd['callback_query'])
                elif 'message' in upd:
                    _handle_message(upd['message'])
            except Exception as exc:
                logger.exception('ошибка обработки update: %s', exc)


if __name__ == '__main__':
    raise SystemExit(run())
