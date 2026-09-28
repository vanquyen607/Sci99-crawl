# -*- coding: utf-8 -*-
"""Update 乳清粉_sci99 from sci99 articles (天津港乳清粉价格动态, weekly).

Fetch search pages for 乳清粉, keep price-dynamic articles, parse the price
range out of each article's raw HTML (content is present in raw HTML even
though the rendered page shows a paywall teaser). Rebuilds the tab to the
standard 17-col layout on first run.
"""
import sys
import io
import os
import re
import json
import time
from urllib.parse import quote

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
from playwright.sync_api import sync_playwright
import gspread
from google.oauth2.service_account import Credentials

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import newsheet_lib as NS

SHEET_ID = '1kuN8rT9shOellupamis9iyb6CpZFaWpao4VLdzZnQQU'
TAB = '乳清粉_sci99'
WIDTH = 17
SEARCH_PAGES = 4
COOKIES = os.path.join(HERE, 'sci99_cookies.json')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')


def search_article_paths(page):
    """Search results are server-rendered page 1; pages 2+ are switched by
    clicking the JS pager (li.link-btn[data-current=N])."""
    base = 'https://www.sci99.com/search.html?keyword=' + quote('乳清粉')
    paths = []
    for attempt in range(3):
        try:
            page.goto(base, wait_until='domcontentloaded', timeout=40000)
            break
        except Exception as e:
            print(f'  search goto err {attempt}: {str(e)[:80]}')
            time.sleep(5)
    page.wait_for_timeout(3000)
    for pn in range(1, SEARCH_PAGES + 1):
        if pn > 1:
            try:
                page.click(f'ul.link-list li.link-btn[data-current="{pn}"]', timeout=8000)
                page.wait_for_timeout(3000)
            except Exception as e:
                print(f'  pager p{pn} click err: {str(e)[:80]}')
                continue
        found = page.evaluate('''() => {
            const out = [];
            document.querySelectorAll('a[onclick]').forEach(a => {
                const t = (a.innerText||'').replace(/\\s+/g,' ').trim();
                const oc = a.getAttribute('onclick')||'';
                const m = oc.match(/jumpToPath\\(encodeURI\\('([^']+)'\\)\\)/);
                if (m && t) out.push({t, path: m[1]});
            });
            return out;
        }''')
        new = 0
        for f in found:
            if ('乳清粉' in f['t'] and '价格动态' in f['t']
                    and f['path'] not in [x['path'] for x in paths]):
                paths.append(f)
                new += 1
        print(f'  search p{pn}: +{new} total={len(paths)}')
    return paths


def parse_article(page, path):
    url = 'https://www.sci99.com' + path.split('?')[0]
    for attempt in range(3):
        try:
            resp = page.request.get(url, timeout=30000)
            if resp.ok:
                break
        except Exception as e:
            print(f'  get err {attempt}: {str(e)[:80]}')
            time.sleep(5)
    else:
        return None
    html = resp.text()
    # date: first full ISO date before the content div (fallback: whole doc)
    idx = html.find('news_content')
    pre = html[:idx] if idx >= 0 else html
    m = re.search(r'20\d{2}-\d{2}-\d{2}', pre) or re.search(r'20\d{2}-\d{2}-\d{2}', html)
    if not m:
        print(f'  no date: {url}')
        return None
    date_iso = m.group(0)
    y, mo, d = date_iso.split('-')
    date_s = f'{int(mo)}/{int(d)}/{y}'
    if idx < 0:
        print(f'  no content: {url}')
        return None
    frag = re.sub(r'<[^>]+>', ' ', html[idx: idx + 4000])
    frag = re.sub(r'\s+', ' ', frag)
    lo = hi = None
    for pat in (r'低蛋白[^。；]{0,60}?(\d{4,5})-(\d{4,5})元/吨',
                r'低蛋白报价\s*(\d{4,5})-(\d{4,5})\s*[，,]',
                r'主流价格为\s*(\d{4,5})-(\d{4,5})元/吨',
                r'报价\s*(\d{4,5})-(\d{4,5})(?:元/吨|[，,])',
                r'(\d{4,5})-(\d{4,5})元/吨'):
        m = re.search(pat, frag)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            break
    if lo is None:
        m = re.search(r'报价\s*(\d{4,5})元/吨', frag)
        if m:
            lo = hi = int(m.group(1))
    if lo is None:
        print(f'  no price: {url} :: {frag[:160]}')
        return None
    spec = '低蛋白'
    mm = re.search(r'(低蛋白|优级|标准)', frag)
    if mm:
        spec = mm.group(1)
    avg = round((lo + hi) / 2, 2)
    print(f'  {date_s} {spec} {lo}-{hi} avg={avg}')
    return [date_s, '乳清粉', spec, '天津', '', lo, hi, avg] + [''] * 9


