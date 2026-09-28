# -*- coding: utf-8 -*-
"""Update + format 磷酸二氢钙: B1 from 川金诺 articles, B2 from prices.sci99 table."""
import sys, io, re, json, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

CREDS = r'C:\Users\DELL\.openclaw\workspace\secrets\service_account.json'
SID = '1kuN8rT9shOellupamis9iyb6CpZFaWpao4VLdzZnQQU'
SHEET_B1 = '磷酸二氢钙_云南_sci99_search'   # B1: 川金诺 articles (云南 22%)
SHEET_B2 = '磷酸二氢钙_西南_sci99'           # B2: prices.sci99 table (西南 饲料级)
HERE = os.path.dirname(os.path.abspath(__file__))
WIDTH = 17
B1_START = 0
B2_START = 21   # marker only (defaults in parse_block_row); both new tabs are full-tab
HEADER = 2      # data from R3

import newsheet_lib

def parse_date(s):
    s = str(s or '').strip()
    for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%y', '%Y.%m.%d', '%Y/%m/%d'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None

def to_mdY(d):
    return f'{d.month}/{d.day}/{d.year}'

def parse_num(s):
    if s is None:
        return None
    raw = str(s)
    s = raw.strip()
    if not s or s.lower() == 'nan':
        return None
    neg = False
    if s.startswith('(') and s.endswith(')'):
        neg = True
        s = s[1:-1].strip()
    s = s.replace(' ', '').replace('\xa0', '').replace('▼', '').replace('▲', '')
    if s.startswith('-'):
        neg = True
        s = s[1:]
    if re.fullmatch(r'-?\d{1,3}(\.\d{3})+(,\d+)?', s):
        s = s.replace('.', '').replace(',', '.')
    elif re.fullmatch(r'-?\d+,\d+', s):
        s = s.replace(',', '.')
    elif re.fullmatch(r'-?\d{1,3}(\.\d{3})+', s):
        s = s.replace('.', '')
    elif ',' in s and '.' in s:
        if s.rfind(',') > s.rfind('.'):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    elif ',' in s:
        if re.fullmatch(r'-?\d+,\d{1,3}', s):
            s = s.replace(',', '.')
        else:
            s = s.replace(',', '')
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v

def fmt_price(v):
    if v is None:
        return ''
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    s = f'{v:.2f}'.rstrip('0').rstrip('.')
    return s

def fmt_chg(v):
    if v is None:
        return ''
    if abs(v - round(v)) < 1e-9:
        iv = int(round(v))
        if iv < 0:
            return f'({abs(iv)})'
        return str(iv)
    return fmt_price(v)

def fmt_pct(v):
    if v is None:
        return ''
    s = f'{v:.2f}'.replace('.', ',')
    return s + '%'

def parse_pct(s):
    s = str(s or '').strip()
    if not s:
        return None
    s = s.replace('%', '').replace(' ', '').replace('▼', '').replace('▲', '')
    neg = s.startswith('-')
    s = s.lstrip('-').replace(',', '.')
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v

