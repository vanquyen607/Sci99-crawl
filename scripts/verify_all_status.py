# -*- coding: utf-8 -*-
"""Verify recent rows + status of every data tab in BOTH spreadsheets.

old = 1kuN8...  33 tabs written by the legacy per-product scripts (dates are M/D/YYYY text)
raw = 1pnDkB... 50 data tabs + 3 index tabs written by scripts/update_raw_*.py
                (dates are serial numbers, 汇率/USD in a formula column)

Reads are batched: 1 worksheets() call per sheet plus values_batch_get in
chunks of 30 ranges, so a full check costs ~6 read calls instead of ~90.

Import-safe: collect_all() returns the data, main() prints the text report
(the GUI dashboard calls collect_all() itself).
"""
import sys, io, time
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials

OLD_SID = '1kuN8rT9shOellupamis9iyb6CpZFaWpao4VLdzZnQQU'
RAW_SID = '1pnDkBjLjfXgNE-Qv7rU7risEfcM3y4f4nd-OTN9XEu0'
RAW_INDEX = {'ECHEMI', 'SCI99', '100PPI'}
CREDS = r'C:\Users\DELL\.openclaw\workspace\secrets\service_account.json'
CHUNK = 30
COL = 'AZ'          # widths are 9..17, a fixed end column avoids a row_count probe
SCAN_ROWS = 16      # newest-first, so the latest date sits near the top
EPOCH = datetime(1899, 12, 30)
FMTS = ('%m/%d/%Y', '%Y-%m-%d', '%Y/%m/%d')

OLD_SHEETS = [
    '汇率',
    '赖氨酸70_河北_sci99', '赖氨酸70_山东_sci99',
    '赖氨酸98_河北_sci99', '赖氨酸98_山东_sci99',
    '苏氨酸_河北_sci99', '苏氨酸_山东_sci99',
    '缬氨酸_sci99_search', '色氨酸_sci99',
    '精氨酸', '异亮氨酸',
    '氯化胆碱_echemi', '磷酸氢钙_sci99', '磷酸一二钙_pdf_sci99',
    '磷酸二氢钙_云南_sci99_search', '磷酸二氢钙_西南_sci99',
    '蛋氨酸_山东_sci99', '蛋氨酸_河南_sci99',
    '维生素A_sci99', '维生素B1_sci99', '维生素B2_sci99',
    '维生素C_sci99', '维生素D3_sci99', '维生素E_sci99',
    '玉米蛋白粉_sci99', 'DDGS_sci', '鱼粉_sci99',
    '乳清粉_sci99', '肌醇_国产_100ppi', '发酵豆粕_mysteel',
    '棕榈油_天津24_sci99', '棕榈油_张家港52_sci99', '棕榈油_张家港24_sci99',
]

_client = None


def client():
    global _client
    if _client is None:
        creds = Credentials.from_service_account_file(
            CREDS, scopes=['https://www.googleapis.com/auth/spreadsheets'])
        _client = gspread.authorize(creds)
    return _client


def with_retry(fn, tries=3, wait=60):
    """Retry on Google 429 quota (read requests per minute)."""
    for i in range(tries):
        try:
            return fn()
        except gspread.exceptions.APIError as e:
            if '429' in str(e) and i < tries - 1:
                print(f'  429 quota — wait {wait}s then retry ({i + 1}/{tries - 1})',
                      flush=True)
                time.sleep(wait)
            else:
                raise


