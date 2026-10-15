"""Category navigation for the existing owner-only bot. Stable callback IDs."""
import hashlib
import html
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
import tempfile
import re
from stock_report_bot import catalog
from stock_report_bot.config import FOTOGEN_CARD_MODE
from stock_report_bot.catalog_excel import export_xlsx
from stock_report_bot.telegram import send_message, edit_message_text, send_photo, send_document

PAGE=8
_SEARCH_QUERIES={}
def token(value): return hashlib.sha256(value.encode()).hexdigest()[:12]
def button(text,data,style=None):
    b={'text':text[:60],'callback_data':data}
    if style: b['style']=style
    return b
def keyboard(rows): return {'inline_keyboard':rows}

def short_choice(number,label,count=None):
    """Buttons are selectors; full information is in the numbered message."""
    prefix=f'{number}. '
    suffix=f' · {count}' if count is not None else ''
    budget=26-len(prefix)-len(suffix)
    label=' '.join(label.split())
    if len(label)>budget: label=label[:budget-1].rstrip()+'…'
    return prefix+label+suffix

def kind_label(kind):
    low=kind.lower()
    if 'кот' in low and 'газов' in low:
        if 'двухконтур' in low: return 'Газовые · 2 контура'
        if 'раздельн' in low: return 'Газовые · раздельные ТО'
        return 'Газовые котлы'
    if 'кот' in low and 'электр' in low:
        return 'Электрокотлы с насосом' if 'насос' in low else 'Электрокотлы'
    for word,title in [('увлажнит','Увлажнители'),('осушит','Осушители'),('тепловентил','Тепловентиляторы')]:
        if word in low: return title
    return kind

def product_name(p):
    model=p.get('model') or p['title']; brand=p.get('brand','')
    return model if model.casefold().startswith(brand.casefold()) else ' '.join(filter(None,[brand,model]))

SUPPLIERS={'breez':'Breez · Бриз','daichi':'Daichi · Даичи'}
def group_of(p):
    g=p['group_name'].lower()
    if any(v in g for v in ('сплит','кондиционир','мультисистем','vrf')): return 'Кондиционеры'
    if any(v in g for v in ('вентиляц',)): return 'Вентиляция'
    if any(v in g for v in ('котлы','теплов','отоплен')): return 'Отопление и вода'
    if 'водоочист' in g: return 'Очистка воды'
    if 'управлен' in g: return 'Управление и Wi-Fi'
    if 'расходн' in g: return 'Материалы и инструмент'
    if 'аксессуар' in g: return 'Аксессуары'
    if 'бытовое' in g: return 'Техника для дома'
    if 'без категории' in g: return 'Прочие товары'
    return p['group_name']

def kind_of(p):
    k=' '.join(p['kind'].split()); g=p['group_name'].lower()
    if group_of(p)=='Кондиционеры':
        if 'vrf' in g: prefix='VRF'
        elif 'мульти' in g or 'мульти' in k.lower(): prefix='Мультисплит'
        elif 'полупром' in g or 'полупром' in k.lower(): prefix='Полупром'
        else: prefix='Бытовые'
        low=k.lower()
        if 'внутрен' in low: label='Внутренние блоки'
        elif 'наруж' in low: label='Наружные блоки'
        elif 'мобил' in low: return 'Мобильные кондиционеры'
        elif 'кассет' in low: label='Кассетные'
        elif 'канальн' in low: label='Канальные'
        elif 'потолоч' in low: label='Напольно-потолочные'
        elif 'аксессуар' in low: label='Аксессуары'
        else: label='Комплекты'
        return prefix+' · '+label
    return k.replace('Бытовые ','').replace('Бытовой ','').replace('для сплит-систем','').strip()

def show(chat_id,message_id,text,kb):
    return edit_message_text(chat_id,message_id,text,keyboard(kb)) if message_id else send_message(chat_id,text,keyboard(kb))

