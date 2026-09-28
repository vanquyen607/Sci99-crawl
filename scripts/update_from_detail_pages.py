# -*- coding: utf-8 -*-
"""
Update Google Sheets from sci99 DETAIL pages (product_price.aspx).

For each target block: open detail page by diid, parse full history table
(date/min/max/avg as separate columns), add only missing dates, sort desc.
"""
import sys, io, os, re, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright

CREDS_PATH = r'C:\Users\DELL\.openclaw\workspace\secrets\service_account.json'
SPREADSHEET_ID = '1kuN8rT9shOellupamis9iyb6CpZFaWpao4VLdzZnQQU'
COOKIES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sci99_cookies.json')

import newsheet_lib

# Match sheet blocks exactly (checked against live sheets)
# One tab per series in the 2026.09.25 sheet; data starts row 3.
# NOTE: 棕榈油 = 3 tabs (天津24°/张家港52°/张家港24°), 维生素E added 2026-09-28.
TARGETS = [
    # 赖氨酸70
    {'sheet': '赖氨酸70_河北_sci99', 'product': '赖氨酸', 'spec': '含量70%', 'market': '河北', 'ppid': 12418, 'diid': 29728},
    {'sheet': '赖氨酸70_山东_sci99', 'product': '赖氨酸', 'spec': '含量70%', 'market': '山东', 'ppid': 12418, 'diid': 29738},
    # 赖氨酸98
    {'sheet': '赖氨酸98_河北_sci99', 'product': '赖氨酸', 'spec': '含量98%', 'market': '河北', 'ppid': 12418, 'diid': 29729},
    {'sheet': '赖氨酸98_山东_sci99', 'product': '赖氨酸', 'spec': '含量98%', 'market': '山东', 'ppid': 12418, 'diid': 29739},
    # 苏氨酸 (diid discovered: 河北=36690, 山东=29724)
    {'sheet': '苏氨酸_河北_sci99', 'product': '苏氨酸', 'spec': '含量98%', 'market': '河北', 'ppid': 12425, 'diid': 36690},
    {'sheet': '苏氨酸_山东_sci99', 'product': '苏氨酸', 'spec': '含量98%', 'market': '山东', 'ppid': 12425, 'diid': 29724},
    # 色氨酸: header order is 日期,产品名称,规格型号,数据类型,市场 (swap_mk)
    {'sheet': '色氨酸_sci99', 'product': '色氨酸', 'spec': '', 'market': '山东', 'ppid': 12424, 'diid': 119847, 'swap_mk': True},
    # 磷酸氢钙
    {'sheet': '磷酸氢钙_sci99', 'product': '磷酸氢钙', 'spec': '饲料级17%粉', 'market': '云南', 'ppid': 12311, 'diid': 113439},
    # 蛋氨酸
    {'sheet': '蛋氨酸_山东_sci99', 'product': '蛋氨酸', 'spec': '固体蛋氨酸', 'market': '山东', 'ppid': 12416, 'diid': 29716},
    {'sheet': '蛋氨酸_河南_sci99', 'product': '蛋氨酸', 'spec': '固体蛋氨酸', 'market': '河南', 'ppid': 12416, 'diid': 29713},
    # 维生素 (standard 17-col layout, 1 tab each)
    {'sheet': '维生素B1_sci99', 'product': '维生素B1', 'spec': '98%含量', 'market': '中国', 'ppid': 12426, 'diid': 36931},
    {'sheet': '维生素C_sci99', 'product': '维生素C', 'spec': '', 'market': '中国', 'ppid': 12427, 'diid': 68504},
    {'sheet': '维生素A_sci99', 'product': '维生素A', 'spec': '', 'market': '中国', 'ppid': 13393, 'diid': 68520},
    {'sheet': '维生素B2_sci99', 'product': '维生素B2', 'spec': '', 'market': '中国', 'ppid': 31385, 'diid': 79215},
    {'sheet': '维生素D3_sci99', 'product': '维生素D3', 'spec': '50%含量', 'market': '中国', 'ppid': 12428, 'diid': 36929},
    # new products (tabs already exist in the new sheet)
    {'sheet': '玉米蛋白粉_sci99', 'product': '玉米蛋白粉', 'spec': '', 'market': '', 'ppid': 12430, 'diid': 21076},
    {'sheet': 'DDGS_sci', 'product': 'DDGS', 'spec': '', 'market': '', 'ppid': 12414, 'diid': 76220},
    {'sheet': '鱼粉_sci99', 'product': '鱼粉', 'spec': '', 'market': '', 'ppid': 12429, 'diid': 14401},
    # 棕榈油 (3 series, one tab each) + 维生素E
    {'sheet': '棕榈油_天津24_sci99', 'product': '棕榈油', 'spec': '24°', 'market': '天津', 'ppid': 12670, 'diid': 15089},
    {'sheet': '棕榈油_张家港52_sci99', 'product': '棕榈油', 'spec': '52°', 'market': '张家港', 'ppid': 12670, 'diid': 70832},
    {'sheet': '棕榈油_张家港24_sci99', 'product': '棕榈油', 'spec': '24°', 'market': '张家港', 'ppid': 12670, 'diid': 15086},
    {'sheet': '维生素E_sci99', 'product': '维生素E', 'spec': '', 'market': '中国', 'ppid': 13394, 'diid': 68516},
]