def as_date(v):
    """Cell value -> datetime, or None. Raw tabs store serials, old tabs text."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        if 30000 <= v <= 60000:
            return EPOCH + timedelta(days=int(v))
        return None
    s = str(v).strip()
    for f in FMTS:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            pass
    return None


def header_of(rows):
    for i, r in enumerate(rows[:8]):
        if any(str(c).strip() == '日期' for c in r):
            return i
    return 0


def fetch(sh, titles, render='UNFORMATTED_VALUE'):
    """{title: rows} for every title that exists, plus the missing titles."""
    ws = {w.title: w for w in with_retry(sh.worksheets)}
    order, ranges, missing = [], [], []
    for t in titles:
        if t in ws:
            order.append(t)
            ranges.append(f"'{t}'!A1:{COL}{ws[t].row_count}")
        else:
            missing.append(t)
    grid = {}
    for i in range(0, len(ranges), CHUNK):
        res = with_retry(lambda rs=ranges[i:i + CHUNK]:
                         sh.values_batch_get(rs, params={'valueRenderOption': render}))
        for t, v in zip(order[i:i + CHUNK], res['valueRanges']):
            grid[t] = v.get('values', [])
        time.sleep(0.3)
    return grid, missing


def status_of(rows):
    """(latest date, data rows, date columns) from a tab's first SCAN_ROWS rows.

    Only columns whose header says 日期 count as dates - price columns can hold
    serial-sized numbers (肌醇 47993) that would otherwise read as 2031.
    """
    header = header_of(rows)
    hdr = rows[header] if header < len(rows) else []
    date_cols = [ci for ci, v in enumerate(hdr) if '日期' in str(v)] or [0]
    body = rows[header + 1:header + 1 + SCAN_ROWS]
    latest = None
    for r in body:
        for ci in date_cols:
            d = as_date(r[ci]) if ci < len(r) else None
            if d is not None and (latest is None or d > latest):
                latest = d
    c0 = date_cols[0]
    data = [r for r in rows[header + 1:]
            if c0 < len(r) and as_date(r[c0]) is not None]
    return latest, len(data), date_cols


def collect_sheet(sh, titles=None, extra_src=False):
    """[{name, status, latest, rows, date_cols, src}] for one spreadsheet.

    status: ok | nodate | missing
    """
    if titles is None:
        titles = [w.title for w in with_retry(sh.worksheets)
                  if w.title not in RAW_INDEX]
    grid, missing = fetch(sh, titles)
    out = []
    for t in titles:
        rec = {'name': t, 'status': 'ok', 'latest': None, 'rows': 0,
               'date_cols': 0, 'src': None}
        if t in missing:
            rec['status'] = 'missing'
            out.append(rec)
            continue
        rows = grid.get(t) or []
        latest, n, cols = status_of(rows)
        rec['rows'], rec['date_cols'] = n, len(cols)
        rec['latest'] = latest
        if latest is None:
            rec['status'] = 'nodate'
            rec['rows'] = len(rows)
        if extra_src:
            s = rows[0][0] if rows and rows[0] else ''
            rec['src'] = isinstance(s, str) and 'http' in s
        out.append(rec)
    return out


def collect_all():
    """{old: [...], raw: [...], ts: datetime} - one batched pass over both sheets."""
    sh_old = with_retry(lambda: client().open_by_key(OLD_SID))
    sh_raw = with_retry(lambda: client().open_by_key(RAW_SID))
    return {
        'old': collect_sheet(sh_old, OLD_SHEETS, extra_src=False),
        'raw': collect_sheet(sh_raw, None, extra_src=True),
        'ts': datetime.now(),
    }


def summary(tabs):
    ok = sum(1 for t in tabs if t['status'] == 'ok')
    latest = max((t['latest'] for t in tabs if t['latest']), default=None)
    return {'total': len(tabs), 'ok': ok, 'latest': latest}


def _fmt(d):
    return f'{d.month}/{d.day}/{d.year}' if d else '-'


def _report(label, tabs, extra_src=False):
    for t in tabs:
        if t['status'] == 'missing':
            print(f"{t['name']}: MISSING")
        elif t['status'] == 'nodate':
            print(f"{t['name']}: NO DATES rows={t['rows']}")
        else:
            line = (f"{t['name']}: latest={_fmt(t['latest'])} "
                    f"rows={t['rows']} date_cols={t['date_cols']}")
            if extra_src:
                line += ' src=' + ('ok' if t['src'] else 'NONE')
            print(line)
    s = summary(tabs)
    print(f"{label}: {s['ok']}/{s['total']} tabs with dates\n")


def main():
    print('=== OLD (33 tabs) ===')
    data = collect_all()
    _report('OLD (33 tabs)', data['old'])
    print('=== RAW (50 data tabs) ===')
    _report('RAW (50 data tabs)', data['raw'], extra_src=True)

    # Format samples: top 3 rows of a few representative tabs (formulas shown)
    print('=== FORMAT SAMPLES (header+2 rows, cols 0-11) ===')
    for label, sid, tabs in (('old', OLD_SID, ['维生素B1_sci99', '赖氨酸70_河北_sci99']),
                             ('raw', RAW_SID, ['维生素E_sci99', '玉米淀粉_100ppi', '三甲胺_cnbg'])):
        sh = with_retry(lambda s=sid: client().open_by_key(s))
        grid, _ = fetch(sh, tabs, render='FORMULA')
        for t in tabs:
            rows = grid.get(t)
            if rows is None:
                print(f'--- [{label}] {t}: MISSING')
                continue
            print(f'--- [{label}] {t}')
            h = header_of(rows)
            body = [r for r in rows[h:] if r and any(str(c).strip() for c in r)]
            for r in body[:3]:
                print(' ', r[0:12])
    print('DONE verify')


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                                  line_buffering=True)
    main()