def home(chat_id,message_id=None):
    return show(chat_id,message_id,'🏠 <b>SplitHub · Главное меню</b>\nСерии и прайс — прежнее меню с фотогенератором.\nКаталог — группы, поставщики и товары.\nВыберите действие:',[
        [button('📋 Серии и прайс','cat:old','primary')],
        [button('📄 Список остатков','cat:report')],
        [button('📂 Каталог по группам','cat:root')],
        [button('🔎 Найти модель','cat:find')],
        [button('⬇️ Excel остатков','cat:x','primary')]])

def pages(kb,page,total,prefix):
    nav=[]
    if page: nav.append(button('◀ Назад',f'{prefix}:{page-1}'))
    if (page+1)*PAGE<total: nav.append(button('Далее ▶',f'{prefix}:{page+1}'))
    if nav: kb.append(nav)
def root(chat_id, message_id=None, data='cat:root'):
    rows=catalog.products()
    parts=data.split(':'); action=parts[1]
    text='📚 <b>Каталог · Симферополь</b>\nВыберите группу товаров.'
    kb=[]
    if action=='root':
        page=max(0,int(parts[2])) if len(parts)>2 else 0
        groups=sorted({group_of(p) for p in rows})
        text+='\n'
        for number,group in enumerate(groups[page*PAGE:(page+1)*PAGE],start=page*PAGE+1):
            count=sum(group_of(p)==group for p in rows)
            text+=f'\n<b>{number}.</b> {html.escape(group)} — {count} поз.\n'
            kb.append([button(short_choice(number,group,count),f'cat:g:{token(group)}')])
        nav=[]
        if page: nav.append(button('◀',f'cat:root:{page-1}'))
        if (page+1)*PAGE<len(groups): nav.append(button('▶',f'cat:root:{page+1}'))
        if nav: kb.append(nav)
        kb += [[button('⬅ Главное меню','cat:home')]]
        if not rows: text+='\nКаталог ещё не загружен.'
        for s in catalog.status(): text+=f"\n{html.escape(s['supplier'])}: {html.escape(s['updated_at'][:16])} UTC"
    else:
        group=next((g for g in {group_of(p) for p in rows} if token(g)==parts[2]),None)
        if group is None: return root(chat_id,message_id)
        selected=[p for p in rows if group_of(p)==group]
        text=f'📂 <b>{html.escape(group)}</b>'
        if action=='g':
            text+='\nВыберите поставщика:'
            for supplier in sorted({p['supplier'] for p in selected}):
                count=sum(p['supplier']==supplier for p in selected)
                kb.append([button(f'{SUPPLIERS.get(supplier,supplier)} · {count}',f'cat:v:{token(group)}:{supplier}:0')])
            kb.append([button('⬅ Группы','cat:root')])
            kb.append([button('🏠 Главное меню','cat:home')])
            return show(chat_id,message_id,text,kb)
        supplier=parts[3]
        selected=[p for p in selected if p['supplier']==supplier]
        text+='\n'+html.escape(SUPPLIERS.get(supplier,supplier))
        if action=='v':
            page=max(0,int(parts[4])); kinds=sorted({kind_of(p) for p in selected})
            text+='\n\nВыберите категорию по номеру:\n'
            for number,kind in enumerate(kinds[page*PAGE:(page+1)*PAGE],start=page*PAGE+1):
                count=sum(kind_of(p)==kind for p in selected)
                text+=f'\n<b>{number}.</b> {html.escape(kind)} — {count} поз.\n'
                kb.append([button(short_choice(number,kind_label(kind),count),f'cat:l:{token(group)}:{supplier}:{token(kind)}:0')])
            prefix=f'cat:v:{token(group)}:{supplier}'
            total=len(kinds)
        else:
            kind=next((k for k in {kind_of(p) for p in selected} if token(k)==parts[4]),None)
            if kind is None: return root(chat_id,message_id)
            selected=[p for p in selected if kind_of(p)==kind]
            page=max(0,int(parts[5])); total=len(selected)
            text+=f'\n{html.escape(kind)}'
            text+='\n\nВыберите товар по номеру:\n'
            for number,p in enumerate(selected[page*PAGE:(page+1)*PAGE],start=page*PAGE+1):
                name=product_name(p)
                text+=f'\n<b>{number}. {html.escape(name)}</b>\n'
                if p['title']!=name: text+=html.escape(p['title'])+'\n'
                text+=f"Остаток: {'от ' if p.get('quantity_lower_bound') else ''}{p['quantity']:g} шт.\n"
                kb.append([button(short_choice(number,p.get('model') or p['title']),f"cat:p:{p['id']}")])
            prefix=f'cat:l:{token(group)}:{supplier}:{token(kind)}'
        nav=[]
        if page: nav.append(button('◀',f'{prefix}:{page-1}'))
        if (page+1)*PAGE<total: nav.append(button('▶',f'{prefix}:{page+1}'))
        if nav: kb.append(nav)
        back=f'cat:v:{token(group)}:{supplier}:0' if action=='l' else f'cat:g:{token(group)}'
        kb.append([button('⬅ Назад',back)])
        kb.append([button('🏠 Главное меню','cat:home')])
    markup=keyboard(kb)
    return edit_message_text(chat_id,message_id,text,markup) if message_id else send_message(chat_id,text,markup)

