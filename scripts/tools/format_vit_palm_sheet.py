# -*- coding: utf-8 -*-
"""Reformat 维生素 + 棕榈油: drop future dates, EU→plain prices, M/D/YYYY, sort desc."""
import sys, io, re
from datetime import datetime, date
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
import gspread
from google.oauth2.service_account import Credentials

CREDS = r'C:\Users\DELL\.openclaw\workspace\secrets\service_account.json'
SID = '1hmDLpYOALH8-Fu4pxG-VJZURDtz3Z2UzWwTPAOs230I'
TODAY = date.today()

# (sheet, start_col0, width, layout)
BLOCKS = [
    # 维生素 standard: date,prod,spec,mkt,dtype,min,max,avg,chg,pct,rest...
    ('维生素', 19, 17, 'vit_std'),
    ('维生素', 37, 17, 'vit_std'),
    ('维生素', 55, 17, 'vit_std'),
    ('维生素', 73, 17, 'vit_std'),
    ('维生素', 91, 17, 'vit_std'),
    # D3: date,prod,mkt,producer,spec,dtype,min,max,avg,chg,pct,rest...
    ('维生素', 109, 18, 'vit_d3'),
    # 棕榈油: date,prod,spec,mkt,dtype,min,max,avg,chg,pct/note
    ('棕榈油', 0, 10, 'palm'),
    ('棕榈油', 12, 10, 'palm'),
    ('棕榈油', 24, 10, 'palm'),
]

def parse_date(s):
    s = str(s or '').strip()
    if not s:
        return None
    for fmt in ('%m/%d/%Y', '%Y/%m/%d', '%Y-%m-%d', '%m/%d/%y', '%Y.%m.%d'):
        try:
            return datetime.strptime(s, fmt).date()
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
    if not s or s.lower() == 'nan' or s in ('-', '请登录'):
        return None
    neg = False
    if s.startswith('(') and s.endswith(')'):
        neg = True
        s = s[1:-1].strip()
    # strip arrow markers
    s = s.replace('▲', '').replace('▼', '').replace('↑', '').replace('↓', '').strip()
    s = s.replace(' ', '').replace('\xa0', '')
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
    # trailing junk like '0,0 ' already stripped spaces
    s = s.rstrip('%')
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v

def fmt_plain(v):
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
    return fmt_plain(v)

def fmt_pct_str(raw):
    """Normalize percent cell to '-0,50%' style (comma decimal)."""
    raw = str(raw or '').strip()
    if not raw:
        return ''
    if not raw.endswith('%'):
        # maybe bare number that belongs in chg — only format if has comma/dot or looks pct
        if not re.search(r'[,\.\d]', raw):
            return raw
        # if pure int without % and column is pct, still try
    tmp = raw.replace('%', '').replace(' ', '').replace('\xa0', '')
    neg = False
    if tmp.startswith('(') and tmp.endswith(')'):
        neg = True
        tmp = tmp[1:-1]
    tmp = tmp.replace(',', '.')
    try:
        v = float(tmp)
    except ValueError:
        return raw
    if neg:
        v = -abs(v)
    s = f'{v:.2f}'.replace('.', ',')
    return s + '%'

def looks_pct(v):
    v = str(v or '').strip()
    return bool(v) and ('%' in v or re.fullmatch(r'-?\d+,\d+%?', v.replace(' ', '')))

def convert_rest(v):
    """Convert remaining EU-looking numerics (汇率/折美金/...) to plain."""
    if v is None:
        return ''
    s = str(v)
    if not s.strip():
        return ''
    # keep pure text
    n = parse_num(s)
    if n is None:
        return s.strip()
    # keep 2-decimal style for non-integers that look like rates
    if abs(n - round(n)) < 1e-9:
        return str(int(round(n)))
    return f'{n:.2f}'.rstrip('0').rstrip('.')

