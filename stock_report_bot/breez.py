"""Опт-цена (base) Бриза напрямую из Бриз API.

Бриз отдаёт опт/закупку (`base`) только в своём stock-эндпоинте `/leftoversnew/`;
в БД сайта у Бриза лежит розница. Поэтому сервис спрашивает Бриз сам — сайт при
этом НЕ трогается. Rusklimat/Daichi опт берут из БД (там он есть), для них этот
модуль не нужен.
"""
import logging

import requests

from stock_report_bot.config import BREEZ_AUTH_HEADER, BREEZ_BASE_URL

logger = logging.getLogger(__name__)


def _extract_base(price):
    """Из `price: [{base, base_currency}, {ric, ric_currency}]` достаём base."""
    if isinstance(price, list):
        for p in price:
            if isinstance(p, dict) and p.get('base') is not None:
                return p['base']
    return None


def _parse_leftovers(data):
    """Из ответа `/leftoversnew/` строит словарь {nc_code: base}. Чистая функция
    (без сети) — поэтому тестируется напрямую.

    Форматы (как `_iter_leftoversnew` у сайта):
    - Format 1: `{"НС": {...запись...}}` — ключ = NC (в самой записи поля `nc`
      может не быть) — текущий живой формат;
    - Format 2: `[{"НС": {...запись...}}]` — список однолючевых dict (Бриз может
      включить позже);
    - плоский: `[{"nc"/"nc_code"/"id": ..., "price": ...}]`.
    """
    if isinstance(data, dict):
        entries = [(key, val) for key, val in data.items() if isinstance(val, dict)]
    elif isinstance(data, list):
        entries = []
        for e in data:
            if not isinstance(e, dict):
                continue
            if len(e) == 1 and isinstance(next(iter(e.values())), dict):
                entries.append(next(iter(e.items())))   # (NC, запись) — Format 2
            else:
                entries.append((None, e))                # плоский — nc внутри записи
    else:
        return {}

    result = {}
    for key, entry in entries:
        nc = entry.get('nc') or entry.get('nc_code') or entry.get('id') or key
        base = _extract_base(entry.get('price'))
        if nc and base is not None:
            result[str(nc)] = base
    return result


def fetch_breez_base_by_nc():
    """Словарь {nc_code: base_price} из Бриз `/leftoversnew/`.

    Пусто, если ключ не задан или запрос упал — тогда отчёт по Бризу мягко
    откатывается на цену из БД (см. report._price_for). Сайт не задействован.
    """
    if not BREEZ_AUTH_HEADER or 'REPLACE' in BREEZ_AUTH_HEADER:
        logger.warning('breez: ключ не задан — опт Бриза будет из БД (розница)')
        return {}

    url = BREEZ_BASE_URL.rstrip('/') + '/leftoversnew/'
    try:
        resp = requests.get(
            url,
            headers={'Authorization': BREEZ_AUTH_HEADER, 'Accept': 'application/json'},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.error('breez base fetch failed: %s', exc)
        return {}

    result = _parse_leftovers(data)
    logger.info('breez: получено опт-цен (base) по %d позициям', len(result))
    return result