def sale_price(p,pct):
    if p.get('purchase_price') is None: return None
    base=Decimal(p['purchase_price'])*(1+Decimal(pct)/100)
    # Existing bot's rounding up to a price ending in 90.
    return ((base-90)/100).to_integral_value(rounding=ROUND_CEILING)*100+90

def series_positions(p):
    # A series with no name must never collect unrelated products.
    if not p.get('series','').strip(): return [p]
    return sorted([r for r in catalog.products() if r['supplier']==p['supplier']
        and r.get('brand','')==p.get('brand','') and r.get('series','').strip()==p['series'].strip()
        and kind_of(r)==kind_of(p)],key=lambda r:r.get('model') or r['title'])

def series_lines(p,pct):
    from stock_report_bot.menu import short_series
    heading=' '.join(filter(None,[p.get('brand'),short_series(p.get('series') or p.get('model') or p['title'])]))
    lines=[f'🏷 <b>{html.escape(heading)}</b>','']
    for row in series_positions(p):
        price=sale_price(row,pct)
        price_text=f"{int(price):,}".replace(',',' ')+' ₽' if price is not None else 'Цена по запросу'
        if row.get('currency','RUB')!='RUB' and price is not None: price_text=f"{price} {row['currency']}"
        label=' '.join(filter(None,[row.get('brand'),row.get('model') or row['title']]))
        lines.append(f"• <b>{html.escape(label)}</b> — {price_text} — {'от ' if row.get('quantity_lower_bound') else ''}{row['quantity']:g} шт.")
        lines.append('────────────────')
    return lines[:-1]

def compact_specs(p):
    from stock_report_bot.specs import build_specs_for_card
    source='breeze' if p['supplier']=='breez' else p['supplier']
    lines=build_specs_for_card(p.get('specs',[]),p.get('brand',''),p.get('series',''),source,
                              utp_raw=p.get('utp') or None,titles=[p['title']])
    if not lines:
        lines=[f"{s['title']}: {s['value']} {s.get('unit','')}".strip() for s in p.get('specs',[])[:7]]
    if not lines and p.get('utp'): lines=p['utp'].splitlines()[:6]
    return lines

def send_payload(chat_id,lines,image=None):
    chunks=['']
    for line in lines:
        if len(line)>2500:
            raw=html.unescape(line)
            segments=[html.escape(raw[i:i+500]) for i in range(0,len(raw),500)]
        else: segments=[line]
        for segment in segments:
            if len(chunks[-1])+len(segment)+1>3500: chunks.append('')
            chunks[-1]+=segment+'\n'
    if image:
        # Fill the photo caption with complete lines, rather than just a title.
        caption=[]; remainder=list(lines)
        while remainder and len('\n'.join(caption+[remainder[0]]))<=1000:
            caption.append(remainder.pop(0))
        if caption and send_photo(chat_id,image,'\n'.join(caption)):
            if remainder: return send_payload(chat_id,remainder)
            return
    for chunk in chunks:
        if chunk: send_message(chat_id,chunk)

def send_series(chat_id,p,pct):
    rows=series_positions(p)
    image=next((url for row in [p]+rows for url in (row.get('images') or [])),None)
    lines=series_lines(p,pct)
    features=compact_specs(p)
    if features:
        lines += ['', '📋 <b>ТТХ / преимущества серии</b>']
        lines += ['✓ '+html.escape(line) for line in features]
    send_payload(chat_id,lines,image)

