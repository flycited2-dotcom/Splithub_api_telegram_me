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

def size_from_btu(btu):
    """Типоразмер (число «семёрка/девятка/…») из `btu_calc`.

    `btu_calc` сайта — УЖЕ готовый номинал в kBTU (7/9/10/12/13/14/16/18/20/22/24/25/26/
    27/30/32/35/36/40/42/48/60): сайт сам округляет к стандарту (apps/catalog/btu.py).
    Поэтому берём значение КАК ЕСТЬ, без повторного снапа (иначе 10→9, 14→12 и дубли).
    Подстраховка: если прилетело в полных BTU (9000) — делим на 1000. None — если нет/мусор."""
    try:
        v = float(btu)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    if v > 200:           # на всякий случай: значение в полных BTU → в kBTU
        v = v / 1000.0
    n = int(round(v))
    return n if 1 <= n <= 200 else None


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
    # Дедуп по типоразмеру: одна строка на размер (мин. цена), чтобы не было «7, 7, 12».
    by_size = {}                 # size -> мин. цена с наценкой
    extras = []                  # (label, price) — позиции без распознанного размера
    for r in positions:
        price = marked_price(_price_for(r, breez_base), pct)
        if price is None:
            continue
        size = size_from_btu(r.get('btu_calc'))
        if size is None:
            extras.append((_fallback_label(r, brand), price))
        elif size not in by_size or price < by_size[size]:
            by_size[size] = price
    rows = [(s, str(s), p) for s, p in by_size.items()]
    rows += [(10 ** 9, lbl, p) for lbl, p in extras]
    rows.sort(key=lambda t: (t[0], t[1]))

    head2 = short_series(series) + (' · инвертор' if inverter else '')
    body = [f'❄️ {(brand or "").strip()}', head2, '──────────────────']
    body += [f'{label} — {_fmt_price(price)}' for _, label, price in rows]
    return f'<blockquote>{html.escape(chr(10).join(body))}</blockquote>'
