"""Интерактивное меню с наценкой. ЧИСТЫЕ функции (без БД и сети) — тестируются
напрямую, как report.py.

Иерархия: Поставщик → Бренд → Серия → % наценки (1–10) → список позиций серии
в наличии с ценой-с-наценкой и количеством. Опт-цена и формат строки берутся из
report (единый источник правды). Серия: поле `series` (Бриз/Daichi), либо парсинг
из `title` (Русклимат, где `series` пуст).

callback_data компактный, без внешнего стора (переживает рестарт бота): источник —
1 символ (r/d/b), бренд и серия — ИНДЕКСЫ в детерминированно отсортированных списках,
пере-выводимых из снапшота остатков при каждом нажатии. Действие — первое поле.
"""
import html
import re

from stock_report_bot.report import (
    SUPPLIER_EMOJI, _chunk_lines, _fmt_price, _price_for, _qty_for, _supplier_label,
)

# Порядок поставщиков в меню и их 1-символьные коды для callback_data.
SUPPLIER_ORDER = ['breeze', 'rusklimat', 'daichi', 'jac']
SRC_CODE = {'breeze': 'b', 'rusklimat': 'r', 'daichi': 'd', 'jac': 'j'}
CODE_SRC = {v: k for k, v in SRC_CODE.items()}

MARKUP_PCTS = list(range(1, 11))   # наценка к опту: +1..+10 %
DISCOUNT_PCTS = [-1, -3, -5, -7]   # регрессивная (скидка от опта): −1/−3/−5/−7 %
PAGE_SIZE = 8                      # кнопок-пунктов на страницу (пагинация брендов/серий)

EMPTY_SERIES = '(без серии)'
# Префиксы типа товара в начале title (Русклимат) — срезаем перед поиском серии.
_TYPE_PREFIXES = (
    'Сплит-система инверторного типа ', 'Сплит-система ',
    'Кондиционер мобильный ', 'Комплект ',
)


# ── серия позиции ──────────────────────────────────────────────────────────
def series_of(row):
    """Серия (модельная линейка) позиции. Бриз/Daichi — поле `series`. Русклимат —
    парсинг из title: слова между брендом/типом и артикулом (первым токеном с цифрой),
    напр. «Ballu Olympio Edge BSO-07HN8…» → «Olympio Edge». Пусто → «(без серии)»."""
    s = (row.get('series') or '').strip()
    if s:
        return s
    title = (row.get('title') or '').strip()
    for p in _TYPE_PREFIXES:
        if title.startswith(p):
            title = title[len(p):]
            break
    brand = (row.get('brand') or '').strip()
    if brand and title.lower().startswith(brand.lower() + ' '):
        title = title[len(brand) + 1:]
    words = []
    for w in title.split():
        if any(ch.isdigit() for ch in w):
            break
        words.append(w)
    return ' '.join(words).strip() or EMPTY_SERIES


# ── срезы иерархии (детерминированно отсортированы) ─────────────────────────
def suppliers_present(rows):
    """Поставщики, у которых есть позиции в наличии — в порядке SUPPLIER_ORDER."""
    have = {r.get('source') for r in rows if _qty_for(r) > 0}
    return [s for s in SUPPLIER_ORDER if s in have]


def brands_for(rows, source):
    names = {(r.get('brand') or '').strip() for r in rows
             if r.get('source') == source and _qty_for(r) > 0}
    return sorted(n for n in names if n)


def series_for(rows, source, brand):
    names = {series_of(r) for r in rows
             if r.get('source') == source and (r.get('brand') or '').strip() == brand
             and _qty_for(r) > 0}
    return sorted(names)


def positions_for(rows, source, brand, series):
    items = [r for r in rows
             if r.get('source') == source and (r.get('brand') or '').strip() == brand
             and series_of(r) == series and _qty_for(r) > 0]
    return sorted(items, key=lambda r: (r.get('title') or ''))


def series_image(rows, source, brand, series):
    """URL фото для серии — первое непустое `image_url` среди позиций (order=0,
    обычно внутренний блок). None, если ни у одной позиции картинки нет."""
    for r in positions_for(rows, source, brand, series):
        url = (r.get('image_url') or '').strip()
        if url:
            return url
    return None


