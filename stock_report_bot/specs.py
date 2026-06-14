"""Блок «ключевые особенности» серии для бота-меню. ЧИСТЫЕ функции — без БД и сети
(данные подаёт `db.fetch_tech_values`, УТП Бриза — `breez.fetch_breez_utp_by_nc`).

Состав согласован с владельцем (15 пунктов). Названия характеристик у Бриз/Daichi/
Русклимат разные → матчим по ключевым словам в title (как квиз сайта). Значения «сырые»
(разный регистр да/нет, Y/N, диапазоны `-15 ~ +21`, шум `18,5/25/29`) → нормализуем здесь.

Уровень — общий блок на серию: подаётся объединённый список tech-строк всех позиций серии,
для каждого пункта берётся первое подходящее/утвердительное значение (числовые — минимум
по серии: самый холодный режим, самый тихий блок).
"""
import html
import re

BREEZE_SOURCE = 'breeze'

# да/Y/1/есть/ready/опция/встроенный → «есть»; нет/no/n/0/-/отсутств → «нет».
_NEG_RE = re.compile(r'^\s*(нет|no|n|0|[-−–—]|отсут\w*|false|не\s)', re.I)
_NUM_RE = re.compile(r'-?\d+(?:[.,]\d+)?')
_CLASS_RE = re.compile(r'[A-G]\+{0,3}')


def _affirm(value):
    v = (value or '').strip()
    return bool(v) and not _NEG_RE.match(v)


def _nums(s):
    out = []
    for m in _NUM_RE.findall(s or ''):
        try:
            out.append(float(m.replace(',', '.')))
        except ValueError:
            pass
    return out


def _fmt_num(x):
    return str(int(x)) if float(x).is_integer() else ('%g' % x)


def _min_num(s):
    ns = _nums(s)
    return _fmt_num(min(ns)) if ns else None


def _class(s):
    m = _CLASS_RE.search(s or '')
    return m.group(0) if m else None


def _temp(value):
    """Минимальная (самая холодная) температура из диапазона/строки → '−15'."""
    n = _min_num(value)
    return n.replace('-', '−') if n else None   # типографский минус


def _clean_utp(raw):
    """HTML-список преимуществ (Бриз utp / Русклимат УТП) → список строк-пунктов.

    Бриз отдаёт `utp` в ДВОЙНОМ HTML-эскейпе (`&amp;#9679;`, `&lt;br&gt;`), поэтому
    unescape дважды (для Русклимата — обычный текст, второй проход безвреден)."""
    s = html.unescape(html.unescape(raw or ''))
    s = re.sub(r'<br\s*/?>', '\n', s, flags=re.I)
    s = re.sub(r'<[^>]+>', ' ', s)
    items = []
    for part in re.split(r'[;\n]+', s):
        p = part.strip().strip('•●·*-–—').strip()
        if p:
            items.append(p)
    return items


# ── доступ к tech-строкам серии ────────────────────────────────────────────
class _Tech:
    def __init__(self, rows, titles=None):
        self.rows = [((r.get('title') or ''), (r.get('value') or '').strip()) for r in rows]
        self.titles = [t for t in (titles or []) if t]

    def value(self, pattern):
        """Первое непустое значение, чей title матчит pattern."""
        rx = re.compile(pattern, re.I)
        for title, val in self.rows:
            if val and rx.search(title):
                return val
        return None


# ── экстракторы пунктов (каждый → строка для цитаты или None) ───────────────
def _energy_class(t):
    for title, val in t.rows:
        if re.search(r'нагрев|обогрев|\bcop\b|scop', title, re.I):
            continue   # нужен класс ОХЛАЖДЕНИЯ
        if re.search(r'класс.*энергоэфф|энергоэффективность|\bseer\b|eer.*класс', title, re.I):
            c = _class(val)
            if c:
                return f'⚡ Класс энергоэффективности {c}'
    return None


def _inverter(t):
    explicit_no = False
    for title, val in t.rows:
        if re.search(r'технология работы', title, re.I):
            if re.search(r'inverter|инвертор', val, re.I):
                return '❄️ Инверторная технология'
            explicit_no = True   # On/Off — явный не-инвертор
        elif re.search(r'инверторн', title, re.I):
            if _affirm(val):
                return '❄️ Инверторная технология'
            explicit_no = True
    # Запасной детектор по названию (часть товаров не имеет tech-поля инвертора),
    # но НЕ переопределяем явное «нет» из характеристик.
    if not explicit_no and any(re.search(r'инвертор|inverter', s, re.I) for s in t.titles):
        return '❄️ Инверторная технология'
    return None


def _compressor(t):
    val = t.value(r'марка компрессора')
    return f'⚙️ Компрессор {val}' if val else None


def _heat_min(t):
    nums = []
    for title, val in t.rows:
        if (re.search(r'(границ|диапазон).*нагрев', title, re.I)
                or re.search(r'мин.*температ.*(внешн|наруж)', title, re.I)):
            nums += _nums(val)
    if not nums:
        return None
    return f'🌡 Работа на обогрев до {_fmt_num(min(nums)).replace("-", "−")} °C'


