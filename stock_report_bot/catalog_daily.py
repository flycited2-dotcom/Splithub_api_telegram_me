"""08:30 Moscow report: refresh suppliers, concise summary, sorted XLSX, menu."""
import html
from collections import Counter
from pathlib import Path
from stock_report_bot import catalog, catalog_menu
from stock_report_bot.config import TELEGRAM_OWNER_CHAT_ID, config
from stock_report_bot.catalog_excel import export_xlsx
from stock_report_bot.supplier_catalog import sync
from stock_report_bot.telegram import send_message, send_document

def daily():
    errors=sync()
    rows=catalog.products()
    text=f'☀️ <b>Склад · Симферополь</b>\nВ наличии: {len(rows)} позиций.\n'
    for supplier,count in sorted(Counter(p['supplier'] for p in rows).items()):
        text+=f'{supplier}: {count}\n'
    if errors:
        text+='⚠️ Не обновились: '+', '.join(errors)+'. Используется последняя успешная выгрузка.\n'
    for s in catalog.status():
        text+=f"{s['supplier']} — {html.escape(s['updated_at'][:16])} UTC\n"
    sent=send_message(TELEGRAM_OWNER_CHAT_ID,text)
    path=export_xlsx(rows,Path(config('CATALOG_OUTPUT',default='output'))/'Симферополь-остатки.xlsx')
    document=send_document(TELEGRAM_OWNER_CHAT_ID,path,'Все товары в наличии · сортировка по группе, виду, бренду и модели')
    catalog_menu.root(TELEGRAM_OWNER_CHAT_ID)
    return 0 if sent and document and not errors else 2

if __name__=='__main__':
    raise SystemExit(daily())
