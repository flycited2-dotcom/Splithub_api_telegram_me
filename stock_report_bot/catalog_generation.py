"""Use MCP/KBT rendering with the existing SplitHub publication workflow."""
import re
import sqlite3
from stock_report_bot import catalog, channel_caption, fotogen_bridge
from stock_report_bot.menu import short_series

def payload(product, pct):
    from stock_report_bot.catalog_menu import series_positions, compact_specs
    rows=series_positions(product)
    photo=next((url for row in [product]+rows for url in row.get('images',[])),None)
    specs=compact_specs(product)
    source='breeze' if product['supplier']=='breez' else product['supplier']
    category=6 if 'полупром' in product['group_name'].lower() or 'полупром' in product['kind'].lower() else 2
    # Reuse precisely the previous channel-caption builder and its rounding.
    adapted=[dict(source=source,nc_code=r['sku'],title=r.get('model') or r['title'],
                  brand=r.get('brand',''),series=r.get('series',''),category_id=category,
                  btu_calc=None,price_wholesale=r.get('purchase_price'),
                  price_base=r.get('purchase_price'),crimea_qty=r['quantity']) for r in rows]
    inverter=bool(re.search(r'\bинвертор|\binverter\b',' '.join(specs+[product.get('series',''),product['title']]),re.I))
    caption=channel_caption.build_publication_caption(adapted,pct,product.get('brand',''),
        product.get('series') or product.get('model') or product['title'],source,
        inverter=inverter,specs_lines=specs)
    return dict(photo_url=photo,brand=product.get('brand',''),
        model=short_series(product.get('series') or product.get('model') or product['title']),
        specs_lines=specs,caption=caption)

def claim(key):
    with catalog.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS card_requests (request_key TEXT PRIMARY KEY, state TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
        try:
            db.execute('INSERT INTO card_requests(request_key,state) VALUES (?,?)',(key,'submitting'))
        except sqlite3.IntegrityError:
            return False
    return True

def submit(product,pct,chat_id,message_id):
    data=payload(product,pct)
    if not data['photo_url']: return False,'no_photo'
    if len(data['caption'])>1024: return False,'caption_too_long'
    key=f'{chat_id}:{message_id}:{product["id"]}:{pct}'
    if not claim(key): return False,'duplicate'
    # Never repeat the HTTP request on timeout or a repeated callback.
    ok,_=fotogen_bridge.submit_card(chat_id=chat_id,**data)
    with catalog.connect() as db:
        db.execute('UPDATE card_requests SET state=? WHERE request_key=?',('submitted' if ok else 'unconfirmed',key))
    return ok,'submitted' if ok else 'unconfirmed'