def parse_block_row(r, base):
    """Parse one block row (list starting at base col) into dict."""
    r = list(r) + [''] * WIDTH
    d = parse_date(r[0])
    if not d:
        return None
    spec = str(r[2] or '').strip()
    if spec in ('-378%', '-278%', '-378', '-278') or re.fullmatch(r'-\d+%', spec):
        spec = '22%'
    elif re.fullmatch(r'0?\.\d+', spec):   # percent-formatted number cell -> '0.22'
        try:
            spec = f'{round(float(spec) * 100)}%'
        except ValueError:
            pass
    product = str(r[1] or '').strip() or '磷酸二氢钙'
    market = str(r[3] or '').strip()
    dtype = str(r[4] or '').strip() or '市场价'
    # default identity by block base
    if base == B1_START:
        if not market:
            market = '云南'
        if not spec:
            spec = '22%'
        remark_default = '云南昆明川金诺'
    else:
        if not market:
            market = '西南'
        if not spec:
            spec = '饲料级'
        remark_default = ''
    mn, mx = parse_num(r[5]), parse_num(r[6])
    avg = parse_num(r[7])
    avg_raw = r[7] if (isinstance(r[7], str) and r[7].startswith('=')) else None
    chg = parse_num(r[8])
    pct = parse_pct(r[9])
    # rest money cols: convert EU to plain for money-like
    rest = [''] * 7  # cols 10-16 relative
    for i, j in enumerate(range(10, 17)):
        v = r[j]
        if j in (11, 12, 15):  # 折美金, 退税后, CIF
            n = parse_num(v)
            rest[i] = f'{n:.2f}' if n is not None else (str(v).strip() if v else '')
        elif j == 10:  # 汇率 — keep raw (update_fx_rate owns 4dp fill; rounding forces daily re-fill)
            rest[i] = str(v).strip() if v else ''
        elif j in (13, 14):
            n = parse_num(v)
            rest[i] = fmt_price(n) if n is not None else (str(v).strip() if v else '')
        elif j == 16:
            rest[i] = (str(v).strip() if v else '') or remark_default
        else:
            rest[i] = str(v).strip() if v else ''
    if base == B1_START and not rest[6]:
        rest[6] = remark_default
    return {
        'date': d,
        'product': product,
        'spec': spec,
        'market': market,
        'dtype': dtype,
        'min': mn,
        'max': mx,
        'avg': avg,
        'avg_raw': avg_raw,
        'chg': chg,
        'pct': pct,
        'rest': rest,  # 7 items: rate, usd, tax, port, sea, cif, remark
        'src': 'sheet',
    }

def row_to_list(rec, base):
    spec = rec['spec']
    if base == B1_START and (not spec or re.fullmatch(r'-?\d+%', spec)):
        spec = '22%'
    row = [''] * WIDTH
    row[0] = to_mdY(rec['date'])
    row[1] = rec['product'] or '磷酸二氢钙'
    row[2] = spec
    row[3] = rec['market']
    row[4] = rec['dtype'] or '市场价'
    row[5] = fmt_price(rec['min'])
    row[6] = fmt_price(rec['max'])
    row[7] = rec.get('avg_raw') or fmt_price(rec['avg'])
    row[8] = fmt_chg(rec['chg'])
    row[9] = fmt_pct(rec['pct']) if rec['pct'] is not None else ''
    rest = list(rec.get('rest') or [''] * 7)
    while len(rest) < 7:
        rest.append('')
    row[10:17] = rest[:7]
    return row

# ========== load sources ==========
print('=== load sources ===', flush=True)

# B1: articles
with open(rf'{HERE}\mcp_cjj_articles.json', encoding='utf-8') as f:
    arts = json.load(f)['articles']
b1_new = {}
for a in arts:
    m = re.search(r'卓创资讯 (2026-\d{2}-\d{2})', a.get('text', ''))
    if not m:
        continue
    d = datetime.strptime(m.group(1), '%Y-%m-%d')
    body = re.search(r'云南川金诺化工[^。\n]+。', a.get('text', ''))
    if not body:
        continue
    sentence = body.group(0)
    if '暂不报价' in sentence or '不报价' in sentence:
        continue
    pm = re.search(r'报价(\d+(?:\.\d+)?)元/吨', sentence)
    if not pm:
        continue
    price = float(pm.group(1))
    b1_new[d] = {
        'date': d, 'product': '磷酸二氢钙', 'spec': '22%', 'market': '云南',
        'dtype': '市场价', 'min': price, 'max': price, 'avg': price,
        'chg': None, 'pct': None,
        'rest': ['', '', '', '', '', '', '云南昆明川金诺'],
        'src': 'article',
    }
print(f'B1 article quoted dates: {len(b1_new)} -> {[to_mdY(d) for d in sorted(b1_new, reverse=True)]}', flush=True)

# B2: prices table
with open(rf'{HERE}\mcp_sw_price_history.json', encoding='utf-8') as f:
    sw = json.load(f)
