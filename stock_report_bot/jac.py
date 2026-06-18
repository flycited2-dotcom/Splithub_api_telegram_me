"""4-й поставщик JAC из файла скрапера (у b2b-jac.com нет API).

Данные готовит отдельный проект `osatakti_mdv_b2b` (скрапит b2b-jac.com и пишет
`jac_stock_latest.json`). Здесь применяем ТЕ ЖЕ правила отчёта, что и для остальных
(см. `db.py`):
  - только Крым (колонка «Крым» бланка JAC), количество = крымский остаток;
  - только кондиционеры: «Холод, кВт» > 0 (у аксессуаров пусто);
  - без мультисплита и аксессуаров (категории) и денилист названий.

Опт-цена JAC = «Ваша цена» портала (дилерская) — она лежит в поле `price`
скрапера; в отчёте `report._price_for` для source='jac' берёт `price_wholesale`.

Файл отсутствует/пустой/битый → 0 строк (отчёт собирается по 3 поставщикам, как
раньше) — JAC никогда не должен ронять суточный отчёт.
"""
import json
import logging
import re

logger = logging.getLogger('stock_report_bot.jac')


def _configured_path():
    """Путь к файлу JAC из config/.env. Импорт config ленивый, чтобы юнит-тесты
    map_rows/load_jac_rows(path) не требовали настроек БД."""
    try:
        from stock_report_bot.config import JAC_STOCK_JSON
        return JAC_STOCK_JSON
    except Exception:
        return ''

JAC_SOURCE = 'jac'

# Категории JAC, попадающие в отчёт (кондиционеры нужных типов). Мультисплит и
# Аксессуары не включаем — как и в db.REPORT_CATEGORY_IDS / EXCLUDE_TITLE_PATTERNS.
INCLUDE_CATEGORIES = {
    'Бытовые сплит-системы',
    'Полупромышленные системы',
    'Мобильные',
    'Мобильные кондиционеры',
}

# Денилист названий — зеркало db.EXCLUDE_TITLE_PATTERNS (мультисплит + аксессуары
# с ошибочной мощностью).
DENY_TITLE = ('мульти', 'виброопор', 'охладитель воздуха', 'зимний комплект', 'комплект зимний')

_BTU_KEYS = ('Холод, кВт', 'Холод кВт', 'Холод')
_CRIMEA_KEYS = ('Крым',)
_MORE_RE = re.compile(r'больше\s*(\d+)', re.IGNORECASE)


def _num(val):
    """'2.2' / '12 360' / '1 234,5' -> float; иначе None."""
    if val is None:
        return None
    s = str(val).replace('\xa0', ' ').replace(' ', ' ').replace(' ', '')
    m = re.search(r'-?\d+(?:[.,]\d+)?', s)
    return float(m.group(0).replace(',', '.')) if m else None


def _attr(attrs, keys):
    for k in keys:
        if k in attrs and str(attrs[k]).strip() != '':
            return attrs[k]
    return None


def _crimea_qty(attrs):
    """Крымский остаток: число; «Больше 100» -> 100; пусто/0 -> 0."""
    raw = _attr(attrs, _CRIMEA_KEYS)
    if raw is None:
        return 0
    mm = _MORE_RE.search(str(raw))
    if mm:
        return int(mm.group(1))
    n = _num(raw)
    return int(n) if n is not None else 0


def _btu(attrs):
    n = _num(_attr(attrs, _BTU_KEYS))
    return n if n is not None else 0.0


def _denied(title):
    t = (title or '').lower()
    return any(d in t for d in DENY_TITLE)


def map_rows(data):
    """Список товаров скрапера -> строки отчёта (та же форма, что db.fetch_stock_rows)."""
    rows = []
    for p in data:
        cat = (p.get('category') or '').strip()
        if cat not in INCLUDE_CATEGORIES:
            continue
        attrs = p.get('attributes') or {}
        if _btu(attrs) <= 0:               # не кондиционер
            continue
        title = (p.get('article') or p.get('name') or '').strip()
        if _denied(title):
            continue
        qty = _crimea_qty(attrs)
        if qty <= 0:                       # нет крымского остатка
            continue
        rows.append({
            'source': JAC_SOURCE,
            'nc_code': None,
            'brand': (p.get('brand') or '').strip(),
            'title': title,
            'series': (p.get('series') or '').strip(),   # из пути категории
            'price_wholesale': p.get('price'),   # «Ваша цена» = опт
            'price_base': None,
            'crimea_qty': qty,
            'image_url': None,
        })
    return rows


def load_jac_rows(path=None):
    """Читает jac_stock_latest.json и возвращает отфильтрованные строки JAC.
    Любая проблема с файлом -> [] (отчёт не падает)."""
    path = path if path is not None else _configured_path()
    if not path:
        return []
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning('JAC: остатки недоступны (%s) — JAC пропущен', e)
        return []
    rows = map_rows(data)
    logger.info('JAC: %d позиций в наличии (Крым)', len(rows))
    return rows
