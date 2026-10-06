# -*- coding: utf-8 -*-
"""Update the 2 vip.sci99.com PDF tabs (磷酸一铵/磷酸二铵) of the 原料 sheet.

Weekly report '磷矿石及磷酸氢钙市场周报' carries both averages in its PDF:
    磷酸一铵 ... 55%粉全国市场均价<N>元/吨
    磷酸二铵 ... 64%市场均价<N>元/吨
One row per report period end, so reports newer than the tab are applied in
order (the tabs were last written on 9/10 and can be several weeks behind).

Pure requests + pymupdf, no browser. The FX block K..Q and 涨跌/比例 are
filled by raw_lib.stamp from the column templates, so only the date, key
columns and the average have to be produced here.

Quota: one values_batch_get + one values_batch_update.
"""
import io
import json
import os
import re
import sys
import time
from datetime import datetime

if __name__ == '__main__' and __package__ is None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

import newsheet_lib as NS
import raw_lib as RL

HERE = os.path.dirname(os.path.abspath(__file__))
COOKIES = os.path.join(HERE, 'sci99_cookies.json')
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'}
TARGET = '磷矿石及磷酸氢钙市场周报'
# verified against the 20260925-0930 report (3883.33 / 4912.50)
PRICE_RE = {
    '磷酸一铵_pdf_sci99': re.compile(r'磷酸一铵.{0,200}?55%粉全国市场均价([\d.]+)元/吨'),
    '磷酸二铵_pdf_sci99': re.compile(r'磷酸二铵.{0,150}?64%市场均价([\d.]+)元/吨'),
}
MAX_REPORTS = 6


def session():
    s = requests.Session()
    for c in json.load(open(COOKIES, encoding='utf-8')):
        s.cookies.set(c['name'], c['value'], domain=c.get('domain', '.sci99.com'))
    return s


def period_end(title):
    m = re.search(r'[（(](\d{8})-(\d{4})[）)]', title or '')
    if not m:
        return None
    start = datetime.strptime(m.group(1), '%Y%m%d')
    end = datetime(start.year, int(m.group(2)[:2]), int(m.group(2)[2:]))
    if end < start:
        try:
            end = end.replace(year=end.year + 1)
        except ValueError:
            pass
    return end


def list_reports(s, floor=None, max_pages=30):
    """[(period_end, title, infoKey)] for TARGET, newest first.

    The listing is 100 reports/page and reaches back roughly 6 days per 1000
    items, so it has to be walked until a report at or before `floor` shows
    up (otherwise only the newest week is found and earlier ones are skipped)."""
    out = []
    seen = set()
    for pi in range(1, max_pages + 1):
        r = None
        try:
            r = s.post('https://vip.sci99.com/api/v2/open/report/getReport',
                       json={'columnId': '', 'sort': 'desc', 'pageSize': 100, 'pageIndex': pi,
                             'classIds': '', 'hyProductId': ''},
                       headers={**UA, 'Referer': 'https://vip.sci99.com/pages/report-list.html',
                                'Content-Type': 'application/json'}, timeout=30)
            items = r.json()['data']['Items']
        except Exception as e:
            code = getattr(r, 'status_code', '?') if r is not None else 'no-response'
            print(f'  getReport failed (status={code}, {e})')
            break
        if not items:
            break
        covered = False
        for it in items:
            title = it.get('searchstr', '')
            if not title.startswith(TARGET):
                continue
            pe = period_end(title)
            if not pe or (pe, title) in seen:
                continue
            seen.add((pe, title))
            out.append((pe, title, it.get('infoKey')))
            if floor is not None and pe <= floor:
                covered = True
        if covered:
            break
    out.sort(key=lambda x: x[0], reverse=True)
    print(f'  scanned {pi} page(s), {len(out)} target report(s)')
    return out[:MAX_REPORTS]


def fetch_text(s, infokey):
    det = s.get('https://vip.sci99.com/api/v1/reportinfo/newsdetail/',
                params={'newskey': infokey, 'system': 6},
                headers={**UA, 'Referer': 'https://vip.sci99.com/pages/shownews.html'}, timeout=30)
    fp = det.json()['data'].get('FilePath')
    if not fp:
        print(f'  no FilePath for {infokey}')
        return ''
    pdf = s.get(fp, headers={**UA, 'Referer': 'https://vip.sci99.com/'}, timeout=90)
    if pdf.status_code != 200 or len(pdf.content) < 10000:
        print(f'  PDF download failed status={pdf.status_code} bytes={len(pdf.content)}')
        return ''
    tmp = os.path.join(os.environ.get('TEMP', '.'), 'raw_sci99_pdf_latest.pdf')
    open(tmp, 'wb').write(pdf.content)
    import pymupdf
    doc = pymupdf.open(tmp)
    text = ''.join(pg.get_text() for pg in doc)
    doc.close()
    return re.sub(r'\s+', '', text)


