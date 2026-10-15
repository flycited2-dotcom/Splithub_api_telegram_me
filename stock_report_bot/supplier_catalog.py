"""Full Breez and Daichi feeds, restricted to explicitly identified Simferopol stock."""
import html
import re
import time
from decimal import Decimal, InvalidOperation
import requests
from decouple import Config, RepositoryEnv
from stock_report_bot.config import config
from stock_report_bot import catalog

def setting(key, default=''):
    value = config(key, default='')
    source = config('SUPPLIER_ENV_FILE', default='')
    if not value and source:
        value = Config(RepositoryEnv(source))(key, default='')
    return value or default

def local_warehouse(name):
    return bool(re.search(r'симфер|симфир|бриз\s+крым', str(name), re.I))

def quantity(value):
    text = str(value or '0').replace(',', '.').strip()
    lower_bound = bool(re.search(r'[>+]|больше|более', text, re.I))
    match = re.search(r'\d+(?:\.\d+)?', text)
    if not match or text.startswith('-'): return 0, False
    return float(match.group()), lower_bound

def money(value):
    try:
        result = Decimal(str(value))
        return str(result) if result.is_finite() and result >= 0 else None
    except (InvalidOperation, ValueError): return None

def plain(value):
    text=str(value or '')
    for _ in range(5):
        decoded=html.unescape(text)
        if decoded==text: break
        text=decoded
    text=re.sub(r'<sup>\s*([23])\s*</sup>',lambda m:'²' if m[1]=='2' else '³',text,flags=re.I)
    text = re.sub(r'<br\s*/?>|</p>', '\n', text, flags=re.I)
    return re.sub(r'<[^>]+>', '', text).strip()

def entries(data):
    if isinstance(data, dict):
        return [dict(v, _id=str(k)) for k,v in data.items() if isinstance(v,dict)]
    if isinstance(data,list):
        result=[]
        for v in data:
            if not isinstance(v,dict): raise ValueError('Unexpected record')
            if len(v)==1 and isinstance(next(iter(v.values())),dict):
                k,p=next(iter(v.items())); result.append(dict(p,_id=str(k)))
            else: result.append(v)
        return result
    raise ValueError('Unexpected API response structure')

class Client:
    def __init__(self, supplier):
        self.supplier = supplier
        self.session = requests.Session()
        self.base = setting('BREEZ_BASE_URL','https://api.breez.ru/v1/') if supplier=='breez' else setting('DAICHI_BASE_URL','https://api.daichi.ru/b2b/v1/')
        self.key = setting('BREEZ_AUTH_HEADER' if supplier=='breez' else 'DAICHI_ACCESS_TOKEN')
        if not self.key: raise ValueError(f'{supplier}: API key is not configured')

    def get(self, endpoint, **params):
        headers={'Accept':'application/json'}
        if self.supplier=='breez': headers['Authorization']=self.key
        else: params['access-token']=self.key
        try:
            response=self.session.get(self.base.rstrip('/')+'/'+endpoint, params=params, headers=headers, timeout=(15,120))
            response.raise_for_status()
            data=response.json()
        except (requests.RequestException, ValueError):
            # Never propagate request URLs: Daichi puts its secret in the query.
            raise RuntimeError(f'{self.supplier}: {endpoint} request failed') from None
        if self.supplier=='daichi':
            if not isinstance(data,dict) or 'Result' not in data: raise ValueError('Daichi: missing Result')
            data=data['Result']
        if isinstance(data,dict) and ('error' in data or data.get('success') is False):
            raise ValueError(f'{self.supplier}: API reported an error')
        return data

def parse_breez(stock, products, categories, brands):
    info={str(p.get('nc')):p for p in entries(products)}
    cats={str(c.get('id',c.get('_id'))):c for c in entries(categories)}
    brands={str(b.get('id',b.get('_id'))):b.get('title','') for b in entries(brands)}
    result=[]
    for s in entries(stock):
        sku=str(s.get('nc') or s.get('nc_code') or s.get('_id') or '')
        if not sku: raise ValueError('Breez stock without SKU')
        local=[w for w in s.get('stocks',[]) if local_warehouse(w.get('stock'))]
        qty=sum(quantity(w.get('quantity'))[0] for w in local)
        if qty<=0: continue
        p=info.get(sku,{})
        cat=cats.get(str(p.get('category_id')),{})
        root=cat; seen=set()
        while str(root.get('level','0')) not in ('0','', 'None'):
            parent=str(root.get('level'))
            if parent in seen or parent not in cats: break
            seen.add(parent); root=cats[parent]
        prices={k:v for price in s.get('price',[]) if isinstance(price,dict) for k,v in price.items()}
        result.append(dict(sku=sku,title=p.get('title') or s.get('title') or sku,
            model=p.get('articul') or s.get('articul') or sku, series=p.get('series',''),
            brand=brands.get(str(p.get('brand')),''),
            group_name=root.get('title') or 'Без категории поставщика',
            kind=cat.get('title') or 'Прочие товары',quantity=qty,
            quantity_lower_bound=any(quantity(w.get('quantity'))[1] for w in local),
            warehouse=', '.join(w['stock'] for w in local),purchase_price=money(prices.get('base')),
            currency=prices.get('base_currency','RUB'),retail_price=money(prices.get('ric')),
            price_label='Закупочная base',images=p.get('images') or [],utp=plain(p.get('utp')),
            description=plain(p.get('description')),specs=[],supplier_product_id=p.get('_id'),
            raw={'stock':s,'product':p}))
    return result

