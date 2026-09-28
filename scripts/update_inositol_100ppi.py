# -*- coding: utf-8 -*-
"""Update 肌醇_国产_100ppi from www.100ppi.com mprice list (plist-1-7598-N.html).

Tracked series: 肌醇 / 99% / 湖北 (山东宏洋化学). The site blocks plain
requests, so pages are read via headless Chromium. Paginate until a page has
no 肌醇 rows. Rebuilds the tab to the standard 17-col layout on first run.
"""
import sys
import io
import os
import re
import time
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
from playwright.sync_api import sync_playwright
import gspread
from google.oauth2.service_account import Credentials

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import newsheet_lib as NS

SHEET_ID = '1kuN8rT9shOellupamis9iyb6CpZFaWpao4VLdzZnQQU'
TAB = '肌醇_国产_100ppi'
WIDTH = 17
MAX_PAGES = 40
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')


def fetch_rows(page, stop_iso=None):
    """stop_iso: latest ISO date already on the sheet — stop once a page's
    newest series row is not newer than that (list is newest-first)."""
    rows = []
    empty_streak = 0
    for pn in range(1, MAX_PAGES + 1):
        url = f'https://www.100ppi.com/mprice/plist-1-7598-{pn}.html'
        ok = False
        for attempt in range(3):
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=35000)
                ok = True
                break
            except Exception as e:
                print(f'  p{pn} goto err {attempt}: {str(e)[:70]}')
                time.sleep(4)
        if not ok:
            print(f'  p{pn}: give up, stopping')
            break
        page.wait_for_timeout(1800)
        data = page.evaluate('''() => {
            const rows = [];
            document.querySelectorAll('table tr').forEach(tr => {
                const cells = [];
                tr.querySelectorAll('th,td').forEach(td => cells.push((td.innerText||'').trim()));
                if (cells.length) rows.push(cells);
            });
            return rows;
        }''')
        series = [r for r in data if len(r) >= 8 and r[0] == '肌醇' and r[1] == '99%' and r[2] == '湖北']
        print(f'  p{pn}: rows={len(data)} series={len(series)}')
        if not series:
            empty_streak += 1
            if empty_streak >= 2:
                break
            continue
        empty_streak = 0
        rows.extend(series)
        if stop_iso:
            page_max = max((r[7] for r in series if len(r) > 7), default='')
            if page_max and page_max <= stop_iso:
                print(f'  p{pn}: page max {page_max} <= sheet max {stop_iso}, stop')
                break
    return rows


def to_row(r):
    """['肌醇','99%','湖北','48000元/吨','市场价','山东省','山东宏洋化学...','2026-09-24']"""
    m = re.search(r'([\d.]+)\s*元/吨', r[3])
    if not m:
        return None
    price = float(m.group(1))
    if price == int(price):
        price = int(price)
    try:
        d = datetime.strptime(r[7], '%Y-%m-%d')
    except ValueError:
        return None
    date_s = f'{d.month}/{d.day}/{d.year}'
    trader = r[6].split('\n')[0].replace('有限公司', '').strip()
    return ([date_s, '肌醇', '99%', '湖北', r[4] or '市场价', '', '', price]
            + [''] * 8 + [trader])


def rebuild_existing(ws):
    """Keep existing rows; preserve K/汇率. Remark = trader — col16 once the
    tab is upgraded (legacy stub had it at col10); restore the constant trader
    where an fx value had leaked into the remark column."""
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
        if rs == '':
            rs = '山东宏洋化学'
        remark = rs
        avg = r[7]
        out.append([d, r[1] or '肌醇', r[2] or '99%', r[3] or '湖北',
                    r[4] or '市场价', '', '', avg, '', '', k] + [''] * 5 + [remark])
    return out


def main():
    creds = Credentials.from_service_account_file(
        r'C:\Users\DELL\.openclaw\workspace\secrets\service_account.json',
        scopes=['https://www.googleapis.com/auth/spreadsheets'])
    sh = gspread.authorize(creds).open_by_key(SHEET_ID)
    ws = sh.worksheet(TAB)

    existing = rebuild_existing(ws)
    stop_iso = None
    if existing:
        isos = []
        for r in existing:
            try:
                isos.append(datetime.strptime(r[0], '%m/%d/%Y').strftime('%Y-%m-%d'))
            except (ValueError, TypeError):
                pass
        if isos:
            stop_iso = max(isos)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(user_agent=UA).new_page()
        raw = fetch_rows(page, stop_iso=stop_iso)
        browser.close()

    fetched = []
    for r in raw:
        row = to_row(r)
        if row:
            fetched.append(row)
    print(f'fetched series rows: {len(fetched)}')

    rows = fetched + existing
    NS.carry_over(rows, existing)   # fetched wins on price; keep K/备注 from old rows
    ded = NS.dedupe_sorted(rows, WIDTH)
    NS.stamp_formulas(ded)
    print(f'rows to write: {len(ded)} (fetched={len(fetched)} existing={len(existing)})')

    ws.update([NS.STD_HEADER], 'A2', value_input_option='RAW')
    n, changed = NS.write_tab(ws, ded, 3, WIDTH)
    print(f'write_tab: n={n} changed={changed}')
    print('DONE inositol')


if __name__ == '__main__':
    main()
