"""Independent supplier catalogue. Stable IDs, atomic snapshots, dated history."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager

from stock_report_bot.config import config

def db_path():
    return Path(config('CATALOG_DB', default='output/catalog.sqlite3'))

@contextmanager
def connect(path=None):
    path = Path(path or db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript('''
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS products (
      id TEXT PRIMARY KEY, supplier TEXT NOT NULL, sku TEXT NOT NULL,
      group_name TEXT NOT NULL, kind TEXT NOT NULL, brand TEXT, title TEXT,
      quantity REAL NOT NULL, purchase_price TEXT, currency TEXT, updated_at TEXT,
      payload TEXT NOT NULL, UNIQUE(supplier,sku));
    CREATE INDEX IF NOT EXISTS product_navigation ON products(group_name,kind,brand);
    CREATE TABLE IF NOT EXISTS snapshots (
      run_id TEXT, supplier TEXT, sku TEXT, quantity REAL, price TEXT, currency TEXT,
      PRIMARY KEY(run_id,supplier,sku));
    CREATE TABLE IF NOT EXISTS sync_status (
      supplier TEXT PRIMARY KEY, updated_at TEXT NOT NULL, product_count INTEGER);
    ''')
    try:
        with db:
            yield db
    finally:
        db.close()

def stable_id(supplier, sku):
    return hashlib.sha256(f'{supplier}:{sku}'.encode()).hexdigest()[:24]

def replace_supplier(supplier, rows, path=None):
    """Caller validates full API responses before committing; failures retain old data."""
    stamp = datetime.now(timezone.utc).isoformat()
    with connect(path) as db:
        db.execute('DELETE FROM products WHERE supplier=?', (supplier,))
        for row in rows:
            row = dict(row, supplier=supplier, updated_at=stamp)
            row['id'] = stable_id(supplier, row['sku'])
            db.execute('INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', (
                row['id'], supplier, row['sku'], row['group_name'], row['kind'],
                row.get('brand',''), row['title'], row['quantity'], row.get('purchase_price'),
                row.get('currency','RUB'), stamp, json.dumps(row, ensure_ascii=False)))
            db.execute('INSERT INTO snapshots VALUES (?,?,?,?,?,?)', (
                stamp, supplier, row['sku'], row['quantity'], row.get('purchase_price'), row.get('currency','RUB')))
        db.execute('INSERT OR REPLACE INTO sync_status VALUES (?,?,?)', (supplier,stamp,len(rows)))

def products(path=None, available=True):
    with connect(path) as db:
        where = 'WHERE quantity>0' if available else ''
        return [json.loads(r['payload']) for r in db.execute(
            f'SELECT payload FROM products {where} ORDER BY group_name,kind,brand,title,supplier,sku')]

def product(pid, path=None):
    with connect(path) as db:
        row = db.execute('SELECT payload FROM products WHERE id=?', (pid,)).fetchone()
        return json.loads(row['payload']) if row else None

def status(path=None):
    with connect(path) as db:
        return [dict(r) for r in db.execute('SELECT * FROM sync_status ORDER BY supplier')]

def export_json(path, database=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps({'schema_version':1, 'sources':status(database),
                              'products':products(database)}, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)