def parse_daichi(data, params_map, store_id):
    result=[]
    for p in entries(data):
        store=p.get('STORE') or p.get('STORE:') or {}
        if str(store.get('XML_ID'))!=str(store_id) or not local_warehouse(store.get('NAME')):
            raise ValueError('Daichi returned an unexpected warehouse')
        qty,bound=quantity(store.get('STORE_AMOUNT'))
        if qty<=0: continue
        sku=p.get('XML_ID')
        if not sku: raise ValueError('Daichi product without XML_ID')
        attrs=p.get('PARAMS') or p.get('PARAMS:') or {}
        pp=params_map.get(sku,{})
        prices=p.get('PRICES') or p.get('PRICES:') or {}
        base=next((v for v in prices.values() if v.get('XML_ID')=='BASE'),{})
        retail=next((v for v in prices.values() if 'mprc' in str(v.get('XML_ID','')).lower()),{})
        specs=[{'title':plain(v.get('NAME') or k),'value':plain(v['VALUE'])} for k,v in pp.items()
               if k.startswith('ATTR_') and isinstance(v,dict) and v.get('VALUE') not in (None,'')]
        brand=attrs.get('BRAND',''); model=p.get('NAME') or sku
        result.append(dict(sku=sku,title=' '.join(filter(None,[brand,model])),model=model,
            brand=brand,series=attrs.get('ATTR_L_SERIA',''),
            group_name=attrs.get('ATTR_L_GOODGROUP') or 'Без категории поставщика',
            kind=attrs.get('ATTR_RUS_NAME_AX') or attrs.get('ATTR_L_GOODTYPE') or 'Прочие товары',
            quantity=qty,quantity_lower_bound=bound,warehouse=store['NAME'],
            purchase_price=money(base.get('PRICE')),currency={'RUR':'RUB'}.get(base.get('CURRENCY'),base.get('CURRENCY','RUB')),
            retail_price=money(retail.get('PRICE')),price_label='Партнёрская BASE',
            images=pp.get('PHOTOES') or pp.get('PHOTOES:') or [],utp='',description='',specs=specs,
            raw={'product':p,'params':pp}))
    return result

def fetch_breez():
    c=Client('breez')
    stock=c.get('leftoversnew/'); data=c.get('products/')
    if not stock or not data: raise ValueError('Breez empty feed; previous snapshot retained')
    rows=parse_breez(stock,data,c.get('categories/'),c.get('brands/'))
    # Specs are fetched only for products physically available in Simferopol.
    old={p['sku']:p for p in catalog.products(available=False) if p['supplier']=='breez'}
    for row in rows:
        previous=old.get(row['sku'],{})
        row['specs']=previous.get('specs',[])
        if row['specs'] or not row['supplier_product_id']: continue
        data=c.get('tech/', id=row['supplier_product_id'])
        for entry in entries(data):
            row['specs']=[{'title':v.get('title',''),'value':str(v.get('value','')),'unit':v.get('unit','')}
                          for v in (entry.get('techs') or {}).values() if isinstance(v,dict) and v.get('value') not in (None,'')]
        time.sleep(.15)
    return rows

def fetch_daichi():
    c=Client('daichi')
    stores=c.get('stores/get/')
    matches=[s for s in stores if local_warehouse(s.get('NAME'))]
    configured=setting('DAICHI_STORE_ID')
    matches=[s for s in matches if not configured or configured=='default' or s['XML_ID']==configured]
    if len(matches)!=1: raise ValueError('Daichi: cannot uniquely identify Simferopol store')
    store_id=matches[0]['XML_ID']
    data=c.get('products/get/', **{'store-id':store_id})
    if not data: raise ValueError('Daichi empty feed; previous snapshot retained')
    pp={}; seen=set()
    for page in range(1,1001):
        batch=c.get('productparams/get/', **{'page-size':500,'page':page,'show-empty-params':'false'})
        if not isinstance(batch,dict) or 'data' not in batch: raise ValueError('Daichi invalid specs page')
        values=entries(batch['data'])
        if not values: break
        keys={v.get('XML_ID') for v in values}
        if keys and keys<=seen: raise ValueError('Daichi repeated specs page')
        seen.update(keys); pp.update({v['XML_ID']:v for v in values if v.get('XML_ID')})
        if len(values)<500: break
    else: raise ValueError('Daichi specs pagination exceeded limit')
    return parse_daichi(data,pp,store_id)

def sync():
    errors=[]
    for supplier,fetch in [('breez',fetch_breez),('daichi',fetch_daichi)]:
        try:
            rows=fetch()
            catalog.replace_supplier(supplier,rows)
            print(f'{supplier}: {len(rows)} available products',flush=True)
        except Exception as exc:
            errors.append(supplier)
            print(f'{supplier}: sync failed ({type(exc).__name__}); previous snapshot retained',flush=True)
    catalog.export_json(config('CATALOG_JSON',default='output/catalog.json'))
    return errors

if __name__=='__main__':
    raise SystemExit(1 if sync() else 0)