def search(chat_id,query,page=0,message_id=None):
    query=' '.join(query.split()).strip()[:160]
    words=query.casefold().split()
    rows=[p for p in catalog.products() if all(w in ' '.join(str(p.get(k,'')) for k in
           ('brand','model','series','title','sku')).casefold() for w in words)] if words else []
    query_id=token(query)
    if len(_SEARCH_QUERIES)>=100: _SEARCH_QUERIES.pop(next(iter(_SEARCH_QUERIES)))
    _SEARCH_QUERIES[(chat_id,query_id)]=query
    text=f'🔎 <b>{html.escape(query)}</b>\nНайдено: {len(rows)}.\nВыберите товар по номеру:\n'
    kb=[]
    for number,p in enumerate(rows[page*PAGE:(page+1)*PAGE],start=page*PAGE+1):
        text+=f"\n<b>{number}. {html.escape(product_name(p))}</b>\n{html.escape(SUPPLIERS.get(p['supplier'],p['supplier']))} · {p['quantity']:g} шт.\n"
        kb.append([button(short_choice(number,p.get('model') or p['title']),f"cat:p:{p['id']}")])
    pages(kb,page,len(rows),f'cat:z:{query_id}')
    kb.append([button('🔎 Новый поиск','cat:find')]); kb.append([button('🏠 Главное меню','cat:home')])
    if not rows: text+=' Попробуйте артикул, модель или бренд.'
    return show(chat_id,message_id,text,kb)

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
    if client: return send_series(chat_id,p,pct)
    lines=[f"<b>{html.escape(p['title'])}</b>", '📋 Характеристики и преимущества']
    lines += ['✓ '+html.escape(line) for line in compact_specs(p)]
    if len(lines)==2: lines.append('Характеристики поставщиком не предоставлены.')
    send_payload(chat_id,lines,next(iter(p.get('images') or []),None))
    send_message(chat_id,'Другие действия:',keyboard([
        [button('Все характеристики',f"cat:a:{p['id']}")],
        [button('⬅ К товару',f"cat:p:{p['id']}")],
        [button('🏠 Главное меню','cat:home')]]))
    return
