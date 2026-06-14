"""Чтение остатков/цен из общей БД сайта SplitHome (read-only).

Состав отчёта (бизнес-правило): «только Крым (Симферополь) для ВСЕХ поставщиков».
Берём из сводной таблицы `stock_stock`: сайт кладёт туда `warehouse='Симферополь'`
только если у товара есть крымский остаток (крымский склад ловится регуляркой
`_CRIMEA_RE` в sync сайта — для Бриза это «…Крым» и т.п.). Материковые остатки
(Шерризон/Ростов/Киржач) и «под заказ» в отчёт НЕ попадают.

Только кондиционеры нужных типов:
- категории `REPORT_CATEGORY_IDS` (Бытовые сплит / Полупромышленные / Мобильные);
- `btu_calc > 0` — у товара есть мощность охлаждения, т.е. это кондиционер, а не
  аксессуар/инструмент (мойки, развальцовки, насосы, шланги, сифоны… btu пуст);
- `EXCLUDE_TITLE_PATTERNS` — добивают аксессуары с ошибочно проставленным btu
  (виброопоры «V40P»→40, охладитель воздуха, зимний комплект) и мультисплит.

Опт-цена: Daichi — `price_wholesale` из БД; Бриз — base из Бриз API по nc_code
(stock_report_bot/breez.py), в БД у него розница; Rusklimat — `stock_stock.price_base`
(в БД `price_wholesale` = розница/ric). Наименование — `title` + бренд (`catalog_brand`).
"""
import psycopg2
from psycopg2.extras import RealDictCursor

from stock_report_bot.config import DB

# Категории-кондиционеры в отчёте (id в catalog_category сайта):
#   2 — Бытовые сплит-системы, 6 — Полупромышленные сплит-системы
#   (кассетные/канальные/напольно-потолочные/колонные), 7 — Мобильные кондиционеры.
# Аксессуары (id 116) сюда не входят.
REPORT_CATEGORY_IDS = [2, 6, 7]

# Названия-исключения: мультисплит + аксессуары, которым compute_btu ошибочно
# проставил btu_calc (виброопоры/охладитель/зимний комплект) и они прошли btu-фильтр.
EXCLUDE_TITLE_PATTERNS = [
    '%мульти%', '%виброопор%', '%охладитель воздуха%',
    '%комплект зимний%', '%зимний комплект%',
]

_QUERY = """
SELECT p.source,
       p.nc_code,
       b.title AS brand,
       p.title,
       p.series,
       p.price_wholesale,
       s.price_base,
       s.quantity AS crimea_qty,
       (SELECT i.url FROM catalog_productimage i
        WHERE i.product_id = p.id ORDER BY i."order" LIMIT 1) AS image_url
FROM catalog_product p
JOIN stock_stock s ON s.product_id = p.id
LEFT JOIN catalog_brand b ON b.id = p.brand_id
WHERE p.is_active = TRUE
  AND s.warehouse = %(crimea)s
  AND s.quantity > 0
  AND p.category_id = ANY(%(cats)s)
  AND p.btu_calc > 0
  AND NOT (p.title ILIKE ANY(%(deny)s))
ORDER BY p.source, b.title NULLS LAST, p.title;
"""


def fetch_stock_rows():
    """Список dict'ов: source, nc_code, brand, title, series, price_wholesale, price_base,
    crimea_qty, image_url.

    `series`/`image_url` нужны интерактивному меню (`menu`); отчёт их не использует.
    `image_url` — URL первого фото товара (order=0, обычно внутренний блок)."""
    conn = psycopg2.connect(
        host=DB['host'], port=DB['port'], dbname=DB['dbname'],
        user=DB['user'], password=DB['password'],
    )
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(_QUERY, {
                'crimea': 'Симферополь',
                'cats': REPORT_CATEGORY_IDS,
                'deny': EXCLUDE_TITLE_PATTERNS,
            })
            return cur.fetchall()
    finally:
        conn.close()


# Технические характеристики позиций серии — для блока «ключевые особенности»
# (см. specs.py). Берём по nc_code; ORDER BY p.id, ts.order — строки первой позиции
# идут первыми (она «представительная» для качественных признаков серии).
_TECH_QUERY = """
SELECT ts.title AS title, pt.value AS value
FROM catalog_producttech pt
JOIN catalog_techspec ts ON ts.id = pt.spec_id
JOIN catalog_product p ON p.id = pt.product_id
WHERE p.nc_code = ANY(%(ncs)s)
ORDER BY p.id, ts."order";
"""


def fetch_tech_values(nc_codes):
    """Список dict'ов {title, value} по характеристикам товаров с указанными nc_code
    (read-only). Пусто, если список пуст. Дёргается лениво — при нажатии кнопки
    «Добавить характеристики»."""
    if not nc_codes:
        return []
    conn = psycopg2.connect(
        host=DB['host'], port=DB['port'], dbname=DB['dbname'],
        user=DB['user'], password=DB['password'],
    )
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(_TECH_QUERY, {'ncs': list(nc_codes)})
            return cur.fetchall()
    finally:
        conn.close()