def norm_date(s):
    s = str(s or '').strip()
    if not s:
        return ''
    for fmt in ('%Y/%m/%d', '%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%d/%m/%Y'):
        try:
            d = datetime.strptime(s, fmt)
            return f'{d.month}/{d.day}/{d.year}'
        except ValueError:
            pass
    return s

def date_key(s):
    try:
        return datetime.strptime(norm_date(s), '%m/%d/%Y')
    except Exception:
        return datetime(1900, 1, 1)

def parse_num(s):
    s = str(s or '').strip()
    if not s or s in ('-', '请登录'):
        return ''
    # remove thousands separators used in sheet: "4.000,00" or "4,000"
    s2 = s.replace(' ', '')
    if re.fullmatch(r'\d{1,3}(\.\d{3})+(,\d+)?', s2):  # 4.000,00 EU style
        s2 = s2.replace('.', '').replace(',', '.')
    elif ',' in s2 and '.' in s2:
        s2 = s2.replace(',', '')
    elif ',' in s2:
        s2 = s2.replace(',', '')
    try:
        v = float(s2)
    except ValueError:
        return s.strip()
    return str(int(v)) if v == int(v) else f'{v:.2f}'.rstrip('0').rstrip('.')

def extract_detail_rows(page, url, attempts=2):
    rows, title = [], ''
    for i in range(attempts):
        page.goto(url, wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(4000)
        rows = page.evaluate('''() => {
        const tables = document.querySelectorAll('table');
        for (const table of tables) {
            const text = table.innerText || '';
            if (text.includes('最低价') && text.includes('平均价') && text.includes('日期')) {
                const out = [];
                for (const tr of table.querySelectorAll('tr')) {
                    const cells = Array.from(tr.querySelectorAll('td, th')).map(td => td.innerText.trim());
                    if (cells.length >= 10) out.push(cells);
                }
                return out;
            }
        }
        // fallback: any table with date-like cells and >= 10 cols
        for (const table of tables) {
            const tr = table.querySelector('tr');
            if (!tr) continue;
            const cells = Array.from(tr.querySelectorAll('td, th')).map(td => td.innerText.trim());
            if (cells.length >= 10) {
                const out = [];
                for (const t of table.querySelectorAll('tr')) {
                    out.push(Array.from(t.querySelectorAll('td, th')).map(td => td.innerText.trim()));
                }
                return out;
            }
        }
        return [];
    }''')
        title = page.title()
        if rows and '403' not in (title or ''):
            return rows, title, page.url
        if i < attempts - 1:
            print(f'  fetch fail #{i+1} (title={title!r}, rows={len(rows)}) — retry in 30s')
            time.sleep(30)
    return rows, title, page.url

def fmt_eu_price(v):
    """Plain number (no EU thousands, no trailing spaces). Legacy name kept for callers."""
    if v is None or v == '':
        return ''
    s = str(v).strip().replace(' ', '').replace('\xa0', '')
    if not s:
        return ''
    # already plain-ish?
    neg = False
    if s.startswith('(') and s.endswith(')'):
        neg = True
        s = s[1:-1]
    s = s.replace('▲', '').replace('▼', '').strip()
    # parse EU if needed
    if re.fullmatch(r'-?\d{1,3}(\.\d{3})+(,\d+)?', s):
        s = s.replace('.', '').replace(',', '.')
    elif re.fullmatch(r'-?\d+,\d+', s):
        s = s.replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '')
    try:
        f = float(s)
    except ValueError:
        return str(v).strip()
    if neg:
        f = -abs(f)
    if abs(f - round(f)) < 1e-9:
        out = str(int(round(f)))
    else:
        out = f'{f:.2f}'.rstrip('0').rstrip('.')
    return out

