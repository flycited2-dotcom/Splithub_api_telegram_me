"""Сборка текста отчёта из строк БД. Чистые функции — тестируются без БД и сети."""
import html
from datetime import date
from itertools import groupby

SUPPLIER_LABELS = {'rusklimat': 'Русклимат', 'breeze': 'Бриз', 'daichi': 'Daichi', 'jac': 'JAC'}
# Свой эмодзи у каждого поставщика — чтобы блоки различались с одного взгляда.
SUPPLIER_EMOJI = {'rusklimat': '🟦', 'daichi': '🟥', 'breeze': '🟩', 'jac': '🟨'}

# Бриз: опт (base) берётся из Бриз API по nc_code — в БД у него розница.
BREEZE_SOURCE = 'breeze'
# Русклимат: опт лежит в stock_stock.price_base — в price_wholesale у него розница
# (ric). Daichi — опт корректно в price_wholesale БД.
RUSKLIMAT_SOURCE = 'rusklimat'

# Полоски-разделители на всю ширину сообщения: тонкая — после каждой позиции,
# двойная — между брендами. Как в боте заказов: так удобнее ориентироваться.
ITEM_DIVIDER = '─' * 26
BRAND_DIVIDER = '═' * 26


def _supplier_label(source):
    return SUPPLIER_LABELS.get(source, source or '—')


def _supplier_header(source):
    emoji = SUPPLIER_EMOJI.get(source, '▫️')
    return f'{emoji} <b>{html.escape(_supplier_label(source)).upper()}</b>'


def _fmt_price(value):
    """'28 500 ₽' для числа/Decimal, '—' для None."""
    if value is None:
        return '—'
    return f'{int(round(float(value))):,}'.replace(',', ' ') + ' ₽'


def _qty_for(row):
    """Крымский остаток (Симферополь) — для всех поставщиков."""
    return int(row['crimea_qty'] or 0)


def _price_for(row, breez_base):
    """Опт-цена.
    - Бриз: base из Бриз API по nc_code (в БД розница), откат на price_wholesale.
    - Русклимат: опт («Ваша цена») лежит в stock_stock.price_base; в price_wholesale
      розница (ric). Откат на price_wholesale, если price_base пуст.
    - Daichi и прочие: price_wholesale из БД."""
    if row['source'] == BREEZE_SOURCE:
        base = (breez_base or {}).get(row.get('nc_code'))
        if base is not None:
            return base
    elif row['source'] == RUSKLIMAT_SOURCE:
        if row.get('price_base') is not None:
            return row['price_base']
    return row['price_wholesale']


def _product_line(row, breez_base):
    """`• <b>Бренд</b> Наименование — опт-цена ₽ — N шт.` Бренд жирным и впереди,
    т.к. в title он есть не всегда."""
    brand = html.escape((row.get('brand') or '').strip())
    name = html.escape(row['title'] or '')
    head = f'<b>{brand}</b> ' if brand else ''
    return f'• {head}{name} — {_fmt_price(_price_for(row, breez_base))} — {_qty_for(row)} шт.'


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
    сгруппированных по поставщику и бренду, с разделителями между брендами.
    breez_base: {nc_code: base} опт-цен Бриза из Бриз API; для остальных опт
    берётся из price_wholesale БД."""
    today = today or date.today()
    header_lines = ['📦 <b>Остатки в наличии</b> — Крым (Симферополь)',
                    f'🗓 {today.strftime("%d.%m.%Y")}']

    rows = [r for r in rows if _qty_for(r) > 0]
    if not rows:
        return ['\n'.join(header_lines) + '\n\nОстатков в наличии нет.']

    rows = sorted(rows, key=lambda r: (r['source'] or '', (r.get('brand') or ''), r['title'] or ''))
    lines = header_lines + ['']
    for source, group in groupby(rows, key=lambda r: r['source']):
        lines.append(_supplier_header(source))
        items = list(group)
        for i, r in enumerate(items):
            lines.append(_product_line(r, breez_base))
            if i < len(items) - 1:   # после каждой позиции, кроме последней у поставщика
                same_brand = (items[i + 1].get('brand') or '') == (r.get('brand') or '')
                lines.append(ITEM_DIVIDER if same_brand else BRAND_DIVIDER)
        lines.append('')

    return _chunk_lines(lines, max_len)