def _noise_min(t):
    nums = []
    for title, val in t.rows:
        if re.search(r'шум|звуков', title, re.I) and re.search(r'внутр|вб|iu', title, re.I):
            nums += [n for n in _nums(val) if n > 0]
    return f'🔇 Уровень шума от {_fmt_num(min(nums))} дБ' if nums else None


def _warranty(t):
    val = t.value(r'гаранти')
    if not val:
        return None
    val = val.strip()
    if val.isdigit():
        val = f'{val} мес'
    return f'🛡 Гарантия {val}'


def _wifi(t):
    for title, val in t.rows:
        if re.search(r'wi[\s-]?fi|вай[\s-]?фай|облачн|удал.{0,5}управл', title, re.I):
            if not _affirm(val):
                continue
            if re.search(r'ready|опц|доп', val, re.I):
                return '📶 Wi-Fi (опция)'
            return '📶 Wi-Fi управление'
    return None


def _voice(t):
    names = []
    for title, val in t.rows:
        m = re.search(r'работает с (алис\w*|hommyn|марус\w*|салют\w*|сбер\w*)', title, re.I)
        if m and _affirm(val):
            raw = m.group(1).lower()
            name = next((v for k, v in (('алис', 'Алиса'), ('hommyn', 'HOMMYN'),
                                        ('марус', 'Маруся'), ('салют', 'Салют'),
                                        ('сбер', 'Сбер')) if raw.startswith(k)), m.group(1))
            if name not in names:
                names.append(name)
    return f'🗣 Управление голосом ({", ".join(names)})' if names else None


def _flag(t, pattern, label):
    """Утвердительный булев признак → строка label, иначе None."""
    for title, val in t.rows:
        if re.search(pattern, title, re.I) and _affirm(val):
            return label
    return None


# Порядок пунктов в цитате (как согласовано: #1,4,5,7,9,13,16,17,19,20,21,23,25,27).
_FEATURES = [
    _energy_class,
    _inverter,
    _compressor,
    _heat_min,
    _noise_min,
    _warranty,
    _wifi,
    _voice,
    lambda t: _flag(t, r'ионизатор|ионизац', '🌿 Ионизация воздуха'),
    lambda t: _flag(t, r'плазмен', '✨ Плазменная очистка'),
    lambda t: _flag(t, r'ультрафиолет|\bуф[\s-]', '☀️ УФ-обеззараживание'),
    lambda t: _flag(t, r'автоочист|самоочист', '🧼 Самоочистка'),
    lambda t: _flag(t, r'режим sleep|ночной режим', '🌙 Ночной режим (SLEEP)'),
    lambda t: _flag(t, r'авторестарт|перезапуск.*питан', '🔄 Авторестарт после отключения'),
]

# Ключевые слова уже показанных пунктов — чтобы не дублировать их из УТП.
_UTP_SKIP_RE = re.compile(
    r'wi[\s-]?fi|вай|инвертор|ионизац|плазм|ультрафиолет|\bуф\b|самоочист|автоочист|'
    r'sleep|ночн|авторестарт|класс\s|энергоэфф|гаранти|компрессор|шум|голос|алис',
    re.I,
)


def _utp_extras(t, source, utp_raw):
    """Доп. «фишки» из УТП (Бриз — из API utp_raw; Русклимат — из tech-поля «УТП»),
    кроме уже показанных пунктов. До 5 штук."""
    if source == BREEZE_SOURCE:
        items = _clean_utp(utp_raw)
    else:
        items = _clean_utp(t.value(r'^\s*утп\b'))
    out, seen = [], set()
    for it in items:
        if _UTP_SKIP_RE.search(it):
            continue
        key = it.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(f'✓ {it}')
        if len(out) >= 5:
            break
    return out


def build_specs_message(tech_rows, brand, series, source, utp_raw=None,
                        titles=None, max_len=3900):
    """Список Telegram-сообщений (HTML) с блоком-цитатой ключевых особенностей серии.

    tech_rows: [{'title','value'}] по всем позициям серии (из БД сайта).
    utp_raw: строка `utp` Бриза из Бриз API (None для прочих).
    titles: названия позиций серии — запасной детектор инвертора, когда tech-поля нет.
    Шапка — бренд+серия (поставщик/наценка НЕ раскрываются — готово к пересылке клиенту).
    """
    t = _Tech(tech_rows, titles)
    lines = [ln for extract in _FEATURES if (ln := extract(t))]
    lines += _utp_extras(t, source, utp_raw)

    head = f'💡 {html.escape(brand)} {html.escape(series)} — ключевые особенности:'
    if not lines:
        return [f'{head}\nХарактеристики уточняются.']
    body = '\n'.join(html.escape(ln) for ln in lines)
    text = f'{head}\n<blockquote>{body}</blockquote>'
    if len(text) <= max_len:
        return [text]
    # Подстраховка (блок почти всегда мал): без цитаты, режем по строкам.
    from stock_report_bot.report import _chunk_lines
    return _chunk_lines([head] + [html.escape(ln) for ln in lines], max_len)