def parse_history(raw_rows, product, market, spec, layout='standard', swap_mk=False):
    """Parse detail history rows into sheet-row dicts keyed by normalized date."""
    header = None
    data_start = 0
    for i, r in enumerate(raw_rows):
        joined = ' '.join(r)
        if '最低价' in joined and '日期' in joined:
            header = r
            data_start = i + 1
            break
    col = {
        'date': 1, 'product': 2, 'market': 3, 'spec': 5,
        'dtype': 7, 'min': 8, 'max': 9, 'avg': 10,
        'change': 11, 'pct': 12, 'producer': 4, 'notes': 15,
    }
    if header:
        for idx, h in enumerate(header):
            h = h.strip()
            if h.endswith('日期') or h == '日期':
                col['date'] = idx
            elif h == '商品名称':
                col['product'] = idx
            elif h == '市场':
                col['market'] = idx
            elif h == '生产企业':
                col['producer'] = idx
            elif h == '规格型号':
                col['spec'] = idx
            elif h == '数据类型':
                col['dtype'] = idx
            elif h == '最低价':
                col['min'] = idx
            elif h == '最高价':
                col['max'] = idx
            elif h == '平均价':
                col['avg'] = idx
            elif h == '涨跌':
                col['change'] = idx
            elif h == '涨跌幅':
                col['pct'] = idx
            elif h == '备注':
                col['notes'] = idx

    out = {}
    for r in raw_rows[data_start:]:
        if len(r) <= max(v for k, v in col.items() if k in ('date', 'min', 'max', 'avg')):
            continue
        d = norm_date(r[col['date']])
        if not re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', d):
            continue
        mkt = r[col['market']].strip() if col['market'] < len(r) else ''
        if mkt and market and mkt != market:
            continue
        prod = r[col['product']].strip() if col['product'] < len(r) and r[col['product']].strip() else product
        sp = r[col['spec']].strip() if col['spec'] < len(r) else spec
        if sp == 'nan':
            sp = spec
        dtype = r[col['dtype']].strip() if col['dtype'] < len(r) and r[col['dtype']].strip() else '市场价'
        mn = parse_num(r[col['min']]) if col['min'] < len(r) else ''
        mx = parse_num(r[col['max']]) if col['max'] < len(r) else ''
        avg = parse_num(r[col['avg']]) if col['avg'] < len(r) else ''
        ch_raw = r[col['change']].strip() if col['change'] < len(r) else ''
        ch = ch_raw.replace('▲', '').replace('▼', '').strip()
        pct = r[col['pct']].strip() if col['pct'] < len(r) else ''
        producer = r[col['producer']].strip() if col.get('producer', -1) < len(r) and col.get('producer', -1) >= 0 else ''

        if layout == 'palm':
            # 日期,产品名称,规格型号,市场,数据类型,最低价,最高价,平均价,涨跌,比例/备注
            row = [''] * 10
            row[0] = d
            row[1] = prod
            row[2] = sp
            row[3] = mkt or market
            row[4] = dtype
            row[5] = fmt_eu_price(mn)
            row[6] = fmt_eu_price(mx)
            row[7] = fmt_eu_price(avg)
            row[8] = ch
            row[9] = pct
        elif layout == 'd3':
            # 日期,产品名称,市场,生产企业,规格型号,数据类型,最低价,最高价,平均价,涨跌,比例,...
            row = [''] * 18
            row[0] = d
            row[1] = prod
            row[2] = mkt or market
            row[3] = producer
            row[4] = sp
            row[5] = dtype
            row[6] = fmt_eu_price(mn)
            row[7] = fmt_eu_price(mx)
            row[8] = fmt_eu_price(avg)
            row[9] = ch
            row[10] = pct
        else:
            # plain numbers for amino + vitamin (EU format removed)
            row = [''] * 17
            row[0] = d
            row[1] = prod
            row[2] = sp
            row[3] = mkt or market
            row[4] = dtype
            row[5] = fmt_eu_price(mn)
            row[6] = fmt_eu_price(mx)
            row[7] = fmt_eu_price(avg)
            row[8] = ch
            row[9] = pct
            if swap_mk:
                row[3], row[4] = row[4], row[3]
        out[d] = row
    return out

