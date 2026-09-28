# -*- coding: utf-8 -*-
"""Weekly: fetch latest 磷矿石及磷酸氢钙市场周报 PDF and append 磷酸一二钙 row.
Pure requests (vip.sci99.com APIs) + pymupdf — no browser.
Non-core step: SKIP (exit 0) when no new report.
"""
import sys, io, os, re, json, html, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
from datetime import datetime
import requests
import gspread
from google.oauth2.service_account import Credentials
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
COOKIES = os.path.join(HERE, 'sci99_cookies.json')
CREDS = r'C:\Users\DELL\.openclaw\workspace\secrets\service_account.json'
SID = '1kuN8rT9shOellupamis9iyb6CpZFaWpao4VLdzZnQQU'
SHEET = '磷酸一二钙_pdf_sci99'
TARGET = '磷矿石及磷酸氢钙市场周报'
NOTE = '磷矿石及磷酸氢钙市场周报'
HEADER = 2  # data starts row 3

import newsheet_lib

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'}


def parse_date(s):
    s = str(s or '').strip()
    for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%Y/%m/%d'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def mdY(d):
    return f'{d.month}/{d.day}/{d.year}'


def session():
    s = requests.Session()
    for c in json.load(open(COOKIES, encoding='utf-8')):
        s.cookies.set(c['name'], c['value'], domain=c.get('domain', '.sci99.com'))
    return s


def fmt_pct(cur, prev):
    if not prev:
        return '0,00%'
    p = (cur - prev) / prev * 100
    a = f'{abs(p):.2f}'.replace('.', ',')
    return f'-{a}%' if p < 0 else f'{a}%'


