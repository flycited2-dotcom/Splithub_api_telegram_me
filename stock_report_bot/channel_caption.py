"""Подпись-прайс для публикации карточки серии в Telegram-канал. ЧИСТЫЕ функции
(без БД и сети) — тестируются напрямую, как report/menu/specs.

Подпись собирается в Stock Bot (только у него есть цены) и передаётся фотоген-боту,
который постит её в канал по кнопке «Опубликовать». Формат — цитата (<blockquote>):
бренд, серия (+ «инвертор»), затем строки «типоразмер — цена с наценкой» по возрастанию.
Поставщик и величина наценки НЕ раскрываются — готово к публикации.

Типоразмер берём из `btu_calc` (см. size_from_btu). Но у части серий `btu_calc` на сайте
неверен — у нескольких РАЗНЫХ моделей оказывается один и тот же размер (напр. Ballu
Olympio Legend: 3 модели 7/9/12, но все помечены 7). Признак — «коллизия» размеров.
В этом случае не схлопываем всё в одну строку: пробуем достать размер из артикула
(BSO-07/09/12 → 7/9/12), а если не вышло — показываем строки с кодом модели. Так в канал
попадают ВСЕ позиции, а не одна.
"""
import html
import re

from stock_report_bot.report import _fmt_price, _price_for
from stock_report_bot.menu import marked_price, short_series, _TYPE_PREFIXES

# Часть поставщиков кодирует модель ПЛОЩАДЬЮ помещения (м²), а не размером, и это число
# попадает в btu_calc/артикул как есть (50 и 70 вообще не бывают kBTU → это точно площади).
# Карта площадь(м²)→типоразмер (kBTU) от владельца. Применяется к итоговому числу.
_AREA_TO_SIZE = {25: 7, 30: 9, 35: 12, 50: 18, 60: 24, 70: 24}

# Стандартные коды типоразмера/площади в артикуле (база — apps/catalog/btu.py сайта,
# + площади 50/70, которые поставщики пишут в названии).
_CODE_RE = re.compile(
    r'(?<!\d)(07|09|10|12|13|14|16|18|20|22|24|25|26|27|30|32|35|36|40|42|48|50|60|70)(?!\d)')


def size_from_btu(btu):
    """Типоразмер (число «семёрка/девятка/…») из `btu_calc`.

    `btu_calc` сайта — УЖЕ готовый номинал в kBTU (7/9/10/12/13/14/16/18/20/22/24/25/26/
    27/30/32/35/36/40/42/48/60): сайт сам округляет к стандарту (apps/catalog/btu.py).
    Поэтому берём значение КАК ЕСТЬ, без повторного снапа (иначе 10→9, 14→12 и дубли).
    Подстраховка: полные BTU (9000) → /1000; число-площадь (25/30/35/50/60/70) → размер.
    None — если нет/мусор."""
    try:
        v = float(btu)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    if v > 200:           # на всякий случай: значение в полных BTU → в kBTU
        v = v / 1000.0
    n = int(round(v))
    if not 1 <= n <= 200:
        return None
    return _AREA_TO_SIZE.get(n, n)


def _model_code(row, brand):
    """Код/артикул модели из title: срезаем тип-префикс, бренд и слова серии — остаётся
    часть, начинающаяся с первого слова с цифрой (BSO-07HN8…). Запасной ярлык строки."""
    t = (row.get('title') or '').strip()
    for p in _TYPE_PREFIXES:
        if t.startswith(p):
            t = t[len(p):]
            break
    b = (brand or '').strip()
    if b and t.lower().startswith(b.lower() + ' '):
        t = t[len(b) + 1:].strip()
    words = t.split()
    for i, w in enumerate(words):
        if any(ch.isdigit() for ch in w):
            return ' '.join(words[i:])[:28].strip()
    return t[:28].strip() or '—'


def _size_from_code(code):
    """Размер из кода модели/артикула (BSO-07HN8 → 7; число-площадь → размер). None — нет кода."""
    m = _CODE_RE.search(code or '')
    if not m:
        return None
    s = int(m.group(1))
    return _AREA_TO_SIZE.get(s, s)


def _by_number(rows):
    """[(size|None, price, code)] → строки. Размер → «7 — цена», без размера → «код — цена»."""
    out = []
    for size, price, code in rows:
        if size is not None:
            out.append((size, str(size), price))
        else:
            out.append((10 ** 9, code, price))
    out.sort(key=lambda t: (t[0], t[1]))
    return [(lbl, p) for _, lbl, p in out]


def build_channel_caption(positions, pct, brand, series, source,
                          breez_base=None, inverter=False):
    """HTML-подпись-цитата серии для канала.

    positions: позиции серии в наличии (dict с btu_calc/title/source/nc_code/цены).
    pct:       выбранная наценка; цена строки = marked_price(опт, pct).
    inverter:  добавить «· инвертор» в заголовок.
    Возвращает строку <blockquote>…</blockquote> (≤ 1024 символов для серии).
    """
    # (size_из_btu, цена_с_наценкой, код_модели) по позициям в наличии с ценой.
    items = []
    for r in positions:
        price = marked_price(_price_for(r, breez_base), pct)
        if price is None:
            continue
        items.append((size_from_btu(r.get('btu_calc')), price, _model_code(r, brand)))

    known = [s for s, _, _ in items if s is not None]
    collision = len(known) != len(set(known))   # один размер у нескольких разных позиций

    if items and (collision or not known):
        # btu_calc серии ненадёжен → пробуем размеры из артикулов.
        art = [_size_from_code(code) for _, _, code in items]
        if art and all(a is not None for a in art) and len(set(art)) == len(art):
            # из артикулов вышли РАЗНЫЕ размеры на ВСЕ позиции → чистые номера.
            rows = _by_number([(a, p, code) for a, (_, p, code) in zip(art, items)])
        else:
            # иначе показываем все позиции по коду модели (сортировка по цене).
            rows = sorted(((code, p) for _, p, code in items), key=lambda t: t[1])
    else:
        rows = _by_number(items)

    head2 = short_series(series) + (' · инвертор' if inverter else '')
    body = [f'❄️ {(brand or "").strip()}', head2, '──────────────────']
    body += [f'{label} — {_fmt_price(price)}' for label, price in rows]
    return f'<blockquote>{html.escape(chr(10).join(body))}</blockquote>'