def rebuild_existing(ws):
    """Keep existing rows (17-col layout); preserve K/汇率 so the later fx
    step only has to heal genuinely new rows."""
    hdr = ws.row_values(2)
    upgraded = len(hdr) > 16 and str(hdr[16]).strip() == '备注'
    old = NS.read_formula_rows(ws, 3, 17)
    out = []
    for r in old:
        d = NS.date_text(r[0])
        if not d:
            continue
        lo, hi = r[5], r[6]
        avg = r[7]
        if isinstance(avg, str) and avg.startswith('='):
            try:
                avg = (float(str(lo).replace(',', '')) + float(str(hi).replace(',', ''))) / 2
            except (ValueError, TypeError):
                avg = ''
        k = ''
        if upgraded:
            remark = r[16] if len(r) > 16 and not str(r[16]).startswith('=') else ''
            k = r[10] if len(r) > 10 and not str(r[10]).startswith('=') else ''
        else:
            remark = r[9] if len(r) > 9 and not str(r[9]).startswith('=') else ''
        if str(remark).strip() == str(k):   # fx value previously written into the remark col
            remark = ''
        out.append([d, '乳清粉', r[2] or '低蛋白', r[3] or '天津', '', lo, hi, avg,
                    '', '', k] + [''] * 5 + [remark])
    return out


def main():
    creds = Credentials.from_service_account_file(
        r'C:\Users\DELL\.openclaw\workspace\secrets\service_account.json',
        scopes=['https://www.googleapis.com/auth/spreadsheets'])
    sh = gspread.authorize(creds).open_by_key(SHEET_ID)
    ws = sh.worksheet(TAB)

    existing = rebuild_existing(ws)
    have_dates = {r[0] for r in existing}

    fetched = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA, viewport={'width': 1440, 'height': 1000})
        if os.path.exists(COOKIES):
            with open(COOKIES, encoding='utf-8') as f:
                cks = json.load(f)
            ctx.add_cookies([{'name': c['name'], 'value': c['value'],
                              'domain': c.get('domain', '.sci99.com'),
                              'path': c.get('path', '/')} for c in cks])
        page = ctx.new_page()
        paths = search_article_paths(page)
        print(f'articles: {len(paths)}')
        for i, item in enumerate(paths):
            row = parse_article(page, item['path'])
            if row:
                fetched.append(row)
                if row[0] in have_dates:
                    # search list is newest-first: everything after this is older
                    print(f'  early-stop at {row[0]} ({len(paths) - i - 1} older skipped)')
                    break
            time.sleep(0.3)
        browser.close()

    rows = fetched + existing          # fetched wins on same date
    NS.carry_over(rows, existing)      # keep K/备注 from old rows
    ded = NS.dedupe_sorted(rows, WIDTH)
    NS.stamp_formulas(ded)
    print(f'rows to write: {len(ded)} (fetched={len(fetched)} existing={len(existing)})')

    ws.update([NS.STD_HEADER], 'A2', value_input_option='RAW')   # upgrade header
    n, changed = NS.write_tab(ws, ded, 3, WIDTH)
    print(f'write_tab: n={n} changed={changed}')
    print('DONE whey')


if __name__ == '__main__':
    main()