def main():
    s = session()

    # 1) newest target report via getReport API
    found = None
    for pi in range(1, 4):
        r = None
        for attempt in range(2):
            try:
                r = s.post('https://vip.sci99.com/api/v2/open/report/getReport',
                           json={'columnId': '', 'sort': 'desc', 'pageSize': 100, 'pageIndex': pi,
                                 'classIds': '', 'hyProductId': ''},
                           headers={**UA, 'Referer': 'https://vip.sci99.com/pages/report-list.html',
                                    'Content-Type': 'application/json'}, timeout=30)
                items = r.json()['data']['Items']
                break
            except Exception as e:
                code = getattr(r, 'status_code', '?') if r is not None else 'no-response'
                print(f'getReport not JSON (status={code}, {e})' + (' — retry in 20s' if attempt == 0 else ' — SKIP'))
                if attempt == 0:
                    time.sleep(20)
                else:
                    return 0
        if not items:
            break
        for it in items:
            if it.get('searchstr', '').startswith(TARGET):
                found = it
                break
        if found:
            break
    if not found:
        print('SKIP: no target report found in getReport listing')
        return 0

    title = found['searchstr']
    print('latest report:', title, 'pubdate', found.get('pubdate'), 'infoKey', found.get('infoKey'))
    m = re.search(r'（(\d{8})-(\d{4})）', title)
    if not m:
        print('SKIP: cannot parse report period from title')
        return 0
    start_dt = datetime.strptime(m.group(1), '%Y%m%d')
    data_end = datetime(start_dt.year, int(m.group(2)[:2]), int(m.group(2)[2:]))
    if data_end < start_dt:
        try:
            data_end = data_end.replace(year=data_end.year + 1)
        except ValueError:
            pass

    # 2) compare with sheet
    creds = Credentials.from_service_account_file(CREDS, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    sh = gspread.authorize(creds).open_by_key(SID)
    ws = sh.worksheet(SHEET)
    vals = ws.get_all_values()
    data_rows = []
    for r in vals[HEADER:]:
        d = parse_date(r[0] if r else '')
        if d:
            data_rows.append((d, list(r) + [''] * 17))
    latest = max((d for d, _ in data_rows), default=None)
    print('sheet latest:', mdY(latest) if latest else None, 'data rows', len(data_rows))
    if latest and data_end <= latest:
        print('SKIP: report period end', mdY(data_end), '<= sheet latest — nothing new')
        return 0

    # 3) detail → PDF
    det = s.get('https://vip.sci99.com/api/v1/reportinfo/newsdetail/',
                params={'newskey': found['infoKey'], 'system': 6},
                headers={**UA, 'Referer': 'https://vip.sci99.com/pages/shownews.html'}, timeout=30)
    fp = det.json()['data'].get('FilePath')
    if not fp:
        print('SKIP: no FilePath (PDF) in newsdetail')
        return 0
    pdf = s.get(fp, headers={**UA, 'Referer': 'https://vip.sci99.com/'}, timeout=90)
    if pdf.status_code != 200 or len(pdf.content) < 10000:
        print(f'SKIP: PDF download failed status={pdf.status_code} bytes={len(pdf.content)}')
        return 0
    tmp = os.path.join(os.environ.get('TEMP', '.'), 'mdcph_weekly_latest.pdf')
    open(tmp, 'wb').write(pdf.content)
    print('pdf saved', tmp, len(pdf.content), 'bytes')

    # 4) extract 磷酸一二钙 price range
    import pymupdf
    doc = pymupdf.open(tmp)
    text = ''.join(pg.get_text() for pg in doc)
    doc.close()
    flat = re.sub(r'\s+', '', text)
    m2 = re.search(r'磷酸一二钙[:：].{0,200}?参考(\d{4,5})-(\d{4,5})元/吨', flat)
    if not m2:
        # fallback: any 一二钙 ... range
        m2 = re.search(r'磷酸一二钙.{0,120}?(\d{4,5})-(\d{4,5})元/吨', flat)
    if not m2:
        print('SKIP: 磷酸一二钙 price not found in PDF')
        return 0
    pmin, pmax = int(m2.group(1)), int(m2.group(2))
    pavg = round((pmin + pmax) / 2)
    print('extracted:', pmin, '-', pmax, 'avg', pavg)

    # 5) FX for report end date from 汇率 sheet
    fx_ws = sh.worksheet('汇率')
    fx_vals = fx_ws.get_all_values()
    fx = None
    for r in fx_vals[1:]:
        d = parse_date(r[0] if r else '')
        if d and d.date() == data_end.date() and len(r) > 1:
            fx = str(r[1]).replace(',', '.').strip()
            break
    if fx is None:
        # fall back to latest available rate
        for r in fx_vals[1:]:
            d = parse_date(r[0] if r else '')
            if d and len(r) > 1:
                fx = str(r[1]).replace(',', '.').strip()
                print('WARN: no FX for', mdY(data_end), '— using latest', fx, 'from', mdY(d))
                break
    if fx is None:
        print('SKIP: no FX available from 汇率 sheet')
        return 0
    print('fx:', fx)

    # 6) build row
    prev_avg = None
    for d, row in sorted(data_rows, key=lambda x: x[0]):
        if d < data_end:
            try:
                prev_avg = float(str(row[7]).replace(',', ''))
            except Exception:
                prev_avg = None
            break
    try:
        f = float(fx)
        zdmj = round(pavg / f, 2)
        tsh = round(zdmj * 0.87, 2)
        cif = round(tsh + 10 + 30, 2)
    except Exception:
        zdmj = tsh = cif = ''

    new_row = [mdY(data_end), '磷酸一二钙', '饲料级21%粉', '云南', '市场价',
               str(pmin), str(pmax), str(pavg),
               '', '',   # chg/pct: write_tab regenerates as formulas
               fx, str(zdmj), str(tsh), '10', '30', str(cif), NOTE]
    print('ADD', new_row)

    # existing rows read with formulas preserved (date serials -> text)
    grid = newsheet_lib.read_formula_rows(ws, HEADER + 1, 17)
    out = [new_row] + [row[:17] for row in grid]
    newsheet_lib.write_tab(ws, out, HEADER + 1, 17)
    print('update n', len(out))

    vals2 = ws.get_all_values()
    print('top after:', vals2[2][:11])
    print('DONE')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f'SKIP: exception {e}')
        sys.exit(0)