def process_block(rows, start, width, layout):
    kept = []
    dropped_future = 0
    dropped_nodate = 0
    fixed_eu = 0
    for ri, r in enumerate(rows[3:], start=4):
        rr = list(r) + [''] * (start + width - len(r))
        block = rr[start:start + width]
        if not any(str(x).strip() for x in block):
            continue
        d = parse_date(block[0])
        if not d:
            dropped_nodate += 1
            continue
        if d > TODAY:
            dropped_future += 1
            continue

        if layout == 'vit_d3':
            # 0 date,1 prod,2 mkt,3 producer,4 spec,5 dtype,6 min,7 max,8 avg,9 chg,10 pct,11+ rest
            price_idx = (6, 7, 8)
            chg_i, pct_i = 9, 10
            rest_from = 11
        elif layout == 'palm':
            price_idx = (5, 6, 7)
            chg_i, pct_i = 8, 9
            rest_from = 10
        else:
            # vit_std / standard
            price_idx = (5, 6, 7)
            chg_i, pct_i = 8, 9
            rest_from = 10

        out = list(block)
        out[0] = to_mdY(d)

        for i in price_idx:
            if i < len(out):
                n = parse_num(out[i])
                new = fmt_plain(n)
                if str(out[i]).strip() and str(out[i]).strip() != new:
                    fixed_eu += 1
                out[i] = new

        if chg_i < len(out):
            raw = out[chg_i]
            n = parse_num(raw)
            new = fmt_chg(n)
            if str(raw).strip() and str(raw).strip() != new:
                fixed_eu += 1
            out[chg_i] = new

        if pct_i < len(out):
            raw = out[pct_i]
            # palm col9 may be note text sometimes — if has % or comma-decimal, format as pct
            if raw and (('%' in str(raw)) or re.search(r'\d+[,.]\d+', str(raw))):
                new = fmt_pct_str(raw)
                if str(raw).strip() != new:
                    fixed_eu += 1
                out[pct_i] = new
            else:
                # leave plain note / blank; if pure EU number convert plain
                n = parse_num(raw)
                if n is not None and (',' in str(raw) or '.' in str(raw)):
                    out[pct_i] = fmt_plain(n)

        for i in range(rest_from, width):
            if i < len(out) and str(out[i]).strip():
                new = convert_rest(out[i])
                if str(out[i]).strip() != new:
                    fixed_eu += 1
                out[i] = new

        while len(out) < width:
            out.append('')
        kept.append((d, out[:width]))

    kept.sort(key=lambda x: x[0], reverse=True)
    # dedupe by date (keep first = already sorted, prefer non-empty prices)
    seen = set()
    grid = []
    for d, row in kept:
        k = d.isoformat()
        if k in seen:
            continue
        seen.add(k)
        grid.append(row)
    return grid, dropped_future, dropped_nodate, fixed_eu

def main():
    creds = Credentials.from_service_account_file(CREDS, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    sh = gspread.authorize(creds).open_by_key(SID)

    # group blocks by sheet
    by_sheet = {}
    for sheet, start, width, layout in BLOCKS:
        by_sheet.setdefault(sheet, []).append((start, width, layout))

    for sheet, blocks in by_sheet.items():
        ws = sh.worksheet(sheet)
        vals = ws.get_all_values()
        print(f'\n=== {sheet} rows={len(vals)} ===', flush=True)
        # clear all data regions first then write? safer: write each block independently
        for start, width, layout in blocks:
            grid, drop_f, drop_n, fix_eu = process_block(vals, start, width, layout)
            col1 = start + 1
            # determine clear range covering old data + a bit
            old_data_rows = 0
            for r in vals[3:]:
                rr = list(r) + [''] * (start + width - len(r))
                if any(str(x).strip() for x in rr[start:start + width]):
                    old_data_rows += 1
            end_row = max(4 + old_data_rows, 4 + len(grid))
            rng_a1 = gspread.utils.rowcol_to_a1(4, col1)
            rng_end = gspread.utils.rowcol_to_a1(end_row, col1 + width - 1)
            rng = f'{rng_a1}:{rng_end}'
            ws.batch_clear([rng])
            if grid:
                ws.update(grid, rng_a1, value_input_option='RAW')
            latest = grid[0][0] if grid else None
            print(f'  col{start}: layout={layout} n={len(grid)} latest={latest} drop_future={drop_f} drop_nodate={drop_n} fixed_eu~{fix_eu}', flush=True)

    # verify
    print('\n=== VERIFY top rows ===', flush=True)
    for sheet in by_sheet:
        ws = sh.worksheet(sheet)
        vals = ws.get_all_values()
        print(f'\n{sheet}:', flush=True)
        for start, width, layout in by_sheet[sheet]:
            # find header-ish first data
            r = vals[3] if len(vals) > 3 else []
            rr = list(r) + [''] * (start + width - len(r))
            block = rr[start:start + width]
            # also R4 and a future-scan
            future = 0
            eu = 0
            for row in vals[3:]:
                b = list(row) + [''] * (start + width - len(row))
                b = b[start:start + width]
                d = parse_date(b[0]) if b else None
                if d and d > TODAY:
                    future += 1
                for cell in b:
                    s = str(cell or '').strip()
                    if not s:
                        continue
                    t = s[1:-1] if s.startswith('(') and s.endswith(')') else s
                    t = t.replace(' ', '')
                    if re.fullmatch(r'-?\d{1,3}(\.\d{3})+,\d+|-?\d+,\d+', t):
                        # exclude pct cells that are intentionally comma
                        if '%' in s:
                            continue
                        # exclude pure comma decimals in text? count as eu if thousands sep
                        if re.fullmatch(r'-?\d{1,3}(\.\d{3})+,\d+', t) or re.fullmatch(r'-?\d+,\d{2}', t):
                            eu += 1
            print(f'  col{start}: R4={block[:10]} future={future} eu_price_like={eu}', flush=True)

if __name__ == '__main__':
    main()
