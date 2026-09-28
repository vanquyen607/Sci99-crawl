# -*- coding: utf-8 -*-
"""Reformat 磷酸一二钙-每周: plain prices, M/D/YYYY dates, sort desc, fix col order."""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
from datetime import datetime
from collections import Counter
import gspread
from google.oauth2.service_account import Credentials

CREDS = r'C:\Users\DELL\.openclaw\workspace\secrets\service_account.json'
SID = '1hmDLpYOALH8-Fu4pxG-VJZURDtz3Z2UzWwTPAOs230I'
SHEET = '磷酸一二钙-每周'
WIDTH = 17
HEADER = 3  # data from R4

MARKETS = {'云南', '山东', '河北', '广东', '河南', '湖北', '四川', '贵州', '中国'}
DTYPES = {'市场价', '企业报价', '区域均价', '均价'}

def parse_date(s):
    s = str(s or '').strip()
    for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%y', '%Y.%m.%d'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None

def to_mdY(d):
    return f'{d.month}/{d.day}/{d.year}'

def parse_num(s):
    """Parse EU '  5.000,00' or plain '5025' or '(25)' -> float (neg if parens)."""
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
    s = s.replace(' ', '').replace('\xa0', '')
    # EU: 5.000,00 or 5.000,00
    if re.fullmatch(r'-?\d{1,3}(\.\d{3})+(,\d+)?', s):
        s = s.replace('.', '').replace(',', '.')
    elif re.fullmatch(r'-?\d+,\d+', s):  # 0,39% style already stripped? keep
        s = s.replace(',', '.')
    elif re.fullmatch(r'-?\d{1,3}(\.\d{3})+', s):
        s = s.replace('.', '')
    elif ',' in s and '.' in s:
        # ambiguous: prefer EU if last comma after last dot
        if s.rfind(',') > s.rfind('.'):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    elif ',' in s:
        # could be decimal comma
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
    """Plain number, no thousand sep, no trailing zeros beyond need."""
    if v is None:
        return ''
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    # keep up to 2 decimals
    s = f'{v:.2f}'.rstrip('0').rstrip('.')
    return s

def fmt_pct_from_ratio(r):
    """r is float ratio like -0.005 -> '-0,50%' keep EU style used in sheet? user said price plain; pct can stay."""
    if r is None:
        return ''
    pct = r * 100
    # sheet uses comma decimal in 比例 e.g. -0,50%
    if abs(pct - round(pct, 2)) < 1e-9:
        s = f'{pct:.2f}'.rstrip('0').rstrip('.')
    else:
        s = f'{pct:.2f}'
    if '.' in s:
        s = s.replace('.', ',')
    if ',' in s:
        # ensure 2 decimal places for consistency if had decimals
        if not re.search(r',\d{2}$', s):
            s = s + '0' if s.endswith(',') else (s + '00' if ',' in s else s)
            # fix: better format directly
    return s

def fmt_pct(v):
    """v already percent number like -0.5 or 0.39 -> '-0,50%' or keep simple"""
    if v is None:
        return ''
    # format with 2 decimals, comma separator (match existing sheet style)
    s = f'{v:.2f}'  # -0.50
    s = s.replace('.', ',')
    return s + '%'

def fmt_chg(v):
    if v is None:
        return ''
    if abs(v - round(v)) < 1e-9:
        iv = int(round(v))
        if iv < 0:
            return f'({abs(iv)})'
        return str(iv)
    return fmt_price(v)

creds = Credentials.from_service_account_file(CREDS, scopes=['https://www.googleapis.com/auth/spreadsheets'])
sh = gspread.authorize(creds).open_by_key(SID)
ws = sh.worksheet(SHEET)
vals = ws.get_all_values()
print('rows', len(vals), flush=True)
print('R1', vals[0][:3] if vals else None, flush=True)
print('R3 header', vals[2][:10], flush=True)

data = []
fixed_price_cells = 0
fixed_dates = 0
odd_cols = 0

