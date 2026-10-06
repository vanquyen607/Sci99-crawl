# -*- coding: utf-8 -*-
"""Update the chinabgao tab (三甲胺_cnbg) of the 原料 sheet.

Source is the index page listed in A1 (https://www.chinabgao.com/jiage/sanjiaan/):
its single table holds the latest day's quotes
    交货地 | 价格 | 产品名称 | 备注 | 产地/品牌 | 时间
The tab's market is 山东, so the row whose 产地/品牌 matches is taken; when the
source lists several of them the one closest to the sheet's latest price wins
(the 9/11 row was recorded at 6650 while the page's 山东 quote read 6500).
A row is added only when its date is newer than the tab's latest date, or when
it revises that same date's price.

Quota: one values_batch_get + one values_batch_update.
"""
import io
import html
import os
import re
import sys
from datetime import datetime

if __name__ == '__main__' and __package__ is None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

import newsheet_lib as NS
import raw_lib as RL

TAB = '三甲胺_cnbg'
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'}


def clean(s):
    s = re.sub(r'<[^>]+>', '', s)
    return html.unescape(s).replace('\xa0', ' ').strip()


def parse_table(page):
    m = re.search(r'<table[^>]*>(.*?)</table>', page, re.S)
    if not m:
        return []
    trs = re.findall(r'<tr[^>]*>(.*?)</tr>', m.group(1), re.S)
    rows = []
    for tr in trs:
        cells = [clean(c) for c in re.findall(r'<(?:td|th)[^>]*>(.*?)</(?:td|th)>', tr, re.S)]
        if cells:
            rows.append(cells)
    if not rows:
        return []
    head = rows[0]
    if '价格' not in head or '时间' not in head:
        return []
    out = []
    for r in rows[1:]:
        if len(r) != len(head):
            continue
        out.append(dict(zip(head, r)))
    return out


def price_of(text):
    m = re.match(r'([\d,]+(?:\.\d+)?)', str(text or '').strip())
    if not m:
        return None
    return float(m.group(1).replace(',', ''))


def key_of(rows, meta):
    old = RL.data_rows(rows, meta)
    if not old:
        return None
    k = old[0]
    return {'name': k[1], 'spec': k[2], 'market': k[3], 'dtype': k[4],
            'width': meta['width'], 'price_col': meta['price_col']}


def main():
    sh = RL.open_sh()
    grid = RL.read_grid(sh, [TAB])
    rows = grid.get(TAB)
    if not rows:
        print('no data')
        print('DONE raw_cnbg')
        return
    meta = RL.analyze(rows)
    if meta is None:
        print('no header row')
        print('DONE raw_cnbg')
        return
    k = key_of(rows, meta)
    if k is None:
        print('no data rows')
        print('DONE raw_cnbg')
        return

    latest = None
    latest_price = None
    for r in RL.data_rows(rows, meta):
        d = NS.date_text(r[0])
        if not d:
            continue
        try:
            dt = datetime.strptime(d, '%m/%d/%Y').date()
        except ValueError:
            continue
        if latest is None or dt > latest:
            latest = dt
            latest_price = RL._plain(r[meta['price_col']])
    url = str(rows[0][0] or '').strip()
    print(f'  {TAB}: latest {latest} price {latest_price}, rows {len(RL.data_rows(rows, meta))}')
    print(f'  url {url}')

    r = requests.get(url, headers=UA, timeout=30)
    r.encoding = r.apparent_encoding or 'utf-8'
    quotes = parse_table(r.text)
    if not quotes:
        print('  no table on index page')
        print('DONE raw_cnbg')
        return
    cands = []
    for q in quotes:
        p = price_of(q.get('价格'))
        if p is None:
            continue
        cands.append((q, p))
    print(f'  {len(cands)} quote(s): ' + '; '.join(
        f"{q.get('产地/品牌')} {q.get('备注')} {p:g} @ {q.get('时间')}" for q, p in cands))
    brand = [c for c in cands if c[0].get('产地/品牌', '').strip() == k['market']]
    if not brand:
        print(f"  WARN no {k['market']} row, falling back to all quotes")
        brand = cands
    q, price = min(brand, key=lambda c: abs(c[1] - (latest_price or 0)))
    try:
        d = datetime.strptime(q.get('时间', ''), '%Y-%m-%d').date()
    except ValueError:
        print('  bad time cell', repr(q.get('时间')))
        print('DONE raw_cnbg')
        return
    print(f"  picked {q.get('交货地')} {q.get('产地/品牌')} {q.get('备注')} {price:g} @ {d}")

    if latest and d < latest:
        print('  SKIP: source date older than sheet latest')
        print('DONE raw_cnbg')
        return
    if d == latest and latest_price is not None and price == latest_price:
        print('  SKIP: newest quote already in the sheet')
        print('DONE raw_cnbg')
        return

    fresh = [''] * k['width']
    fresh[0] = f'{d.month}/{d.day}/{d.year}'
    fresh[1], fresh[2], fresh[3], fresh[4] = k['name'], k['spec'], k['market'], k['dtype']
    fresh[meta['price_col']] = price
    fresh[8] = q.get('备注') or q.get('产地/品牌') or ''

    built, meta2, err = RL.build(rows, [fresh], meta)
    if err:
        print(f'  FAIL: {err}')
        print('DONE raw_cnbg')
        return
    old_n = len(RL.data_rows(rows, meta))
    print(f'  rows {old_n} -> {len(built)}')
    if '--dry' in sys.argv:
        print('[dry] would write 1 tab')
        print('DONE raw_cnbg')
        return
    RL.write_all(sh, {TAB: built}, {TAB: meta['first']},
                 old_end={TAB: meta['first'] + old_n - 1})
    print('wrote 1 tab in 1 call')
    print('DONE raw_cnbg')


if __name__ == '__main__':
    main()
