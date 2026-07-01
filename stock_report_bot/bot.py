"""Интерактивный бот меню с наценкой (long-polling).

Запуск: `python -m stock_report_bot.bot`. Постоянный процесс (systemd), рядом с
суточным cron-отчётом. Слушает кнопки/команды ТОЛЬКО владельца, строит меню
Поставщик→Бренд→Серия→% и присылает список позиций с ценой-с-наценкой.

Сеть — через stock_report_bot.telegram (тот же charset/Session/ретраи + IPv6-форсинг
серверной обёртки). Данные — read-only из БД сайта (fetch_stock_rows), опт Бриза — из
Бриз API (кэш с TTL).
"""
import html
import logging
import time

import psycopg2

from stock_report_bot.config import TELEGRAM_OWNER_CHAT_ID
from stock_report_bot.breez import fetch_breez_base_by_nc, fetch_breez_utp_by_nc
from stock_report_bot.db import fetch_stock_rows, fetch_tech_values
from stock_report_bot.jac import load_jac_rows
from stock_report_bot.jac_utp import load_utp, utp_for, build_utp_block
from stock_report_bot import menu, specs, fotogen_bridge, channel_caption, jac_photos
from stock_report_bot.telegram import (
    answer_callback_query, edit_message_text, get_updates, send_message, send_photo,
    set_my_commands,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('stock_report_bot.bot')

_ROWS_TTL = 120      # снапшот остатков
_BREEZ_TTL = 300     # опт Бриза из API
_UTP_TTL = 1800      # УТП Бриза из API (меняется редко — держим дольше)
_JAC_UTP_TTL = 3600  # УТП JAC из файла скрапера (меняются редко)
_cache = {'rows': (0, None), 'breez': (0, None), 'utp': (0, None), 'jac_utp': (0, None),
          'jac_photos': (0, None)}


def _rows():
    ts, val = _cache['rows']
    if val is None or time.time() - ts > _ROWS_TTL:
        val = fetch_stock_rows() + load_jac_rows()   # + 4-й поставщик JAC из файла
        _cache['rows'] = (time.time(), val)
    return val


def _breez_base():
    ts, val = _cache['breez']
    if val is None or time.time() - ts > _BREEZ_TTL:
        val = fetch_breez_base_by_nc()
        _cache['breez'] = (time.time(), val)
    return val


def _breez_utp():
    ts, val = _cache['utp']
    if val is None or time.time() - ts > _UTP_TTL:
        val = fetch_breez_utp_by_nc()
        _cache['utp'] = (time.time(), val)
    return val


def _jac_utp():
    ts, val = _cache['jac_utp']
    if val is None or time.time() - ts > _JAC_UTP_TTL:
        val = load_utp()
        _cache['jac_utp'] = (time.time(), val)
    return val


def _jac_photos():
    ts, val = _cache['jac_photos']
    if val is None or time.time() - ts > _JAC_UTP_TTL:
        val = jac_photos.load_photos()
        _cache['jac_photos'] = (time.time(), val)
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
    Картинки нет / Telegram не смог её забрать → откат на только текст.
    Характеристики (если выбраны) уже вклеены в chunks — отдельным сообщением НЕ шлём."""
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
        elif action == 'g':                       # g|code|bidx|sidx|pct — выбор: с/без характеристик
            code, bidx, sidx, pct = parts[1], int(parts[2]), int(parts[3]), int(parts[4])
            source, brand, series = _resolve(rows, code, bidx, sidx)
            edit_message_text(chat_id, message_id, menu.text_specs_choice(brand, series, pct),
                              menu.kb_specs_choice(source, bidx, sidx, pct))
        elif action in ('gp', 'gs'):              # отправка итога БЕЗ (gp) / С (gs) характеристиками
            code, bidx, sidx, pct = parts[1], int(parts[2]), int(parts[3]), int(parts[4])
            source, brand, series = _resolve(rows, code, bidx, sidx)
            breez_base = _breez_base() if source == 'breeze' else None
            extra_block = None
            if action == 'gs':
                if source == 'jac':
                    # JAC нет в БД сайта — блок «птички»-УТП серии из файла скрапера.
                    extra_block = build_utp_block(brand, menu.short_series(series),
                                                  utp_for(_jac_utp(), brand, series))
                else:
                    positions = menu.positions_for(rows, source, brand, series)
                    nc_codes = [r.get('nc_code') for r in positions if r.get('nc_code')]
                    titles = [r.get('title') for r in positions]
                    utp_raw = None
                    if source == 'breeze':
                        utp_map = _breez_utp()
                        utp_raw = next((utp_map.get(nc) for nc in nc_codes if utp_map.get(nc)), None)
                    extra_block = specs.build_specs_block(
                        fetch_tech_values(nc_codes), brand, menu.short_series(series),
                        source, utp_raw, titles)
            chunks = menu.build_priced_message(rows, source, brand, series, pct, breez_base,
                                               extra_block=extra_block)
            image_url = menu.series_image(rows, source, brand, series)
            _send_result(chat_id, chunks, image_url)
        elif action == 'c':                       # c|code|bidx|sidx|pct — карточка в фотоген-агент
            code, bidx, sidx, pct = parts[1], int(parts[2]), int(parts[3]), int(parts[4])
            source, brand, series = _resolve(rows, code, bidx, sidx)
            positions = menu.positions_for(rows, source, brand, series)
            short = menu.short_series(series)
            breez_base = _breez_base() if source == 'breeze' else None
            if source == 'jac':
                # JAC: specs = птички-УТП серии, фото — из jac_photos (URL вендора или
                # локальный файл THAICON). В БД сайта JAC нет, поэтому отдельная ветка.
                spec_lines = utp_for(_jac_utp(), brand, series)
                photo_url = jac_photos.resolve_photo(
                    jac_photos.photo_ref(_jac_photos(), brand, series))
            else:
                nc_codes = [r.get('nc_code') for r in positions if r.get('nc_code')]
                titles = [r.get('title') for r in positions]
                utp_raw = None
                if source == 'breeze':
                    utp_map = _breez_utp()
                    utp_raw = next((utp_map.get(nc) for nc in nc_codes if utp_map.get(nc)), None)
                spec_lines = specs.build_specs_for_card(
                    fetch_tech_values(nc_codes), brand, menu.short_series(series),
                    source, utp_raw=utp_raw, titles=titles)
                photo_url = menu.series_image(rows, source, brand, series)
            # Подпись-прайс для канала: цены по выбранной наценке pct (см. channel_caption).
            inverter = (any('нвертор' in (l or '').lower() for l in spec_lines)
                        or 'нвертор' in (series or '').lower())
            caption = channel_caption.build_channel_caption(
                positions, pct, brand, series, source,
                breez_base=breez_base, inverter=inverter)
            if not photo_url:
                edit_message_text(chat_id, message_id,
                    '⚠️ Фото товара не найдено в базе. Загрузите фото вручную в фотоген-боте.',
                    None)
            else:
                ok, err = fotogen_bridge.submit_card(
                    photo_url=photo_url, brand=brand, model=short,
                    specs_lines=spec_lines, chat_id=chat_id, caption=caption)
                if ok:
                    edit_message_text(chat_id, message_id,
                        f'⏳ <b>{html.escape(brand)} {html.escape(short)}</b>\n'
                        'Карточка отправлена в фотоген-агент. Готовая карточка придёт '
                        'через ~2 мин в чат фотоген-бота с кнопками подтверждения.',
                        None)
                else:
                    edit_message_text(chat_id, message_id,
                        f'❌ Не удалось отправить задачу: {html.escape(err)}', None)
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
    if text == '/start':
        # один раз ставим постоянную кнопку «📋 Меню» — дальше владелец просто тапает её
        send_message(chat_id, 'Готово 👇 Жмите «📋 Меню» в любой момент.', menu.MAIN_REPLY_KB)
        send_message(chat_id, menu.text_suppliers(), menu.kb_suppliers(_rows()))
    elif text in ('/menu', menu.MENU_BUTTON_TEXT):
        send_message(chat_id, menu.text_suppliers(), menu.kb_suppliers(_rows()))


def run():
    if not TELEGRAM_OWNER_CHAT_ID:
        logger.error('TELEGRAM_OWNER_CHAT_ID не задан — некого слушать')
        return 1
    try:
        set_my_commands([{'command': 'menu', 'description': '📋 Остатки с наценкой'}])
    except Exception as exc:
        logger.warning('setMyCommands не удалось: %s', exc)
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
            except psycopg2.OperationalError:
                # БД сайта недоступна — обычно у контейнера oasis-db-1 сменился IP после
                # пересоздания стека сайта, а долгоживущий бот держит старый IP (в отличие
                # от суточного отчёта, который резолвит IP каждый запуск). Выходим: systemd
                # (Restart=always) перезапустит, run_bot.sh пере-резолвит текущий IP — самолечение.
                logger.error('БД недоступна — выход для авто-рестарта (пере-резолв IP БД)')
                raise SystemExit(1)
            except Exception as exc:
                logger.exception('ошибка обработки update: %s', exc)


if __name__ == '__main__':
    raise SystemExit(run())