def handle(chat_id,message_id,data):
    parts=data.split(':'); action=parts[1]
    if action=='home': return home(chat_id,message_id)
    if action=='z':
        query=_SEARCH_QUERIES.get((chat_id,parts[2]))
        if query is None:
            return show(chat_id,message_id,'Поиск обновился. Нажмите «Найти модель» и введите запрос снова.',[
                [button('🔎 Найти модель','cat:find')],[button('🏠 Главное меню','cat:home')]])
        return search(chat_id,query,int(parts[3]),message_id)
    if action=='x' and len(parts)==2:
        return show(chat_id,message_id,'⬇️ <b>Скачать остатки</b>\nВыберите состав Excel:',[
            [button('Все поставщики','cat:x:all','primary')],
            [button('Только Breez','cat:x:breez')], [button('Только Daichi','cat:x:daichi')],
            [button('⬅ Главное меню','cat:home')]])
    if action=='x':
        with tempfile.TemporaryDirectory() as directory:
            rows=[p for p in catalog.products() if parts[2]=='all' or p['supplier']==parts[2]]
            path=export_xlsx(rows,Path(directory)/'Симферополь-остатки.xlsx')
            if not send_document(chat_id,path,'Остатки и цены · группы и виды товаров'):
                send_message(chat_id,'Не удалось отправить Excel. Попробуйте ещё раз.')
        return send_message(chat_id,'⬇️ Остатки по группам и видам товаров.',keyboard([
            [button('⬅ К выбору файла','cat:x')],[button('🏠 Главное меню','cat:home')]]))
    elif action in ('p','t','c','s','a','f','q','j'):
        p=catalog.product(parts[2])
        if not p or p['quantity']<=0:
            return send_message(chat_id,'Товар больше не доступен. Откройте каталог заново.')
        if action=='p':
            kb=keyboard([[button('📋 Фото + ТТХ / УТП',f"cat:t:{p['id']}")],
                         [button('👤 Клиенту: прайс + ТТХ',f"cat:c:{p['id']}",'primary')],
                         [button('🎨 Карточка для канала',f"cat:f:{p['id']}",'primary')],
                         [button('⬅ К товарам',f"cat:l:{token(group_of(p))}:{p['supplier']}:{token(kind_of(p))}:0")],
                         [button('🏠 Главное меню','cat:home')]])
            edit_message_text(chat_id,message_id,'\n'.join(description(p)[:5]),kb)
        elif action=='t': send_card(chat_id,p)
        elif action=='a':
            send_payload(chat_id,description(p))
            send_message(chat_id,'Назад:',keyboard([[button('⬅ К товару',f"cat:p:{p['id']}")]]))
        elif action in ('c','f'):
            next_action='s' if action=='c' else 'q'
            kb=keyboard([[button(f'+{pct}%',f"cat:{next_action}:{p['id']}:{pct}") for pct in group]
                         for group in ([0,1,2,3,4],[5,6,7,8,9,10],[15,20,25,30,40,50])]+[[button('⬅ К товару',f"cat:p:{p['id']}")]])
            edit_message_text(chat_id,message_id,
                ('👤 <b>Фото + прайс серии + ТТХ/УТП</b>' if action=='c' else f'🎨 <b>Карточка для канала · {html.escape(FOTOGEN_CARD_MODE.upper())}</b>')+
                f"\nМоделей в наличии: {len(series_positions(p))}.\nВыберите наценку:",kb)
        elif action=='q':
            from stock_report_bot.catalog_generation import payload
            data=payload(p,int(parts[3]))
            if not data['photo_url']:
                return show(chat_id,message_id,'У поставщика нет фото для генерации.',[[button('⬅ К товару',f"cat:p:{p['id']}")]])
            if len(data['caption'])>1024:
                return show(chat_id,message_id,'Прайс серии слишком длинный для подписи фото в канале. Выберите меньшую серию в прежнем меню.',[[button('⬅ К товару',f"cat:p:{p['id']}")]])
            text=f'🎨 <b>Создать карточку для канала · {html.escape(FOTOGEN_CARD_MODE.upper())}</b>\nГрафитовый фон, белый текст и стеклянные плашки.\nФото товара сохраняется без изменения формы.\n\nПодпись к публикации:\n'+data['caption']
            return show(chat_id,message_id,text,[[button(f'🎨 Генерировать · {FOTOGEN_CARD_MODE.upper()}',f"cat:j:{p['id']}:{parts[3]}",'primary')],
                [button('⬅ Изменить наценку',f"cat:f:{p['id']}")],[button('🏠 Главное меню','cat:home')]])
        elif action=='j':
            from stock_report_bot.catalog_generation import submit
            ok,result=submit(p,int(parts[3]),chat_id,message_id)
            texts={'submitted':'⏳ Карточка отправлена в ваш прежний фотогенератор. Результат придёт в чат фотоген-бота с прежними кнопками подтверждения и публикации.',
                   'duplicate':'Эта задача уже отправлялась. Повторное нажатие не запускает ещё одну генерацию.',
                   'unconfirmed':'Не удалось подтвердить приём задачи фотогенератором. Проверьте чат фотоген-бота; повторная отправка автоматически не выполняется.',
                   'no_photo':'У поставщика нет фото для генерации.',
                   'caption_too_long':'Прайс серии не помещается в подпись к фото.'}
            return show(chat_id,message_id,texts[result],[[button('⬅ К товару',f"cat:p:{p['id']}")],[button('🏠 Главное меню','cat:home')]])
        else:
            send_series(chat_id,p,int(parts[3]))
            send_message(chat_id,'Готово — фото, прайс серии и ТТХ/УТП можно переслать клиенту.',keyboard([
                [button('⬅ Изменить наценку',f"cat:c:{p['id']}")],
                [button('🎨 Карточка для канала',f"cat:q:{p['id']}:{parts[3]}",'primary')],
                [button('🏠 Главное меню','cat:home')]]))
    else: root(chat_id,message_id,data)
