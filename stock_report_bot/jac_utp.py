"""УТП (преимущества) серий JAC из файла скрапера (jac_utp_latest.json).

Скрапер `ostatki_mdv_b2b` готовит файл с отобранными владельцем УТП по сериям —
короткие «птички»-преимущества (общие на серию, не зависят от артикула/мощности).
Формат файла: { бренд → СЕРИЯ_В_ВЕРХНЕМ_РЕГИСТРЕ → [список УТП] }.

Отдельно от `jac_specs.py` (тот — per-model ТТХ из jac_specs_latest.json) и от
`specs.py` (блок особенностей серии из БД сайта). Связка с товаром — по имени серии
(нормализованному), бренд = поле `brand` остатков. Серии нет в файле → пустой список
→ блок просто не выводим. Файла нет/битый → {} (бот не падает).
"""
import html
import json
import logging

logger = logging.getLogger('stock_report_bot.jac_utp')


def _configured_path():
    try:
        from stock_report_bot.config import JAC_UTP_JSON
        return JAC_UTP_JSON
    except Exception:
        return ''


def normalize_series(s):
    """Серия → UPPER CASE со схлопнутыми пробелами (ключ файла УТП). None/'' → ''."""
    return ' '.join((s or '').upper().split())


def load_utp(path=None):
    """Возвращает {бренд:{СЕРИЯ:[УТП…]}}; путь пуст/файла нет/битый → {}."""
    path = path if path is not None else _configured_path()
    if not path:
        return {}
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning('УТП JAC недоступны (%s) — без блока УТП', e)
        return {}


def utp_for(utp_data, brand, series):
    """Список УТП для серии товара (связка по бренду + нормализованной серии).
    Нет бренда/серии в файле → [] (товар выводится без блока УТП)."""
    return utp_data.get(brand, {}).get(normalize_series(series), [])


def build_utp_block(brand, series, utp_list):
    """HTML-блок «ключевые особенности» серии (цитата) — в стиле
    specs.build_specs_block: заголовок + <blockquote> со строками «✓ …».
    Пустой список → None (блок не выводим). `series` — уже готовое к показу имя."""
    if not utp_list:
        return None
    head = (f'💡 {html.escape((brand or "").strip())} '
            f'{html.escape((series or "").strip())} — ключевые особенности:')
    body = '\n'.join('✓ ' + html.escape(x) for x in utp_list)
    return f'{head}\n<blockquote>{body}</blockquote>'
