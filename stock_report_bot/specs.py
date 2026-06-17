"""Характеристики (ТТХ) товаров JAC из файла скрапера (jac_specs_latest.json).

Готовит КОМПАКТНУЮ строку ключевых характеристик под каждую модель — для
клиентского сообщения с наценкой (мощность · хладагент · тип). Полные ТТХ
доступны в самом файле. Файла нет/пусто → пустые строки (всё работает без ТТХ).

Формат файла (готовит проект osatakti_mdv_b2b, команда `specs`):
  { "<артикул>": {"brand": .., "series": .., "characteristics": {..}}, ... }
"""
import json
import logging

logger = logging.getLogger('stock_report_bot.specs')


def _configured_path():
    try:
        from stock_report_bot.config import JAC_SPECS_JSON
        return JAC_SPECS_JSON
    except Exception:
        return ''


def load_specs(path=None):
    """Возвращает {артикул: {brand, series, characteristics}}; проблема → {}."""
    path = path if path is not None else _configured_path()
    if not path:
        return {}
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning('ТТХ недоступны (%s) — без характеристик', e)
        return {}


# Ключевые поля для компактной строки (в порядке вывода).
_KW_KEYS = ('Холод, кВт', 'Холод кВт')
_REFR_KEYS = ('Тип хладагента',)
_CTRL_KEYS = ('Тип управления компрессором',)
_AREA_KEYS = ('Рекомендуемая площадь помещения, м2', 'Площадь помещения, м2',
              'Обслуживаемая площадь, м2')


def _first(ch, keys):
    for k in keys:
        v = ch.get(k)
        if v not in (None, ''):
            return str(v).strip()
    return ''


def compact_spec(characteristics: dict) -> str:
    """'❄ 7.1 кВт · R410A · on-off' из словаря характеристик; '' если пусто."""
    if not characteristics:
        return ''
    parts = []
    kw = _first(characteristics, _KW_KEYS)
    if kw:
        parts.append(f'❄ {kw} кВт')
    area = _first(characteristics, _AREA_KEYS)
    if area:
        parts.append(f'~{area} м²')
    refr = _first(characteristics, _REFR_KEYS)
    if refr:
        parts.append(refr)
    ctrl = _first(characteristics, _CTRL_KEYS)
    if ctrl:
        parts.append(ctrl)
    return ' · '.join(parts)


def spec_lines_for(specs: dict, articles) -> dict:
    """{артикул: компактная_строка} для заданных артикулов (только непустые)."""
    out = {}
    for art in articles:
        rec = specs.get(art)
        if rec:
            line = compact_spec(rec.get('characteristics') or {})
            if line:
                out[art] = line
    return out
