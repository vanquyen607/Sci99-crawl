# -*- coding: utf-8 -*-
"""Update the two chinabgao tabs of the 原料 sheet (one tab per product series).

Source: the index page stored in A1 (https://www.chinabgao.com/jiage/sanjiaan/)
lists only today's 3 quotes, while its newest daily article can list up to 10
(brands included). The article linked from the index is therefore the primary
source; the index table itself is the fallback when no article can be read.

Series matched by brand + spec, never substituted by another quote:
    三甲胺_鲁西化工_cnbg <- 产地/品牌 contains 鲁西化工 (else 鲁西 with spec 99.9)
    三甲胺_国产_cnbg     <- 产地/品牌 == 国产 and 备注 contains 99.99
A series with no matching quote that day is skipped (SKIP in the log), so the
tab keeps its own price line instead of inheriting a stranger's.

A row is written only when its date is newer than the tab's latest date, or
when it revises that same date's price.

Quota: one values_batch_get + one values_batch_update (+2 HTTP GETs).
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

DEFAULT_URL = 'https://www.chinabgao.com/jiage/sanjiaan/'
PRODUCT = '三甲胺'
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'}
ARTICLE_RE = re.compile(r'<a[^>]+href="([^"]*?/jiage/\d+\.html)"[^>]*>(.*?)</a>', re.S)
DATE_RE = re.compile(r'(\d{4})年(\d{1,2})月(\d{1,2})日')


def score_luxi(q):
    """鲁西化工 series: the brand itself, else the plain 鲁西 99.9 row."""
    brand = (q.get('产地/品牌') or '').strip()
    note = (q.get('备注') or '')
    if '30%' in note:
        return 0
    if '鲁西化工' in brand:
        return 3
    if brand == '鲁西' and '99.9' in note:
        return 2
    return 0


def score_local(q):
    """国产 series: only the 99.99%优等品 row (the 30% water solution never)."""
    brand = (q.get('产地/品牌') or '').strip()
    note = (q.get('备注') or '')
    if brand == '国产' and '99.99' in note:
        return 3
    return 0


SERIES = (
    {'tab': '三甲胺_鲁西化工_cnbg', 'label': '鲁西化工', 'score': score_luxi},
    {'tab': '三甲胺_国产_cnbg', 'label': '国产99.99%', 'score': score_local},
)


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


def spec_of(note):
    """'优等品；含量99.99%' -> '99.99%', '99.9' -> '99.9', '纯品' -> '纯品'."""
    n = str(note or '').strip()
    m = re.search(r'\d+(?:\.\d+)?\s*%', n)
    if m:
        return m.group(0).replace(' ', '')
    m = re.search(r'\d+\.\d+', n)
    if m:
        return m.group(0)
    return n[:24]


def get(url, referer=None):
    headers = dict(UA)
    if referer:
        headers['Referer'] = referer
    r = requests.get(url, headers=headers, timeout=30)
    r.encoding = r.apparent_encoding or 'utf-8'
    return r


def newest_article(index_page):
    """(date, url) of the newest dated article link, or None."""
    best = None
    for m in ARTICLE_RE.finditer(index_page):
        href, txt = m.group(1), clean(m.group(2))
        dm = DATE_RE.search(txt)
        if not dm:
            continue
        try:
            d = datetime(int(dm.group(1)), int(dm.group(2)), int(dm.group(3))).date()
        except ValueError:
            continue
        if best is None or d > best[0]:
            url = href if href.startswith('http') else 'https://www.chinabgao.com' + href
            best = (d, url, txt)
    return best


def fetch_quotes(index_url):
    """(quotes, note) - quotes from the newest article, else from the index."""
    r = get(index_url)
    if r.status_code != 200:
        print(f'  index HTTP {r.status_code}')
        return [], 'index HTTP %s' % r.status_code
    art = newest_article(r.text)
    if art:
        for attempt in range(2):
            try:
                a = get(art[1], referer=index_url)
            except requests.RequestException as e:
                print(f'  article GET error {e}')
                break
            if a.status_code == 200:
                rows = parse_table(a.text)
                if rows:
                    print(f'  source: article {art[0]} {art[1]} ({len(rows)} quotes)')
                    return rows, f'article {art[0]}'
                print(f'  article {art[1]} has no quote table')
                break
            print(f'  article HTTP {a.status_code} (attempt {attempt + 1})')
        print('  fallback: index table')
    else:
        print('  no dated article link on index')
    rows = parse_table(r.text)
    print(f'  source: index table ({len(rows)} quotes)')
    return rows, 'index'


def pick(quotes, score, latest_price):
    """(quote, price) of the best-scoring row, or None; ties go to the price
    closest to the sheet's latest."""
    cands = []
    for q in quotes:
        p = price_of(q.get('价格'))
        s = score(q)
        if p is None or s <= 0:
            continue
        cands.append((q, p, s))
    if not cands:
        return None
    top = [c for c in cands if c[2] == max(x[2] for x in cands)]
    if len(top) == 1:
        return top[0][0], top[0][1]
    q, p, _ = min(top, key=lambda c: abs(c[1] - (latest_price or 0)))
    return q, p