for i in range(HEADER, len(vals)):
    r = list(vals[i]) + [''] * WIDTH
    d = parse_date(r[0])
    if not d:
        # skip empty
        if any(str(c).strip() for c in r):
            print(f'skip non-date R{i+1}:', r[:5], flush=True)
        continue
    if str(r[0]).strip() != to_mdY(d):
        fixed_dates += 1

    product = (r[1] or '').strip() or '磷酸一二钙'
    spec = (r[2] or '').strip()
    if spec.lower() == 'nan':
        spec = ''

    c3, c4 = (r[3] or '').strip(), (r[4] or '').strip()
    market, dtype = c3, c4
    if c3 in DTYPES and c4 in MARKETS:
        market, dtype = c4, c3
        odd_cols += 1
    elif c3 in MARKETS and c4 in DTYPES:
        market, dtype = c3, c4
    elif c3 in MARKETS and c4 not in DTYPES:
        market, dtype = c3, (c4 or '市场价')
        odd_cols += 1
    elif c4 in MARKETS and c3 not in DTYPES:
        market, dtype = c4, (c3 or '市场价')
        odd_cols += 1
    else:
        if not market:
            market = '云南'
        if not dtype:
            dtype = '市场价'

    # prices cols 5,6,7 (min max avg)
    mn_raw, mx_raw, avg_raw = r[5], r[6], r[7]
    mn, mx, avg = parse_num(mn_raw), parse_num(mx_raw), parse_num(avg_raw)
    for orig, val in ((mn_raw, mn), (mx_raw, mx), (avg_raw, avg)):
        if orig and str(orig).strip() and (',' in str(orig) or str(orig).strip() != (fmt_price(val) if val is not None else str(orig).strip())):
            if val is not None and str(orig).strip() != fmt_price(val):
                fixed_price_cells += 1

    chg = parse_num(r[8])
    # 比例: parse ' -0,50%' or '0,39%' or '-11,30%'
    pct_raw = (r[9] or '').strip()
    pct_val = None
    if pct_raw:
        tmp = pct_raw.replace('%', '').replace(' ', '').replace('%', '')
        tmp = tmp.replace(',', '.')  # -0.50
        try:
            pct_val = float(tmp)
        except ValueError:
            pct_val = None

    # rest cols 10-16: parse numeric EU to plain for money-like cols 11,12,15; keep 10 (汇率) as comma-decimal plain; 13,14 plain int
    rest = []
    for j in range(10, WIDTH):
        v = r[j]
        if j == 10:  # 汇率 USD like 6,78 -> 6.78 plain?
            n = parse_num(v)
            rest.append(fmt_price(n) if n is not None else (v or ''))
        elif j in (11, 12, 15):  # 折美金, 退税后, CIF EU money
            n = parse_num(v)
            if n is not None:
                # keep 2 decimals for USD
                rest.append(f'{n:.2f}'.rstrip('0').rstrip('.') if abs(n-int(n))<1e-9 else f'{n:.2f}')
            else:
                rest.append(v or '')
        elif j in (13, 14):  # 拉柜, 海运费 plain
            n = parse_num(v)
            rest.append(fmt_price(n) if n is not None else (v or ''))
        elif j == 16:  # 备注
            rest.append((v or '').strip())
        else:
            rest.append(v if v is not None else '')

    # recompute 折成美金 etc? Keep as converted plain numbers (don't change logic)
    row = [
        to_mdY(d),
        product,
        spec,
        market,
        dtype,
        fmt_price(mn),
        fmt_price(mx),
        fmt_price(avg),
        fmt_chg(chg),
        fmt_pct(pct_val) if pct_val is not None else pct_raw,
    ] + rest

    # pad
    while len(row) < WIDTH:
        row.append('')

    data.append({'date': d, 'row': row})

print(f'parsed {len(data)} rows; fixed_dates~{fixed_dates} fixed_price_cells~{fixed_price_cells} odd_cols_swapped~{odd_cols}', flush=True)

# sort desc, dedupe by date
data.sort(key=lambda x: x['date'], reverse=True)
seen = set()
grid = []
for x in data:
    k = x['date'].strftime('%Y-%m-%d')
    if k in seen:
        print('dedupe drop', k, flush=True)
        continue
    seen.add(k)
    grid.append(x['row'])

print('grid', len(grid), 'latest', grid[0][:8] if grid else None, flush=True)
print('oldest', grid[-1][:8] if grid else None, flush=True)

start = HEADER + 1  # R4
old_n = sum(1 for i in range(HEADER, len(vals)) if parse_date(vals[i][0] if vals[i] else ''))
a1 = f'A{start}:Q{start + len(grid) - 1}'
print('update', a1, flush=True)
ws.update(grid, a1, value_input_option='RAW')
if old_n > len(grid):
    clear = f'A{start+len(grid)}:Q{start+old_n-1}'
    print('clear', clear, flush=True)
    ws.batch_clear([clear])

# verify
vals2 = ws.get_all_values()
print('\n=== top 12 ===', flush=True)
for i in range(HEADER - 1, min(HEADER + 11, len(vals2))):
    print(f'R{i+1}:', list(vals2[i])[:17], flush=True)

# format audit
price_pat_eu = 0
price_pat_plain = 0
date_bad = 0
col_bad = 0
n = 0
for r in vals2[HEADER:]:
    if not str(r[0]).strip():
        continue
    n += 1
    d = parse_date(r[0])
    if not d or str(r[0]).strip() != to_mdY(d):
        date_bad += 1
    for j in (5, 6, 7, 11, 12, 15):
        v = (r[j] if j < len(r) else '').strip()
        if not v:
            continue
        if re.search(r'\s\d{1,3}\.\d{3}|^\s*\d{1,3}\.\d{3},', v) or (',' in v and '.' in v.replace('.', '', 0) and re.fullmatch(r'.*\d\.\d{3},\d+.*', v)):
            price_pat_eu += 1
        elif re.fullmatch(r'-?\d+(\.\d+)?', v):
            price_pat_plain += 1
        else:
            price_pat_eu += 1  # treat as unconverted
    c3, c4 = (r[3] if len(r)>3 else '').strip(), (r[4] if len(r)>4 else '').strip()
    if c3 in MARKETS and c4 in DTYPES:
        pass
    elif c3 in DTYPES and c4 in MARKETS:
        col_bad += 1
    else:
        col_bad += 1

print(f'\naudit n={n} date_bad={date_bad} col_bad={col_bad} price_plain={price_pat_plain} price_eu_or_odd={price_pat_eu}', flush=True)

# show any remaining EU-looking in price cols
print('\nremaining non-plain price cells:', flush=True)
shown = 0
for i, r in enumerate(vals2[HEADER:], start=HEADER+1):
    for j in (5, 6, 7):
        v = (r[j] if j < len(r) else '').strip()
        if v and not re.fullmatch(r'-?\d+(\.\d+)?', v):
            print(f'  R{i} c{j}: {v!r}', flush=True)
            shown += 1
            if shown >= 20:
                break
    if shown >= 20:
        break
if shown == 0:
    print('  none — all plain', flush=True)
