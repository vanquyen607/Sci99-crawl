# -*- coding: utf-8 -*-
"""Update 发酵豆粕_mysteel from the mysteel chart API (营口市 daily series).

The daily price-table articles on m.mysteel.com are login-walled, but the
public trend chart on the hot page exposes full values via JSONP:
  seo.mysteel.com/xpic/getTrendValueByCodeAndTime?indexCode=ID01213983&type=103
type=103 -> 1 year of daily points (fallback: 6 -> 90d, 2 -> 15d).
Rebuilds the tab to the standard 17-col layout on first run.
"""
import sys
import io
import os
import re
import json
import time
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
import requests
import gspread
from google.oauth2.service_account import Credentials

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import newsheet_lib as NS

SHEET_ID = '1kuN8rT9shOellupamis9iyb6CpZFaWpao4VLdzZnQQU'
TAB = '发酵豆粕_mysteel'
WIDTH = 17
INDEX_CODE = 'ID01213983'
TYPES = (103, 6, 2)   # 1y, 90d, 15d
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')


def fetch_series():
    last_err = None
    for t in TYPES:
        u = ('https://seo.mysteel.com/xpic/getTrendValueByCodeAndTime'
             f'?callback=cb&indexCode={INDEX_CODE}&type={t}&_={int(time.time() * 1000)}')
        for attempt in range(3):
            try:
                r = requests.get(u, headers={'User-Agent': UA, 'Referer': 'https://m.mysteel.com/'},
                                 timeout=25)
                m = re.search(r'\((\{.*\})\)', r.text)
                if not m:
                    raise ValueError(f'no jsonp: {r.text[:120]}')
                d = json.loads(m.group(1))
                ys = d['datas'][0]['yAxis']
                xs = d['xAxis']
                if not ys:
                    raise ValueError('empty series')
                print(f'type={t}: {len(ys)} points {xs[0]}..{xs[-1]} last={ys[-1]}')
                return list(zip(xs, ys))
            except Exception as e:
                last_err = e
                print(f'type={t} attempt {attempt}: {e}')
                time.sleep(4)
    raise RuntimeError(f'chart fetch failed: {last_err}')


def to_row(date_iso, val):
    try:
        d = datetime.strptime(date_iso, '%Y-%m-%d')
    except ValueError:
        return None
    try:
        price = float(val)
        if price == int(price):
            price = int(price)
    except (ValueError, TypeError):
        return None
    date_s = f'{d.month}/{d.day}/{d.year}'
    return ([date_s, '发酵豆粕', '50%', '营口', '市场价', '', '', price]
            + [''] * 8 + [''])


def rebuild_existing(ws):
    """Keep existing rows; preserve K/汇率 (legacy stub had 备注 at col10,
    upgraded layout at col16 — an fx value may have leaked there)."""
    hdr = ws.row_values(2)
    upgraded = len(hdr) > 16 and str(hdr[16]).strip() == '备注'
    old = NS.read_formula_rows(ws, 3, 17)
    out = []
    for r in old:
        d = NS.date_text(r[0])
        if not d:
            continue
        k = ''
        if upgraded:
            remark = r[16] if len(r) > 16 and not str(r[16]).startswith('=') else ''
            k = r[10] if len(r) > 10 and not str(r[10]).startswith('=') else ''
        else:
            remark = r[10] if len(r) > 10 and not str(r[10]).startswith('=') else ''
        rs = str(remark).strip() if remark is not None else ''
        try:
            float(rs)      # stale fx rate leaked into the remark col
            rs = ''
        except (ValueError, TypeError):
            pass
        remark = rs
        out.append([d, r[1] or '发酵豆粕', r[2] or '50%', r[3] or '营口',
                    r[4] or '市场价', '', '', r[7], '', '', k] + [''] * 5 + [remark])
    return out


def main():
    creds = Credentials.from_service_account_file(
        r'C:\Users\DELL\.openclaw\workspace\secrets\service_account.json',
        scopes=['https://www.googleapis.com/auth/spreadsheets'])
    sh = gspread.authorize(creds).open_by_key(SHEET_ID)
    ws = sh.worksheet(TAB)

    series = fetch_series()
    fetched = [row for row in (to_row(d, v) for d, v in series) if row]
    print(f'fetched rows: {len(fetched)}')

    existing = rebuild_existing(ws)
    rows = fetched + existing
    NS.carry_over(rows, existing)   # fetched wins on price; keep K/备注 from old rows
    ded = NS.dedupe_sorted(rows, WIDTH)
    NS.stamp_formulas(ded)
    print(f'rows to write: {len(ded)} (fetched={len(fetched)} existing={len(existing)})')

    ws.update([NS.STD_HEADER], 'A2', value_input_option='RAW')
    n, changed = NS.write_tab(ws, ded, 3, WIDTH)
    print(f'write_tab: n={n} changed={changed}')
    print('DONE fsb')


if __name__ == '__main__':
    main()
