# -*- coding: utf-8 -*-
"""Update the 26 *_100ppi tabs of the 原料 spreadsheet from www.100ppi.com.

The site blocks plain requests, so pages are read through headless Chromium.
Tabs are grouped by their A1 source url (甲酸 has 3 tabs on plist-1-1726,
三甲胺 2 on 1285, 富马酸 2 on 3279), so each unique page is fetched once and
sliced per tab by its own series key (商品名称 + 规格 + 品牌/产地, spec compared
by prefix because the sheet keeps a shortened 规格).

One values_batch_get reads all touched tabs and one values_batch_update writes
them back - 2 Sheets API calls for the whole run.
"""
import io
import re
import sys
import time
from datetime import datetime

if __name__ == '__main__' and __package__ is None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))

from playwright.sync_api import sync_playwright

import newsheet_lib as NS
import raw_lib as RL

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
MAX_PAGES = 15
# Some tabs were created under a product name the site no longer uses; the
# spec/market/dtype/price of the series all match the source row below, only
# the recorded name differs (甜菜碱BS-0 -> 甜菜碱BS-12).
NAME_ALIAS = {
    '甜菜碱_100ppi': '甜菜碱BS-12',
}
PAGE_ROWS_JS = '''() => {
    const out = [];
    document.querySelectorAll('table tr').forEach(tr => {
        const cells = [];
        tr.querySelectorAll('th,td').forEach(td => cells.push((td.innerText||'').trim()));
        if (cells.length) out.push(cells);
    });
    return out;
}'''
RE_PRICE = re.compile(r'(-?[\d,]+(?:\.\d+)?)\s*元')   # 元/吨, 元/千克, 元/公斤 ...


def group_by_id(urls):
    """{'1726': ['甲酸_...','甲酸_...'], ...}"""
    out = {}
    for title, url in urls.items():
        m = re.search(r'plist-1-(\d+)-', url)
        if not m:
            print(f'  WARN {title}: not a plist url ({url})')
            continue
        out.setdefault(m.group(1), []).append(title)
    return out


def norm(s):
    return str(s or '').replace('\t', '').strip()


def spec_eq(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return not a and not b
    return a == b or a.startswith(b) or b.startswith(a)


def matches(src, k):
    name = norm(src[0])
    if name != k['name'] and name != k.get('alias'):
        return False
    return spec_eq(src[1], k['spec']) and norm(src[2]) == norm(k['market'])


def trader(src):
    """交易商 column: '山东金生润化工有限公司\\nVIP' -> '山东金生润化工有限公司'"""
    return norm(str(src[6]).split('\n')[0])


def trader_match(src, remark):
    """The tab's 备注 holds the trader the series belongs to, sometimes shortened
    by the sheet ('山东满堂红新'). Match either direction on prefix."""
    a, b = trader(src), norm(remark)
    if not a or not b:
        return False
    return a.startswith(b) or b.startswith(a)


def key_of(rows, meta):
    old = RL.data_rows(rows, meta)
    if not old:
        return None
    k = old[0]
    return {
        'name': k[1], 'spec': k[2], 'market': k[3], 'dtype': k[4],
        'width': meta['width'],
        'remark': (k[10] if len(k) > 10 and isinstance(k[10], str) else '').strip() or '',
    }


def to_fresh(src, k, width):
    m = RE_PRICE.search(str(src[3]))
    if not m:
        return None
    price = float(m.group(1).replace(',', ''))
    if price == int(price):
        price = int(price)
    try:
        d = datetime.strptime(str(src[7]).strip(), '%Y-%m-%d')
    except ValueError:
        return None
    row = [''] * 11
    row[0] = f'{d.month}/{d.day}/{d.year}'
    row[1], row[2], row[3], row[4] = k['name'], k['spec'], k['market'], k['dtype']
    row[7] = price
    if width > 10:
        row[10] = k['remark']
    return row


def fetch_group(page, pid, stop_iso_by_title, titles):
    """All source rows for one plist id, newest page first, until every tab of
    the group is already up to date."""
    raw = []
    empty = 0
    for pn in range(1, MAX_PAGES + 1):
        url = f'https://www.100ppi.com/mprice/plist-1-{pid}-{pn}.html'
        ok = False
        for attempt in range(3):
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=35000)
                ok = True
                break
            except Exception as e:
                print(f'    p{pn} goto err {attempt}: {str(e)[:70]}')
                time.sleep(4)
        if not ok:
            print(f'    p{pn}: give up')
            break
        page.wait_for_timeout(1500)
        data = page.evaluate(PAGE_ROWS_JS)
        rows = [r for r in data if len(r) >= 8 and r[0] != '商品名称']
        if not rows:
            break
        raw.extend(rows)
        page_max = max((str(r[7]) for r in rows if len(r) > 7), default='')
        if all(s and page_max <= s for s in stop_iso_by_title.values()):
            print(f'    p{pn}: page max {page_max} <= sheet max, stop')
            break
        matched = sum(1 for t in titles for r in rows if matches(r, KEYS[t]))
        if matched == 0:
            empty += 1
            if empty >= 2:
                print(f'    p{pn}: no matching series twice, stop')
                break
        else:
            empty = 0
        time.sleep(0.4)
    return raw


