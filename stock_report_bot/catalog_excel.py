"""Portable server-side XLSX export; no Office/Node installation required."""
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

HEADERS=['Группа','Вид товара','Бренд','Модель','Поставщик','Артикул','Склад',
         'Остаток','Количество указано','Цена поставщика','Валюта','Тип цены','РРЦ / МПРЦ','Обновлено','Фото']

def col(n):
    value=''
    while n:
        n,r=divmod(n-1,26); value=chr(65+r)+value
    return value

def cell(value, ref, style=0):
    if isinstance(value,(int,float)):
        return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'
    text=escape(''.join(c for c in str(value or '') if ord(c)>=32 or c in '\n\t'))
    return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'

def export_xlsx(rows, path):
    rows=sorted(rows,key=lambda p:tuple(str(p.get(k,'')) for k in ('group_name','kind','brand','model','supplier','sku')))
    values=[HEADERS]
    for p in rows:
        values.append([p['group_name'],p['kind'],p.get('brand'),p.get('model'),p['supplier'],p['sku'],
                       p['warehouse'],p['quantity'],'Не менее' if p.get('quantity_lower_bound') else 'Точно',
                       float(p['purchase_price']) if p.get('purchase_price') is not None else None,
                       p.get('currency'),p.get('price_label'),
                       float(p['retail_price']) if p.get('retail_price') is not None else None,
                       p['updated_at'],next(iter(p.get('images') or []),'')])
    counts=defaultdict(lambda:[0,0])
    for p in rows:
        key=(p['group_name'],p['kind'],p['supplier'])
        counts[key][0]+=1; counts[key][1]+=p['quantity']
    summary=[['Группа','Вид товара','Поставщик','Позиций','Остаток (не менее при лимитах)']]
    summary += [list(key)+value for key,value in sorted(counts.items())]
    sheets=[('Сводка',summary),('Остатки',values)]
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    with ZipFile(temporary,'w',ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'+''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,3))+'</Types>')
        z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>' for i,(name,_) in enumerate(sheets,1))+'</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,3))+'<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr('xl/styles.xml','<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF173B52"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="3"><xf fontId="0" fillId="0" borderId="0"/><xf fontId="1" fillId="2" borderId="0" applyAlignment="1"><alignment wrapText="1" vertical="center"/></xf><xf numFmtId="4" fontId="0" fillId="0" borderId="0" applyNumberFormat="1"/></cellXfs></styleSheet>')
        for i,(_,matrix) in enumerate(sheets,1):
            end=f'{col(len(matrix[0]))}{len(matrix)}'
            widths=[48,64,22,48,16,42,22,12,20,20,12,24,20,30,60] if i==2 else [48,66,16,12,42]
            body=''.join(f'<row r="{r}" ht="{34 if r==1 else 18}" customHeight="1">'+''.join(cell(v,f'{col(c)}{r}',1 if r==1 else 2 if isinstance(v,float) and i==2 and c in (10,13) else 0) for c,v in enumerate(line,1))+'</row>' for r,line in enumerate(matrix,1))
            cols=''.join(f'<col min="{c}" max="{c}" width="{w}" customWidth="1"/>' for c,w in enumerate(widths,1))
            z.writestr(f'xl/worksheets/sheet{i}.xml',f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:{end}"/><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>{cols}</cols><sheetData>{body}</sheetData><autoFilter ref="A1:{end}"/></worksheet>')
    temporary.replace(path)
    return path
