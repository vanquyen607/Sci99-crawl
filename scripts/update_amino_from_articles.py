# -*- coding: utf-8 -*-
"""Update 精氨酸 / 异亮氨酸 / 缬氨酸 from recent 和谐通 amino acid articles."""
import sys, io, re, os, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright

CREDS = r'C:\Users\DELL\.openclaw\workspace\secrets\service_account.json'
SID = '1kuN8rT9shOellupamis9iyb6CpZFaWpao4VLdzZnQQU'
COOKIES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sci99_cookies.json')

import newsheet_lib

ARTICLES = [
    'https://www.sci99.com/info/3_1000008_45667839.html',  # 2026-09-28
    'https://www.sci99.com/info/3_1000008_45655299.html',  # 2026-09-24
]

PRODUCTS = {
    '缬氨酸': {'kw': '缬氨酸', 'spec': '98%', 'market': '国产', 'width': 17},
    '精氨酸': {'kw': '精氨酸', 'spec': '99%', 'market': '希杰', 'width': 17},
    '异亮氨酸': {'kw': '异亮氨酸', 'spec': '99%', 'market': '国产', 'width': 17},
}
# new-sheet tab names (None = no tab in the 2026.09.25 sheet yet -> skipped)
TABS = {
    '缬氨酸': '缬氨酸_sci99_search',
    '精氨酸': '精氨酸',
    '异亮氨酸': '异亮氨酸',
}

def norm_date(s):
    s = (s or '').strip()
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%m/%d/%y'):
        try:
            d = datetime.strptime(s, fmt)
            return f'{d.month}/{d.day}/{d.year}'
        except ValueError:
            pass
    return ''

def date_key(s):
    try:
        return datetime.strptime(norm_date(s), '%m/%d/%Y')
    except Exception:
        return datetime(1900, 1, 1)

def parse_price_range(s):
    s = (s or '').strip()
    if not s or s == '-':
        return '', '', ''
    # "11-11.5" or "20-22" or single
    parts = re.split(r'\s*-\s*', s)
    try:
        if len(parts) >= 2:
            mn, mx = float(parts[0]), float(parts[-1])
        else:
            mn = mx = float(parts[0])
    except ValueError:
        return '', '', ''
    avg = round((mn + mx) / 2, 2)

    def fmt(v):
        return str(int(v)) if float(v).is_integer() else str(v)
    return fmt(mn), fmt(mx), fmt(avg)

def fetch_articles():
    cookies = []
    if os.path.exists(COOKIES):
        with open(COOKIES, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
    extracted = {name: {} for name in PRODUCTS}  # name -> date -> row
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1400, 'height': 900})
        if cookies:
            try:
                ctx.add_cookies(cookies)
            except Exception:
                pass
        page = ctx.new_page()
        for url in ARTICLES:
            try:
                art_date = None
                for attempt in range(2):
                    page.goto(url, wait_until='domcontentloaded', timeout=30000)
                    page.wait_for_timeout(2000)
                    title = page.title()
                    text = page.evaluate('() => document.body.innerText')
                    dm = re.search(r'卓创资讯\s+(\d{4}-\d{2}-\d{2})', text) or re.search(r'(\d{4}-\d{2}-\d{2})', text)
                    if dm:
                        art_date = norm_date(dm.group(1))
                        break
                    if attempt == 0 and ('403' in (title or '') or '403 Forbidden' in text[:120]):
                        print('  403 on article — retry in 30s')
                        time.sleep(30)
                        continue
                    break
                if not art_date:
                    print('no date for', url)
                    continue
                lines = text.split('\n')
                for name, cfg in PRODUCTS.items():
                    for i, line in enumerate(lines):
                        if cfg['kw'] in line and cfg['spec'] in line:
                            # price usually in same line after package, e.g. 缬氨酸（98%）\t25kg\t11-11.5
                            # or next lines
                            m = re.search(r'(\d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?)\s*$', line.strip())
                            if not m and i + 1 < len(lines):
                                # try combining with next
                                combined = line + ' ' + lines[i + 1]
                                m = re.search(r'(\d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?)', combined)
                            if not m:
                                # broader: any range not 25kg
                                m = re.search(r'(?<!\d)(\d{1,2}(?:\.\d+)?\s*-\s*\d{1,2}(?:\.\d+)?)(?!\d)', line)
                            if m:
                                price = m.group(1)
                                if price.startswith('25'):
                                    continue
                                mn, mx, avg = parse_price_range(price)
                                if not mn:
                                    continue
                                row = [''] * cfg['width']
                                row[0] = art_date
                                row[1] = name
                                row[2] = cfg['spec']
                                row[3] = cfg['market']
                                row[4] = '市场均价'
                                row[5] = mn
                                row[6] = mx
                                row[7] = avg
                                extracted[name][art_date] = row
                                print(f'{name} {art_date}: {price} -> min={mn} max={mx} avg={avg}')
                            break
            except Exception as e:
                print('article err', url, e)
        browser.close()
    return extracted

def update_sheet(name, new_by_date, width):
    tab = TABS.get(name)
    if not tab:
        print(f'{name}: SKIP (no tab in new sheet)')
        return 0
    creds = Credentials.from_service_account_file(CREDS, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    sh = gspread.authorize(creds).open_by_key(SID)
    ws = sh.worksheet(tab)
    old = newsheet_lib.read_formula_rows(ws, 3, width)
    existing = set()
    for r in old:
        d = norm_date(r[0])
        if d:
            existing.add(d)
    added = []
    final_rows = []
    for d, row in new_by_date.items():
        if d in existing:
            continue
        rr = list(row) + [''] * (width - len(row))
        final_rows.append(rr)
        added.append(d)
        existing.add(d)
    newsheet_lib.write_tab(ws, final_rows + old, 3, width)
    print(f'{tab}: added {len(added)} {sorted(added, key=date_key, reverse=True)}; total {len(final_rows) + len(old)}')
    return len(added)

def main():
    print('Fetching articles...')
    extracted = fetch_articles()
    total = 0
    for name, new_by_date in extracted.items():
        if not new_by_date:
            print(name, 'no data')
            continue
        total += update_sheet(name, new_by_date, PRODUCTS[name]['width'])
    print('TOTAL_ADDED', total)

if __name__ == '__main__':
    main()