def read_block(rows, start, width, first_data_row=4):
    out = []
    for r in rows[first_data_row - 1:]:
        rr = list(r) + [''] * (start + width - len(r))
        block = rr[start:start + width]
        if any(str(x).strip() for x in block):
            out.append(block)
    return out

def write_block(ws, start, width, data, first_data_row=4):
    data = [list(r)[:width] + [''] * (width - len(r)) for r in data]
    data.sort(key=lambda r: date_key(r[0]) if r and r[0] else datetime(1900, 1, 1), reverse=True)
    # safety: keep first row per date (stable sort keeps new row ahead of old)
    seen = set()
    deduped = []
    for r in data:
        k = norm_date(r[0]) if r and r[0] else ''
        if k:
            if k in seen:
                continue
            seen.add(k)
        deduped.append(r)
    data = deduped
    col1 = start + 1
    end_row = max(ws.row_count, len(data) + 20)
    rng = gspread.utils.rowcol_to_a1(first_data_row, col1) + ':' + gspread.utils.rowcol_to_a1(end_row, col1 + width - 1)
    ws.batch_clear([rng])
    if data:
        ws.update(data, gspread.utils.rowcol_to_a1(first_data_row, col1), value_input_option='USER_ENTERED')
    return len(data)

def main():
    creds = Credentials.from_service_account_file(CREDS_PATH, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)

    with open(COOKIES_PATH, 'r', encoding='utf-8') as f:
        cookies = json.load(f)

    # Cache detail pages by diid (multiple targets may share a page)
    total_added = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1400, 'height': 900})
        ctx.add_cookies(cookies)
        page = ctx.new_page()
        page_cache = {}
        consec_fail = 0

        for t in TARGETS:
            diid = t['diid']
            url = f'https://prices.sci99.com/cn/product_price.aspx?diid={diid}&ppid={t["ppid"]}&cycletype=day'
            print(f"\n=== {t['sheet']} {t['market']}/{t['spec']} diid={diid} ===")

            if diid not in page_cache:
                raw, title, final_url = extract_detail_rows(page, url)
                print(f'  title={title}')
                print(f'  raw rows={len(raw)}')
                if raw:
                    print(f'  header sample: {raw[0][:12]}')
                    if len(raw) > 1:
                        print(f'  row1 sample: {raw[1][:14]}')
                page_cache[diid] = raw
                if not raw:
                    consec_fail += 1
                    if consec_fail >= 4:
                        print('  4 consecutive fetch failures (403/timeout?) — site seems blocked, aborting remaining targets')
                        break
                    continue
                consec_fail = 0
                if '请登录' in json.dumps(raw, ensure_ascii=False):
                    print('  WARNING: login required in data')
            else:
                raw = page_cache[diid]
            layout = t.get('layout', 'standard')
            history = parse_history(raw, t['product'], t['market'], t['spec'],
                                    layout=layout, swap_mk=t.get('swap_mk', False))
            print(f'  history dates: {len(history)} | latest: {sorted(history.keys(), key=date_key, reverse=True)[:5]}')

            first_data_row = t.get('first_data_row', 3)
            width = 17
            ws = sh.worksheet(t['sheet'])
            old = newsheet_lib.read_formula_rows(ws, first_data_row, width)
            existing = {norm_date(r[0]) for r in old if r and str(r[0]).strip()}

            new_rows = []
            for d, row in history.items():
                if d in existing:
                    continue
                # check any price cell non-empty (index depends on layout)
                price_idx = 5
                if not any(str(row[i]).strip() for i in range(price_idx, min(len(row), price_idx + 3))):
                    continue
                new_rows.append(row)
                existing.add(d)

            if new_rows:
                newsheet_lib.write_tab(ws, new_rows + old, first_data_row, width)
                print(f'  ADDED {len(new_rows)}: {[r[0] for r in new_rows]}')
                total_added += len(new_rows)
            elif not history:
                print(f'  WARN: fetch returned 0 dates — keeping existing {len(existing)} rows')
            else:
                print(f'  added 0 (all {len(existing)} dates already present)')

        browser.close()

    print(f'\nTOTAL_ADDED {total_added}')

if __name__ == '__main__':
    main()