KEYS = {}


def main():
    sh = RL.open_sh()
    all_titles = RL.all_titles(sh)
    urls = {}
    res = RL.retry(sh.values_batch_get, [f"'{t}'!A1:A1" for t in all_titles],
                   params={'valueRenderOption': 'FORMULA'})
    for t, v in zip(all_titles, res['valueRanges']):
        vals = v.get('values') or [['']]
        u = vals[0][0] if vals and vals[0] else ''
        if '100ppi.com' in u:
            urls[t] = u
    groups = group_by_id(urls)
    titles = sorted(urls)
    print(f'100ppi: {len(titles)} tabs over {len(groups)} pages ids')

    grid = RL.read_grid(sh, titles)
    metas, stops = {}, {}
    for t in titles:
        m = RL.analyze(grid[t])
        if m is None:
            print(f'  WARN {t}: no header, skipped')
            continue
        k = key_of(grid[t], m)
        if k is None:
            print(f'  WARN {t}: no data rows, skipped')
            continue
        k['alias'] = NAME_ALIAS.get(t)
        KEYS[t] = k
        if t in NAME_ALIAS:
            print(f'  NOTE {t}: source now calls the series {NAME_ALIAS[t]!r} '
                  f'(sheet keeps {k["name"]!r})')
        metas[t] = m
        old = RL.data_rows(grid[t], m)
        stops[t] = max((datetime.strptime(NS.date_text(r[0]), '%m/%d/%Y').strftime('%Y-%m-%d')
                        for r in old if NS.date_text(r[0])), default='')

    cand = {t: [] for t in titles}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(user_agent=UA).new_page()
        for pid, group in sorted(groups.items()):
            group = [t for t in group if t in KEYS]
            if not group:
                continue
            print(f'  id {pid}: {len(group)} tabs')
            raw = fetch_group(page, pid, {t: stops[t] for t in group}, group)
            seen = set()
            for r in raw:
                key = tuple(r)
                if key in seen:
                    continue
                seen.add(key)
                for t in group:
                    if matches(r, KEYS[t]):
                        cand[t].append(r)
            print(f'    rows={len(raw)} -> ' +
                  ', '.join(f'{t}:{len(cand[t])}' for t in group))
        browser.close()

    # Several traders can publish the same name+spec+产地 on one day at
    # different prices; the tab's 备注 names the trader the series belongs to,
    # so keep only its rows when it is still quoting. When that trader has no
    # row on the fetched pages the tab is left untouched rather than being
    # mixed with another trader's quote.
    fresh = {t: [] for t in titles}
    for t in titles:
        rows = cand[t]
        if not rows:
            continue
        keep = [r for r in rows if trader_match(r, KEYS[t]['remark'])]
        if keep:
            dropped = len(rows) - len(keep)
            if dropped:
                print(f'  {t}: kept {len(keep)} rows of trader '
                      f'{KEYS[t]["remark"]!r}, dropped {dropped} from others')
            rows = keep
        elif KEYS[t]['remark']:
            # Never substitute another trader's quote: the series is that
            # trader's price, and a stranger can land 30% away (玉米淀粉
            # 2900 -> 3860 quoted by 山东隆汇). The tab stays where it was
            # until the named trader quotes again.
            print(f'  NOTE {t}: no row from trader {KEYS[t]["remark"]!r} on the '
                  f'fetched pages, skipping instead of mixing another trader')
            continue
        for r in rows:
            row = to_fresh(r, KEYS[t], KEYS[t]['width'])
            if row:
                fresh[t].append(row)

    blocks, first, old_end = {}, {}, {}
    for t in titles:
        if t not in KEYS:
            continue
        rows = grid[t]
        meta = metas[t]
        built, meta2, err = RL.build(rows, fresh[t], meta)
        if err:
            print(f'  FAIL {t}: {err}')
            continue
        old_n = len(RL.data_rows(rows, meta))
        new_n = len(built)
        if fresh[t]:
            print(f'  {t}: +{len(fresh[t])} fetched, rows {old_n} -> {new_n}')
        if new_n != old_n or fresh[t]:
            blocks[t] = built
            first[t] = meta['first']
            old_end[t] = meta['first'] + old_n - 1
    if not blocks:
        print('nothing new')
        print('DONE raw100ppi')
        return
    if '--dry' in sys.argv:
        print(f'[dry] would write {len(blocks)} tabs: '
              + ', '.join(f'{t}:{len(v)}' for t, v in sorted(blocks.items())))
        print('DONE raw100ppi')
        return
    n = RL.write_all(sh, blocks, first, old_end=old_end)
    print(f'wrote {n} tabs in 1 call')
    print('DONE raw100ppi')


if __name__ == '__main__':
    main()