def key_of(rows, meta):
    old = RL.data_rows(rows, meta)
    if not old:
        return None
    k = old[0]
    rem = k[10] if len(k) > 10 else ''
    return {
        'name': k[1], 'spec': k[2], 'market': k[3], 'dtype': k[4],
        'width': meta['width'],
        'remark': rem if isinstance(rem, str) else '',
        'price_col': meta['price_col'],
    }


def to_fresh(end, price, k):
    row = [''] * k['width']
    row[0] = f'{end.month}/{end.day}/{end.year}'
    row[1], row[2], row[3], row[4] = k['name'], k['spec'], k['market'], k['dtype']
    row[k['price_col']] = price
    if k['width'] > 10:
        row[10] = k['remark']
    return row


def main():
    sh = RL.open_sh()
    titles = [t for t in RL.all_titles(sh) if t in PRICE_RE]
    if not titles:
        print('no pdf tabs found')
        print('DONE raw_sci99_pdf')
        return
    titles.sort()
    grid = RL.read_grid(sh, titles)
    metas, keys, latest = {}, {}, {}
    for t in titles:
        m = RL.analyze(grid[t])
        if m is None:
            print(f'  WARN {t}: no header')
            continue
        k = key_of(grid[t], m)
        if k is None:
            print(f'  WARN {t}: no data rows')
            continue
        metas[t], keys[t] = m, k
        ends = []
        for r in RL.data_rows(grid[t], m):
            d = NS.date_text(r[0])
            if d:
                try:
                    ends.append(datetime.strptime(d, '%m/%d/%Y'))
                except ValueError:
                    pass
        latest[t] = max(ends) if ends else datetime(1900, 1, 1)
        print(f'  {t}: latest {latest[t].month}/{latest[t].day}/{latest[t].year} '
              f'rows {len(RL.data_rows(grid[t], m))}')

    s = session()
    floor = min(latest.values()) if latest else None
    reports = list_reports(s, floor=floor)
    if not reports:
        print('  no target reports in listing')
        print('DONE raw_sci99_pdf')
        return
    need = [r for r in reports if any(r[0] > latest[t] for t in titles if t in keys)]
    print(f'  reports: {len(reports)}, needed (> sheet latest): {len(need)}')
    for pe, title, _ in sorted(need):
        print(f'    {pe.month}/{pe.day}/{pe.year} {title}')

    fresh = {t: [] for t in titles}
    for pe, title, infokey in sorted(need, key=lambda x: x[0]):
        text = fetch_text(s, infokey)
        if not text:
            continue
        found = 0
        for t, rx in PRICE_RE.items():
            if t not in keys or pe <= latest[t]:
                continue
            m = rx.search(text)
            if not m:
                print(f'    {t}: price not in {title}')
                continue
            price = float(m.group(1))
            if price == int(price):
                price = int(price)
            fresh[t].append(to_fresh(pe, price, keys[t]))
            found += 1
            print(f'    {t}: {price} @ {pe.month}/{pe.day}/{pe.year}')
        if not found:
            print(f'    nothing extracted from {title}')
        time.sleep(1)

    blocks, first_row, old_end = {}, {}, {}
    for t in titles:
        if t not in keys:
            continue
        built, meta, err = RL.build(grid[t], fresh[t], metas[t])
        if err:
            print(f'  FAIL {t}: {err}')
            continue
        old_n = len(RL.data_rows(grid[t], metas[t]))
        new_n = len(built)
        if new_n != old_n or fresh[t]:
            blocks[t] = built
            first_row[t] = metas[t]['first']
            old_end[t] = metas[t]['first'] + old_n - 1
            print(f'  {t}: +{len(fresh[t])} fetched, rows {old_n} -> {new_n}')
    if not blocks:
        print('nothing new')
        print('DONE raw_sci99_pdf')
        return
    if '--dry' in sys.argv:
        print(f'[dry] would write {sorted(blocks)}')
        print('DONE raw_sci99_pdf')
        return
    n = RL.write_all(sh, blocks, first_row, old_end=old_end)
    print(f'wrote {n} tabs in 1 call')
    print('DONE raw_sci99_pdf')


if __name__ == '__main__':
    main()
