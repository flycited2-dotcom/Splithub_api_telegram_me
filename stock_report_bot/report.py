"""Сборка текста отчёта из строк БД. Чистые функции — тестируются без БД и сети."""
import html
from datetime import date
from itertools import groupby

SUPPLIER_LABELS = {'rusklimat': 'Русклимат', 'breeze': 'Бриз', 'daichi': 'Daichi'}

# Поставщик, у которого опт-цена (base) берётся из Бриз API, а не из БД.
BREEZE_SOURCE = 'breeze'


def _supplier_label(source):
    return SUPPLIER_LABELS.get(source, source or '—')


def _fmt_price(value):
    """'28 500 ₽' для числа/Decimal, '—' для None."""
    if value is None:
        return '—'
    return f'{int(round(float(value))):,}'.replace(',', ' ') + ' ₽'


def _qty_for(row):
    """Крымский остаток (Симферополь) — для всех поставщиков."""
    return int(row['crimea_qty'] or 0)


def _price_for(row, breez_base):
    """Опт-цена. Бриз отдаёт опт (base) только в своём API — в БД сайта у него
    розница. Поэтому для Бриза берём base по nc_code из breez_base; если его нет
    (ключ не задан/ошибка) — откатываемся на price_wholesale из БД."""
    if row['source'] == BREEZE_SOURCE:
        base = (breez_base or {}).get(row.get('nc_code'))
        if base is not None:
            return base
    return row['price_wholesale']


def _product_line(row, breez_base):
    """Строка `• Бренд Наименование — опт-цена ₽ — N шт.` Бренд впереди, т.к. в
    title он есть не всегда."""
    brand = html.escape((row.get('brand') or '').strip())
    name = html.escape(row['title'] or '')
    title = f'{brand} {name}'.strip() if brand else name
    return f'• {title} — {_fmt_price(_price_for(row, breez_base))} — {_qty_for(row)} шт.'


def _chunk_lines(lines, max_len):
    """Склеивает строки в сообщения по границам строк, каждое ≤ max_len."""
    chunks, cur, cur_len = [], [], 0
    for line in lines:
        add = len(line) + 1  # +1 за перенос строки
        if cur and cur_len + add > max_len:
            chunks.append('\n'.join(cur))
            cur, cur_len = [line], add
        else:
            cur.append(line)
            cur_len += add
    if cur:
        chunks.append('\n'.join(cur))
    return chunks


def build_report_chunks(rows, breez_base=None, today=None, max_len=3900):
    """Список Telegram-сообщений (HTML) с остатками (Крым, Симферополь),
    сгруппированных по поставщику и бренду. breez_base: {nc_code: base} опт-цен
    Бриза из Бриз API; для остальных опт берётся из price_wholesale БД."""
    today = today or date.today()
    header = f'📦 Остатки в наличии (Крым, Симферополь) — {today.strftime("%d.%m.%Y")}'

    rows = [r for r in rows if _qty_for(r) > 0]
    if not rows:
        return [f'{header}\n\nОстатков в наличии нет.']

    rows = sorted(rows, key=lambda r: (r['source'] or '', (r.get('brand') or ''), r['title'] or ''))
    lines = [header, '']
    for source, group in groupby(rows, key=lambda r: r['source']):
        lines.append(f'<b>{html.escape(_supplier_label(source))}</b>')
        lines.extend(_product_line(r, breez_base) for r in group)
        lines.append('')

    return _chunk_lines(lines, max_len)
