"""Прямой доступ к Бриз API за тем, чего нет в БД сайта.

1. Опт-цена (`base`): Бриз отдаёт опт/закупку только в `/leftoversnew/`; в БД сайта
   у Бриза лежит розница. Поэтому сервис спрашивает Бриз сам — сайт НЕ трогается.
   Rusklimat/Daichi опт берут из БД (там он есть), для них это не нужно.
2. УТП (`utp`): готовый список преимуществ товара. Синк сайта кладёт в БД только
   tech-характеристики, а поле `utp` из `/products/` теряет (в модели товара его нет).
   Для блока «ключевые особенности» (см. `specs.py`) берём `utp` Бриза тем же ключом.
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


def _parse_products_utp(data):
    """Из ответа `/products/` (dict id→продукт) строит {nc_code: utp_raw}. Чистая
    функция (без сети) — тестируется напрямую. Пустые/без nc позиции пропускаются."""
    result = {}
    if not isinstance(data, dict):
        return result
    for entry in data.values():
        if not isinstance(entry, dict):
            continue
        nc = entry.get('nc')
        utp = entry.get('utp')
        if nc and utp and str(utp).strip():
            result[str(nc)] = str(utp)
    return result


def fetch_breez_utp_by_nc():
    """Словарь {nc_code: utp_raw} из Бриз `/products/` (тот же ключ BREEZE_AUTH_HEADER).

    Пусто, если ключ не задан или запрос упал — тогда блок особенностей по Бризу
    обойдётся без УТП-экстра (технические пункты берутся из БД). Сайт не задействован.
    """
    if not BREEZ_AUTH_HEADER or 'REPLACE' in BREEZ_AUTH_HEADER:
        logger.warning('breez utp: ключ не задан — УТП Бриза недоступно')
        return {}

    url = BREEZ_BASE_URL.rstrip('/') + '/products/'
    try:
        resp = requests.get(
            url,
            headers={'Authorization': BREEZ_AUTH_HEADER, 'Accept': 'application/json'},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.error('breez utp fetch failed: %s', exc)
        return {}

    result = _parse_products_utp(data)
    logger.info('breez: получено utp по %d позициям', len(result))
    return result