# ── наценка ────────────────────────────────────────────────────────────────
def marked_price(opt, pct):
    """Опт + наценка, округление ВВЕРХ до ближайшего числа, оканчивающегося на …90.
    Пример: 26 404 × 1.05 = 27 724.2 → 27 790. None → None."""
    if opt is None:
        return None
    raw = float(opt) * (1 + pct / 100.0)
    base = (int(raw) // 100) * 100
    return base + 90 if raw <= base + 90 else base + 190


# ── callback_data кодек ────────────────────────────────────────────────────
def cb_pack(*parts):
    return '|'.join(str(p) for p in parts)


def cb_unpack(data):
    return (data or '').split('|')


# ── клавиатуры (reply_markup dict для Telegram) ────────────────────────────
def _kb(rows_of_buttons):
    return {'inline_keyboard': rows_of_buttons}


def _btn(text, data):
    return {'text': text, 'callback_data': data}


def _paginate(items_buttons, page, nav_back_data, page_cb):
    """items_buttons: список (text, callback). Возвращает inline_keyboard: по 1 кнопке
    в ряд, срез страницы, ряд навигации ◀/▶ при необходимости, кнопка «⬅ Назад».
    page_cb(p) -> callback_data для перехода на страницу p."""
    total = len(items_buttons)
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    chunk = items_buttons[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    kb = [[_btn(t, d)] for t, d in chunk]
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(_btn('◀', page_cb(page - 1)))
        nav.append(_btn(f'{page + 1}/{pages}', 'noop'))
        if page < pages - 1:
            nav.append(_btn('▶', page_cb(page + 1)))
        kb.append(nav)
    if nav_back_data is not None:
        kb.append([_btn('⬅ Назад', nav_back_data)])
    return _kb(kb)


def kb_suppliers(rows):
    btns = []
    for src in suppliers_present(rows):
        emoji = SUPPLIER_EMOJI.get(src, '▫️')
        btns.append([_btn(f'{emoji} {_supplier_label(src)}', cb_pack('b', SRC_CODE[src], 0))])
    return _kb(btns)


def kb_brands(rows, source, page=0):
    code = SRC_CODE[source]
    brands = brands_for(rows, source)
    items = [(b, cb_pack('s', code, i, 0)) for i, b in enumerate(brands)]
    return _paginate(items, page, nav_back_data=cb_pack('m'),
                     page_cb=lambda p: cb_pack('b', code, p))


def kb_series(rows, source, brand_idx, page=0):
    code = SRC_CODE[source]
    brands = brands_for(rows, source)
    brand = brands[brand_idx]
    series = series_for(rows, source, brand)
    items = [(s, cb_pack('k', code, brand_idx, i)) for i, s in enumerate(series)]
    return _paginate(items, page, nav_back_data=cb_pack('b', code, 0),
                     page_cb=lambda p: cb_pack('s', code, brand_idx, p))


def _pct_btn(code, brand_idx, series_idx, p):
    sign = '+' if p > 0 else '−'   # callback хранит знак ASCII ('-5'), отображаем '−5%'
    return _btn(f'{sign}{abs(p)}%', cb_pack('g', code, brand_idx, series_idx, p))


def kb_markup(source, brand_idx, series_idx):
    code = SRC_CODE[source]
    disc = [_pct_btn(code, brand_idx, series_idx, p) for p in DISCOUNT_PCTS]      # −1/−3/−5/−7
    row1 = [_pct_btn(code, brand_idx, series_idx, p) for p in MARKUP_PCTS[:5]]    # +1..+5
    row2 = [_pct_btn(code, brand_idx, series_idx, p) for p in MARKUP_PCTS[5:]]    # +6..+10
    back = [_btn('⬅ Назад', cb_pack('s', code, brand_idx, 0))]
    return _kb([disc, row1, row2, back])


# ── текст уровней навигации ────────────────────────────────────────────────
def text_suppliers():
    return '📦 <b>Остатки с наценкой</b>\nВыберите поставщика:'


def text_brands(source):
    emoji = SUPPLIER_EMOJI.get(source, '▫️')
    return f'{emoji} <b>{html.escape(_supplier_label(source))}</b>\nВыберите бренд:'


def text_series(source, brand):
    return f'<b>{html.escape(brand)}</b>\nВыберите серию:'


def text_markup(source, brand, series):
    return (f'<b>{html.escape(brand)}</b> · {html.escape(series)}\n'
            f'Наценка (+) или скидка (−) к опт-цене:')


# ── итоговый список с наценкой ─────────────────────────────────────────────
def build_priced_message(rows, source, brand, series, pct, breez_base=None, spec_lines=None):
    """Текст сообщения со списком позиций серии в наличии: опт × (1+pct%) → …90.

    Шапка — только 2 эмодзи (🏷 + квадрат поставщика): сообщение готово к пересылке
    клиенту, поставщик и величина наценки/скидки в нём НЕ раскрываются.
    spec_lines: {артикул: компактные ТТХ} — подпись под позицией (для JAC)."""
    spec_lines = spec_lines or {}
    emoji = SUPPLIER_EMOJI.get(source, '▫️')
    head = f'🏷 {emoji}'
    lines = [head, '']
    items = positions_for(rows, source, brand, series)
    for r in items:
        opt = _price_for(r, breez_base)
        price = marked_price(opt, pct)
        b = html.escape((r.get('brand') or '').strip())
        ser = html.escape((r.get('series') or '').strip())
        name = html.escape(r.get('title') or '')
        head_b = f'<b>{b}</b> ' if b else ''
        ser_p = f'{ser} · ' if ser and r.get('source') == 'jac' else ''   # серия только у JAC
        lines.append(f'• {head_b}{ser_p}{name} — {_fmt_price(price)} — {_qty_for(r)} шт.')
        spec = spec_lines.get(r.get('title') or '')
        if spec:
            lines.append(f'   <i>{html.escape(spec)}</i>')
    if not items:
        lines.append('Нет позиций в наличии.')
    return _chunk_lines(lines, 3900)
