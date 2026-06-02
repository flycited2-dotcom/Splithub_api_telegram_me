"""Чтение остатков/цен из общей БД сайта SplitHome (read-only).

Состав отчёта (бизнес-правило): «Крым для всех поставщиков + Бриз со всех
складов». Количество: Бриз — сумма по всем складам, остальные — крымский остаток
(`stock_stock.quantity` при `warehouse='Симферополь'`). Опт-цена — `price_wholesale`
(для Бриза туда сайт кладёт base/закупку — см. фикс в sync_stock сайта).
"""
import psycopg2
from psycopg2.extras import RealDictCursor

from stock_report_bot.config import DB

_QUERY = """
SELECT p.source,
       p.title,
       p.price_wholesale,
       s.quantity AS crimea_qty,
       COALESCE(ws.total_qty, 0) AS total_qty
FROM catalog_product p
LEFT JOIN stock_stock s ON s.product_id = p.id
LEFT JOIN (
    SELECT product_id, SUM(quantity) AS total_qty
    FROM stock_warehousestock
    GROUP BY product_id
) ws ON ws.product_id = p.id
WHERE p.is_active = TRUE
  AND COALESCE(ws.total_qty, 0) > 0
  AND (s.warehouse = %(crimea)s OR p.source = %(breeze)s)
ORDER BY p.source, p.title;
"""


def fetch_stock_rows():
    """Возвращает список dict'ов: source, title, price_wholesale, crimea_qty, total_qty."""
    conn = psycopg2.connect(
        host=DB['host'], port=DB['port'], dbname=DB['dbname'],
        user=DB['user'], password=DB['password'],
    )
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(_QUERY, {'crimea': 'Симферополь', 'breeze': 'breeze'})
            return cur.fetchall()
    finally:
        conn.close()
