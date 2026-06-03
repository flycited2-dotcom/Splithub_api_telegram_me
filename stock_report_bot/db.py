"""Чтение остатков/цен из общей БД сайта SplitHome (read-only).

Состав отчёта (бизнес-правило): «только Крым (Симферополь) для ВСЕХ поставщиков».
Берём из сводной таблицы `stock_stock`: сайт кладёт туда `warehouse='Симферополь'`
только если у товара есть крымский остаток (крымский склад ловится регуляркой
`_CRIMEA_RE` в sync сайта — для Бриза это «…Крым» и т.п.). Материковые остатки
(Шерризон/Ростов/Киржач) и «под заказ» в отчёт НЕ попадают.

Категории: только кондиционеры нужных типов (Бытовые сплит / Полупромышленные /
Мобильные); расходники (Аксессуары) и мультисплит-системы исключены. Опт-цена для
Rusklimat/Daichi — `price_wholesale` из БД; для Бриза — base из Бриз API
(stock_report_bot/breez.py). Наименование — `title` с подставленным брендом
(`catalog_brand`).
"""
import psycopg2
from psycopg2.extras import RealDictCursor

from stock_report_bot.config import DB

# Категории-кондиционеры, нужные в отчёте (id в catalog_category сайта):
#   2 — Бытовые сплит-системы, 6 — Полупромышленные сплит-системы
#   (кассетные/канальные/напольно-потолочные/колонные), 7 — Мобильные кондиционеры.
# Исключаются: 116 «Аксессуары» (расходники) и мультисплит-системы (по названию).
REPORT_CATEGORY_IDS = [2, 6, 7]

_QUERY = """
SELECT p.source,
       p.nc_code,
       b.title AS brand,
       p.title,
       p.price_wholesale,
       s.quantity AS crimea_qty
FROM catalog_product p
JOIN stock_stock s ON s.product_id = p.id
LEFT JOIN catalog_brand b ON b.id = p.brand_id
WHERE p.is_active = TRUE
  AND s.warehouse = %(crimea)s
  AND s.quantity > 0
  AND p.category_id = ANY(%(cats)s)
  AND p.title NOT ILIKE %(multi)s
ORDER BY p.source, b.title NULLS LAST, p.title;
"""


def fetch_stock_rows():
    """Список dict'ов: source, nc_code, brand, title, price_wholesale, crimea_qty."""
    conn = psycopg2.connect(
        host=DB['host'], port=DB['port'], dbname=DB['dbname'],
        user=DB['user'], password=DB['password'],
    )
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(_QUERY, {
                'crimea': 'Симферополь',
                'cats': REPORT_CATEGORY_IDS,
                'multi': '%мульти%',
            })
            return cur.fetchall()
    finally:
        conn.close()