b2_new = {}
for r in sw['tables'][0]['rows'][1:]:
    # ID, 日期, 商品名称, 市场, 生产企业, 规格型号, 价格类型, 数据类型, 最低价, 最高价, 平均价, 涨跌, 涨跌幅, 单位, 价格条件, 备注
    d = parse_date(r[1])
    if not d:
        continue
    chg_s = str(r[11] or '').strip()
    chg = parse_num(chg_s)
    pct = parse_pct(r[12])
    mn, mx, avg = parse_num(r[8]), parse_num(r[9]), parse_num(r[10])
    b2_new[d] = {
        'date': d, 'product': r[2] or '磷酸二氢钙', 'spec': r[5] or '饲料级',
        'market': r[3] or '西南', 'dtype': r[7] or '市场价',
        'min': mn, 'max': mx, 'avg': avg, 'chg': chg, 'pct': pct,
        'rest': ['', '', '', '', '', '', (r[15] or '').strip()],
        'src': 'prices',
    }
print(f'B2 table dates: {len(b2_new)} -> {[to_mdY(d) for d in sorted(b2_new, reverse=True)]}', flush=True)

# ========== read sheet ==========
creds = Credentials.from_service_account_file(CREDS, scopes=['https://www.googleapis.com/auth/spreadsheets'])
sh = gspread.authorize(creds).open_by_key(SID)

b1_map = {}  # datetime -> rec
b2_map = {}
fixed_spec = 0
eu_fixed = 0

for tab, marker, target in ((SHEET_B1, B1_START, b1_map), (SHEET_B2, B2_START, b2_map)):
    ws0 = sh.worksheet(tab)
    raw_rows = newsheet_lib.read_formula_rows(ws0, HEADER + 1, WIDTH)
    print(f'{tab}: rows={len(raw_rows)}', flush=True)
    for r in raw_rows:
        rec = parse_block_row(r, marker)
        if rec:
            # track spec fix
            old_spec = str(r[2] or '').strip()
            if old_spec != rec['spec'] and re.fullmatch(r'-?\d+%', old_spec or ''):
                fixed_spec += 1
            # count EU fix on avg
            old_avg = str(r[7] or '').strip()
            if old_avg and not old_avg.startswith('=') and parse_num(old_avg) is not None and fmt_price(parse_num(old_avg)) != old_avg:
                eu_fixed += 1
            target[rec['date']] = rec

print(f'parsed sheet B1={len(b1_map)} B2={len(b2_map)} fixed_spec~{fixed_spec} eu_avg_fixed~{eu_fixed}', flush=True)

# ========== merge sources (source overwrites same-date price fields; keep sheet USD cols) ==========
added1 = []
for d, src in b1_new.items():
    if d in b1_map:
        old = b1_map[d]
        # update prices from article if sheet missing min/max or mismatch
        if old['avg'] is None or abs((old['avg'] or 0) - src['avg']) > 0.51:
            src['rest'] = old['rest']  # keep sheet USD/remark
            src['chg'] = old['chg']
            src['pct'] = old['pct']
            b1_map[d] = src
            added1.append(('update', to_mdY(d), src['avg']))
        else:
            # fill missing min/max
            if old['min'] is None:
                old['min'] = src['min']
            if old['max'] is None:
                old['max'] = src['max']
            # fill empty chg later after sort
    else:
        b1_map[d] = src
        added1.append(('add', to_mdY(d), src['avg']))

added2 = []
for d, src in b2_new.items():
    if d in b2_map:
        old = b2_map[d]
        changed = False
        for k in ('min', 'max', 'avg', 'chg', 'pct'):
            ov, nv = old[k], src[k]
            if nv is not None and (ov is None or (isinstance(ov, float) and isinstance(nv, float) and abs(ov-nv) > 0.01) or (isinstance(ov, float) and not isinstance(nv, float))):
                if ov is None or (isinstance(ov, float) and isinstance(nv, float) and abs(ov - nv) > 0.01):
                    old[k] = nv
                    changed = True
        # also if sheet has empty min but source has it
        if old['min'] is None and src['min'] is not None:
            old['min'] = src['min']; changed = True
        if old['max'] is None and src['max'] is not None:
            old['max'] = src['max']; changed = True
        if changed:
            added2.append(('update', to_mdY(d), old['avg']))
    else:
        b2_map[d] = src
        added2.append(('add', to_mdY(d), src['avg']))

