"""Сборка текста отчёта из строк БД. Чистые функции — тестируются без БД и сети."""
import html
from datetime import date
from itertools import groupby

SUPPLIER_LABELS = {'rusklimat': 'Русклимат', 'breeze': 'Бриз', 'daichi': 'Daichi'}

# Поставщик, для которого берём остаток со ВСЕХ складов (а не только Крым).
ALL_WAREHOUSES_SOURCE = 'breeze'


def _supplier_label(source):
    return SUPPLIER_LABELS.get(source, source or '—')


def _fmt_price(value):
    """'28 500 ₽' для числа/Decimal, '—' для None."""
    if value is None:
        return '—'
    return f'{int(round(float(value))):,}'.replace(',', ' ') + ' ₽'


def _qty_for(row):
    """Бриз — сумма по всем складам, остальные — крымский остаток."""
    if row['source'] == ALL_WAREHOUSES_SOURCE:
        return int(row['total_qty'] or 0)
    return int(row['crimea_qty'] or 0)


def _product_line(row):
    name = html.escape(row['title'] or '')
    return f'• {name} — {_fmt_price(row["price_wholesale"])} — {_qty_for(row)} шт.'


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


def build_report_chunks(rows, today=None, max_len=3900):
    """Список Telegram-сообщений (HTML) с остатками, сгруппированных по поставщику."""
    today = today or date.today()
    header = f'📦 Остатки в наличии (Крым + материк Бриза) — {today.strftime("%d.%m.%Y")}'

    rows = [r for r in rows if _qty_for(r) > 0]
    if not rows:
        return [f'{header}\n\nОстатков в наличии нет.']

    rows = sorted(rows, key=lambda r: (r['source'] or '', r['title'] or ''))
    lines = [header, '']
    for source, group in groupby(rows, key=lambda r: r['source']):
        lines.append(f'<b>{html.escape(_supplier_label(source))}</b>')
        lines.extend(_product_line(r) for r in group)
        lines.append('')

    return _chunk_lines(lines, max_len)
