"""Category navigation for the existing owner-only bot. Stable callback IDs."""
import hashlib
import html
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
import tempfile
from stock_report_bot import catalog
from stock_report_bot.catalog_excel import export_xlsx
from stock_report_bot.telegram import send_message, edit_message_text, send_photo, send_document

PAGE=8
def token(value): return hashlib.sha256(value.encode()).hexdigest()[:12]
def button(text,data): return {'text':text[:60],'callback_data':data}
def keyboard(rows): return {'inline_keyboard':rows}
def root(chat_id, message_id=None, data='cat:root'):
    rows=catalog.products()
    parts=data.split(':'); action=parts[1]
    text='📚 <b>Каталог · Симферополь</b>\nВыберите группу товаров.'
    kb=[]
    if action=='root':
        page=max(0,int(parts[2])) if len(parts)>2 else 0
        groups=sorted({p['group_name'] for p in rows})
        for group in groups[page*PAGE:(page+1)*PAGE]:
            count=sum(p['group_name']==group for p in rows)
            kb.append([button(f'{group} · {count}',f'cat:g:{token(group)}:0')])
        nav=[]
        if page: nav.append(button('◀',f'cat:root:{page-1}'))
        if (page+1)*PAGE<len(groups): nav.append(button('▶',f'cat:root:{page+1}'))
        if nav: kb.append(nav)
        kb += [[button('📊 Скачать Excel','cat:x')]]
        if not rows: text+='\nКаталог ещё не загружен.'
        for s in catalog.status(): text+=f"\n{html.escape(s['supplier'])}: {html.escape(s['updated_at'][:16])} UTC"
    else:
        group=next((g for g in {p['group_name'] for p in rows} if token(g)==parts[2]),None)
        if group is None: return root(chat_id,message_id)
        selected=[p for p in rows if p['group_name']==group]
        text=f'📂 <b>{html.escape(group)}</b>'
        if action=='g':
            page=max(0,int(parts[3])); kinds=sorted({p['kind'] for p in selected})
            for kind in kinds[page*PAGE:(page+1)*PAGE]:
                kb.append([button(kind,f'cat:k:{token(group)}:{token(kind)}:0')])
            prefix=f'cat:g:{token(group)}'
            total=len(kinds)
        else:
            kind=next((k for k in {p['kind'] for p in selected} if token(k)==parts[3]),None)
            if kind is None: return root(chat_id,message_id)
            selected=[p for p in selected if p['kind']==kind]
            page=max(0,int(parts[4])); total=len(selected)
            text+=f'\n{html.escape(kind)}'
            for p in selected[page*PAGE:(page+1)*PAGE]:
                kb.append([button(f"{p['title']} · {p['quantity']:g} шт.",f"cat:p:{p['id']}")])
            prefix=f'cat:k:{token(group)}:{token(kind)}'
        nav=[]
        if page: nav.append(button('◀',f'{prefix}:{page-1}'))
        if (page+1)*PAGE<total: nav.append(button('▶',f'{prefix}:{page+1}'))
        if nav: kb.append(nav)
        if action=='k': kb.append([button('⬅ Виды товаров',f'cat:g:{token(group)}:0')])
        kb.append([button('🏠 Каталог','cat:root')])
    markup=keyboard(kb)
    return edit_message_text(chat_id,message_id,text,markup) if message_id else send_message(chat_id,text,markup)

def sale_price(p,pct):
    if p.get('purchase_price') is None: return None
    base=Decimal(p['purchase_price'])*(1+Decimal(pct)/100)
    # Existing bot's rounding up to a price ending in 90.
    return ((base-90)/100).to_integral_value(rounding=ROUND_CEILING)*100+90

def description(p,client=False,pct=0):
    lines=[f"<b>{html.escape(p['title'])}</b>"]
    if client:
        price=sale_price(p,pct)
        lines.append(f"Цена: {price} {html.escape(p.get('currency',''))}" if price is not None else 'Цена по запросу')
    else:
        lines += [f"Поставщик: {p['supplier']}",f"Склад: {html.escape(p['warehouse'])}",
                  f"Остаток: {'не менее ' if p.get('quantity_lower_bound') else ''}{p['quantity']:g} шт.",
                  f"Цена поставщика: {p.get('purchase_price') or 'не предоставлена'} {html.escape(p.get('currency',''))}",
                  f"Обновлено: {p['updated_at'][:16]} UTC"]
    for s in p.get('specs',[]):
        lines.append(html.escape(f"{s['title']}: {s['value']} {s.get('unit','')}".strip()))
    if p.get('utp'): lines.append('\n💡 '+html.escape(p['utp']))
    if not p.get('specs') and not p.get('utp'): lines.append('Характеристики поставщиком не предоставлены.')
    return lines

def send_card(chat_id,p,client=False,pct=0):
    lines=description(p,client,pct)
    # Split by lines, including exceptionally long supplier descriptions.
    chunks=['']
    for line in lines:
        # escape chunks independently so an HTML entity cannot be split in half
        if len(line)>2500:
            raw=html.unescape(line)
            segments=[html.escape(raw[i:i+500]) for i in range(0,len(raw),500)]
        else: segments=[line]
        for segment in segments:
            if len(chunks[-1])+len(segment)+1>3500: chunks.append('')
            chunks[-1]+=segment+'\n'
    image=next(iter(p.get('images') or []),None)
    if image:
        caption=chunks[0] if len(chunks[0])<=1024 else html.escape(p['title'])[:900]
        if send_photo(chat_id,image,caption) and caption==chunks[0]: chunks=chunks[1:]
    for chunk in chunks:
        if chunk: send_message(chat_id,chunk)

def handle(chat_id,message_id,data):
    parts=data.split(':'); action=parts[1]
    if action=='x':
        with tempfile.TemporaryDirectory() as directory:
            path=export_xlsx(catalog.products(),Path(directory)/'Симферополь-остатки.xlsx')
            if not send_document(chat_id,path,'Остатки и цены · группы и виды товаров'):
                send_message(chat_id,'Не удалось отправить Excel. Попробуйте ещё раз.')
    elif action in ('p','t','c','s'):
        p=catalog.product(parts[2])
        if not p or p['quantity']<=0:
            return send_message(chat_id,'Товар больше не доступен. Откройте каталог заново.')
        if action=='p':
            kb=keyboard([[button('📋 ТТХ + УТП + фото',f"cat:t:{p['id']}")],
                         [button('👤 Карточка клиенту',f"cat:c:{p['id']}")],
                         [button('🏠 Каталог','cat:root')]])
            edit_message_text(chat_id,message_id,'\n'.join(description(p)[:5]),kb)
        elif action=='t': send_card(chat_id,p)
        elif action=='c':
            kb=keyboard([[button(f'+{pct}%',f"cat:s:{p['id']}:{pct}") for pct in group]
                         for group in ([0,1,2,3,4],[5,6,7,8,9,10],[15,20,25,30,40,50])]+[[button('🏠 Каталог','cat:root')]])
            edit_message_text(chat_id,message_id,'Выберите наценку для карточки клиента:',kb)
        else: send_card(chat_id,p,True,int(parts[3]))
    else: root(chat_id,message_id,data)