print(f'\nB1 changes ({len(added1)}):', added1, flush=True)
print(f'B2 changes ({len(added2)}):', added2, flush=True)

# ========== sort desc ==========
def sorted_recs(m):
    return sorted(m.values(), key=lambda x: x['date'], reverse=True)

b1_sorted = sorted_recs(b1_map)
b2_sorted = sorted_recs(b2_map)
# NOTE: empty chg/pct/col8/col9 are left empty on purpose — write_tab
# regenerates them as sheet formulas (=H{R-1}-H{R} pattern).

# ========== write (one tab per block) ==========
for tab, recs, marker in ((SHEET_B1, b1_sorted, B1_START), (SHEET_B2, b2_sorted, B2_START)):
    ws = sh.worksheet(tab)
    grid = [row_to_list(r, marker) for r in recs]
    print(f'\nwriting {len(grid)} rows to {tab} ...', flush=True)
    newsheet_lib.write_tab(ws, grid, HEADER + 1, WIDTH)

# ========== verify ==========
print('\n=== verify top 15 ===', flush=True)
for tab, label in ((SHEET_B1, 'B1 云南'), (SHEET_B2, 'B2 西南')):
    ws = sh.worksheet(tab)
    vals2 = ws.get_all_values()
    print(f'--- {label} ({tab}) rows={len(vals2)}', flush=True)
    for i in range(2, min(HEADER + 14, len(vals2))):
        r = vals2[i]
        b = list(r[0:17]) if len(r) >= 17 else list(r) + [''] * (17 - len(r))
        print(f'  R{i + 1}:', b[:11], flush=True)

# audit
def audit_block(rows, marker, label):
    n_dates = 0
    date_bad = 0
    price_eu = 0
    price_plain = 0
    spec_bad = 0
    dates = []
    for r in rows[HEADER:]:
        rr = list(r) + [''] * WIDTH
        blk = rr[0:WIDTH]
        d = parse_date(blk[0])
        if not d:
            continue
        n_dates += 1
        dates.append(d)
        if str(blk[0]).strip() != to_mdY(d):
            date_bad += 1
        spec = (blk[2] or '').strip()
        if marker == B1_START and spec != '22%':
            spec_bad += 1
        if marker == B2_START and spec != '饲料级':
            spec_bad += 1
        for j in (5, 6, 7, 11, 12, 15):
            v = str(blk[j] if j < len(blk) else '').strip()
            if not v or v.startswith('='):
                continue
            if re.fullmatch(r'-?\d+(\.\d+)?', v):
                price_plain += 1
            else:
                price_eu += 1
    sorted_ok = all(dates[i] >= dates[i + 1] for i in range(len(dates) - 1))
    print(f'{label}: n={n_dates} date_bad={date_bad} spec_bad={spec_bad} '
          f'price_plain={price_plain} price_odd={price_eu} sort_desc={sorted_ok} '
          f'latest={to_mdY(dates[0]) if dates else None} oldest={to_mdY(dates[-1]) if dates else None}', flush=True)

vals_b1 = sh.worksheet(SHEET_B1).get_all_values()
vals_b2 = sh.worksheet(SHEET_B2).get_all_values()
audit_block(vals_b1, B1_START, 'B1 云南')
audit_block(vals_b2, B2_START, 'B2 西南')

# show B1 latest 10 full key cols
print('\n=== B1 latest 10 (date,spec,min,max,avg,chg,pct,remark) ===', flush=True)
n = 0
for r in vals_b1[HEADER:]:
    rr = list(r) + [''] * WIDTH
    if not parse_date(rr[0]):
        continue
    print(' ', rr[0], rr[2], rr[5], rr[6], rr[7], rr[8], rr[9], rr[16][:20], flush=True)
    n += 1
    if n >= 10:
        break

print('\n=== B2 latest 10 ===', flush=True)
n = 0
for r in vals_b2[HEADER:]:
    rr = list(r) + [''] * WIDTH
    if not parse_date(rr[0]):
        continue
    print(' ', rr[0], rr[2], rr[5], rr[6], rr[7], rr[8], rr[9], flush=True)
    n += 1
    if n >= 10:
        break

print('\nDONE', flush=True)