def col_of(meta, name, default=-1):
    for i, h in enumerate(meta['header']):
        if name in str(h):
            return i
    return default


def latest_of(rows, meta):
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
    return latest, latest_price


def main():
    sh = RL.open_sh()
    tabs = [s['tab'] for s in SERIES]
    grid = RL.read_grid(sh, tabs)
    metas, latests = {}, {}
    for s in SERIES:
        rows = grid.get(s['tab'])
        if not rows:
            print(f"  {s['tab']}: no data")
            continue
        meta = RL.analyze(rows)
        if meta is None:
            print(f"  {s['tab']}: no header row")
            continue
        metas[s['tab']] = meta
        latests[s['tab']] = latest_of(rows, meta)
        lp, price = latests[s['tab']]
        print(f"  {s['tab']}: latest {lp} price {price}, "
              f"rows {len(RL.data_rows(rows, meta))}")
    if not metas:
        print('DONE raw_cnbg')
        return

    index_url = str((grid.get(SERIES[0]['tab']) or [['']])[0][0] or '').strip() or DEFAULT_URL
    print(f'  url {index_url}')
    quotes, src = fetch_quotes(index_url)
    if not quotes:
        print('  no quotes on source')
        print('DONE raw_cnbg')
        return
    for q in quotes:
        print(f"    {q.get('产地/品牌')} | {q.get('备注')} | "
              f"{q.get('价格')} | {q.get('交货地')} | {q.get('时间')}")

    built, first, old_end = {}, {}, {}
    for s in SERIES:
        tab = s['tab']
        if tab not in metas:
            continue
        meta = metas[tab]
        latest, latest_price = latests[tab]
        picked = pick(quotes, s['score'], latest_price)
        if picked is None:
            print(f"  {tab}: SKIP no {s['label']} quote in {src}")
            continue
        q, price = picked
        note = (q.get('备注') or '').strip()
        loc = (q.get('交货地') or '').strip()
        try:
            d = datetime.strptime(q.get('时间', ''), '%Y-%m-%d').date()
        except ValueError:
            print(f'  {tab}: bad time cell {q.get("时间")!r} - SKIP')
            continue
        print(f"  {tab}: picked {loc} {q.get('产地/品牌')} {note} {price:g} @ {d}")
        if latest and d < latest:
            print(f'  {tab}: SKIP source date older than sheet latest {latest}')
            continue
        if d == latest and latest_price is not None and price == latest_price:
            print(f'  {tab}: SKIP newest quote already in the sheet')
            continue

        width = meta['width']
        fresh = [''] * width
        fresh[0] = f'{d.month}/{d.day}/{d.year}'
        c_name = col_of(meta, '产品名称', 1)
        c_spec = col_of(meta, '规格型号', 2)
        c_market = col_of(meta, '市场', 3)
        c_type = col_of(meta, '数据类型', 4)
        c_note = col_of(meta, '备注', width - 1)
        if c_name >= 0:
            fresh[c_name] = PRODUCT
        if c_spec >= 0:
            fresh[c_spec] = spec_of(note)
        if c_market >= 0:
            fresh[c_market] = (q.get('产地/品牌') or '').strip()
        if c_type >= 0:
            fresh[c_type] = '市场价'
        fresh[meta['price_col']] = price
        if c_note >= 0:
            fresh[c_note] = ' '.join(x for x in (loc, note) if x)

        out, meta2, err = RL.build(grid[tab], [fresh], meta)
        if err:
            print(f'  {tab}: FAIL {err}')
            continue
        old_n = len(RL.data_rows(grid[tab], meta))
        print(f'  {tab}: rows {old_n} -> {len(out)}')
        built[tab] = out
        first[tab] = meta['first']
        old_end[tab] = meta['first'] + old_n - 1

    if not built:
        print('nothing to write')
        print('DONE raw_cnbg')
        return
    if '--dry' in sys.argv:
        print(f'[dry] would write {len(built)} tab(s)')
        print('DONE raw_cnbg')
        return
    RL.write_all(sh, built, first, old_end=old_end)
    print(f'wrote {len(built)} tab(s) in 1 call')
    print('DONE raw_cnbg')


if __name__ == '__main__':
    main()
