"""Подпись-прайс для публикации карточки серии в Telegram-канал. ЧИСТЫЕ функции
(без БД и сети) — тестируются напрямую, как report/menu/specs.

Подпись собирается в Stock Bot (только у него есть цены) и передаётся фотоген-боту,
который постит её в канал по кнопке «Опубликовать». Формат — цитата (<blockquote>):
бренд, серия (+ «инвертор»), затем строки «типоразмер — цена с наценкой» по возрастанию.
Поставщик и величина наценки НЕ раскрываются — готово к публикации.
"""
import html

from stock_report_bot.report import _fmt_price, _price_for
from stock_report_bot.menu import marked_price, short_series

# Стандартные типоразмеры кондиционеров (тысячи BTU): бытовые 7/9/12/18/24,
# полупромышленные 30/36/42/48/60. Номер в подписи — ближайший из них.
_STD_SIZES = [7, 9, 12, 18, 24, 30, 36, 42, 48, 60]


def size_from_btu(btu):
    """Типоразмер (число «семёрка/девятка/…») из btu_calc. Нормализуем к тысячам BTU
    (значение > 1000 — это BTU, делим на 1000; иначе уже в тысячах) и привязываем к
    ближайшему стандартному. None — если значения нет или привязка недостоверна
    (ближайший стандарт дальше 20%): тогда caller показывает имя модели."""
    try:
        v = float(btu)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    k = v / 1000.0 if v > 1000 else v
    nearest = min(_STD_SIZES, key=lambda s: abs(s - k))
    if abs(nearest - k) > nearest * 0.2:
        return None
    return nearest


def _fallback_label(row, brand):
    """Короткое имя модели — когда типоразмер из btu не вывести."""
    t = (row.get('title') or '').strip()
    b = (brand or '').strip()
    if b and t.lower().startswith(b.lower() + ' '):
        t = t[len(b) + 1:].strip()
    return t[:24].strip() or '—'


def build_channel_caption(positions, pct, brand, series, source,
                          breez_base=None, inverter=False):
    """HTML-подпись-цитата серии для канала.

    positions: позиции серии в наличии (dict с btu_calc/title/source/nc_code/цены).
    pct:       выбранная наценка; цена строки = marked_price(опт, pct).
    inverter:  добавить «· инвертор» в заголовок.
    Возвращает строку <blockquote>…</blockquote> (≤ 1024 символов для серии).
    """
    rows = []
    for r in positions:
        price = marked_price(_price_for(r, breez_base), pct)
        if price is None:
            continue
        size = size_from_btu(r.get('btu_calc'))
        if size is not None:
            rows.append((size, str(size), price))
        else:
            rows.append((10 ** 9, _fallback_label(r, brand), price))
    rows.sort(key=lambda t: (t[0], t[1]))

    head2 = short_series(series) + (' · инвертор' if inverter else '')
    body = [f'❄️ {(brand or "").strip()}', head2, '──────────────────']
    body += [f'{label} — {_fmt_price(price)}' for _, label, price in rows]
    return f'<blockquote>{html.escape(chr(10).join(body))}</blockquote>'
