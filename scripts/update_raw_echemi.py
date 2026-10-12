# -*- coding: utf-8 -*-
"""Update the 15 *_echemi tabs of the 原料 spreadsheet from www.echemi.com.

Each tab has its own product page (row 1) and its own series key read from the
sheet, so no source-side filtering is needed - only the right chart of the page
has to be picked. Pages carry several echarts widgets (China Domestic / China
Regional / Enterprise); the winner is the one whose values overlap the tab's
own history (mean abs error over the shared dates), falling back to closeness
of the newest value when there is no overlap.

The site is behind an Aliyun slider, so Chrome is launched as a real process
with the saved .echemi_profile + echemi_cookies.json (headless Chromium is
always challenged); with --my-chrome (daily_sync default) it attaches to the
user's own verified session instead. Cookies are re-saved after every run.

Quota: one values_batch_get for all 15 tabs + one values_batch_update.
"""
import io
import os
import random
import sys
import time
from datetime import datetime

if __name__ == '__main__' and __package__ is None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import newsheet_lib as NS
import raw_lib as RL
from cdp_browser import (_iso, launch_echemi, my_chrome_requested, open_domestic,
                         save_echemi_cookies, shutdown_echemi, unblock)

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(HERE, '.echemi_profile')
CDP_PORT = 9335
MY_MODE = False

EXTRACT_JS = '''() => {
    const out = {title: document.title, charts: [], bodyLen: (document.body.innerText || '').length};
    document.querySelectorAll('[_echarts_instance_]').forEach(el => {
        const c = {label: '', inst: false};
        let n = el, hops = 0;
        while (n && hops < 6) {
            const sib = n.previousElementSibling;
            if (sib) {
                const t = (sib.innerText || '').trim();
                if (t && t.length < 140) { c.label = t.split('\\n').join(' | '); break; }
            }
            n = n.parentElement; hops++;
        }
        try {
            const inst = (window.echarts && echarts.getInstanceByDom(el)) || null;
            if (inst) {
                const opt = inst.getOption();
                c.inst = true;
                c.xAxis = opt.xAxis && opt.xAxis[0] && (opt.xAxis[0].data || opt.xAxis[0].categories);
                c.series = opt.series && opt.series.map(s => ({name: s.name, data: s.data}));
            }
        } catch (e) { c.err = String(e); }
        out.charts.push(c);
    });
    return out;
}'''


def launch():
    """(proc, pw, browser) — proc/pw are None in my-chrome mode."""
    global MY_MODE
    my_ok, browser, proc, pw = launch_echemi(PROFILE, CDP_PORT, my_chrome_requested())
    MY_MODE = my_ok
    return proc, pw, browser


_MY_TAB = None


def fetch(browser, url, label):
    """Charts of one product page, or None."""
    global _MY_TAB
    if MY_MODE:
        # one scratch tab reused across products: fewer new-tab signals
        if _MY_TAB is None:
            _MY_TAB = browser.contexts[0].new_page()
        return _fetch_page(_MY_TAB, url, label)
    ctx = browser.contexts[0]
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return _fetch_page(page, url, label)


def _fetch_page(page, url, label):
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=45000)
    except Exception as e:
        print(f'    {label}: goto err {str(e)[:70]}')
        return None
    if not unblock(page, url, label, manual_wait=45 if label == 'first' else 0):
        return None
    open_domestic(page)
    data = None
    for _ in range(6):
        try:
            data = page.evaluate(EXTRACT_JS)
        except Exception:
            data = None
        if data and any(c.get('inst') for c in data.get('charts') or []):
            break
        page.wait_for_timeout(1500)
    return data


def _num(v):
    if v is None or v == '' or v == '-':
        return None
    try:
        return float(str(v).replace(',', '').replace('元', ''))
    except ValueError:
        return None


def series_pairs(chart):
    xs = chart.get('xAxis') or []
    sers = chart.get('series') or []
    if not xs or not sers:
        return []
    s = max(sers, key=lambda s: sum(1 for v in (s.get('data') or []) if _num(v) is not None))
    out = []
    for x, v in zip(xs, s.get('data') or []):
        d, n = _iso(x), _num(v)
        if d and n is not None:
            out.append((d, n))
    return out


def pick_chart(charts, sheet_map, latest):
    best = None
    for c in charts or []:
        pairs = series_pairs(c)
        if not pairs:
            continue
        shared = [(d, v) for d, v in pairs if d in sheet_map]
        if shared:
            err = sum(abs(v - sheet_map[d]) for d, v in shared) / len(shared)
            score = (0, err, -len(shared))
        elif latest is not None:
            score = (1, abs(pairs[-1][1] - latest), 0)
        else:
            continue
        if best is None or score < best[0]:
            best = (score, pairs, c)
    if not best:
        return None, None
    return best[1], best[2]


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


def to_fresh(iso, price, k):
    d = datetime.strptime(iso, '%Y-%m-%d')
    row = [''] * k['width']
    row[0] = f'{d.month}/{d.day}/{d.year}'
    row[1], row[2], row[3], row[4] = k['name'], k['spec'], k['market'], k['dtype']
    pc = k['price_col']
    row[pc] = int(price) if price == int(price) else price
    if k['width'] > 10:
        row[10] = k['remark']
    return row


def main():
    global _MY_TAB
    sh = RL.open_sh()
    allt = RL.all_titles(sh)
    titles = []
    urls = {}
    res = RL.retry(sh.values_batch_get, [f"'{t}'!A1:A1" for t in allt],
                   params={'valueRenderOption': 'FORMULA'})
    for t, v in zip(allt, res['valueRanges']):
        vals = v.get('values') or [['']]
        u = vals[0][0] if vals and vals[0] else ''
        if 'echemi.com' in str(u):
            titles.append(t)
            urls[t] = u
    titles.sort()
    print(f'echemi: {len(titles)} tabs')
    if not titles:
        print('DONE raw_echemi')
        return

    grid = RL.read_grid(sh, titles)
    metas, keys, sheet_map = {}, {}, {}
    for t in titles:
        m = RL.analyze(grid[t])
        if m is None:
            print(f'  WARN {t}: no header, skipped')
            continue
        k = key_of(grid[t], m)
        if k is None:
            print(f'  WARN {t}: no data rows, skipped')
            continue
        metas[t] = m
        keys[t] = k
        smap, latest = {}, None
        for r in RL.data_rows(grid[t], m):
            iso = None
            d = NS.date_text(r[0])
            if d:
                try:
                    iso = datetime.strptime(d, '%m/%d/%Y').strftime('%Y-%m-%d')
                except ValueError:
                    pass
            if iso:
                price = RL._plain(r[m['price_col']])
                if price is not None:
                    smap[iso] = price
                    if latest is None:
                        latest = price
        sheet_map[t] = (smap, latest)

    fresh = {t: [] for t in titles}
    proc = None
    pw = None
    browser = None
    try:
        proc, pw, browser = launch()
        if not browser:
            print('SKIP: no browser')
            print('DONE raw_echemi')
            return
        first = True
        for t in titles:
            if t not in keys:
                continue
            data = fetch(browser, urls[t], 'first' if first else t)
            first = False
            time.sleep(random.uniform(4, 8))  # pace pages: keeps Aliyun risk low
            if not data or not data.get('charts'):
                print(f'  {t}: no charts')
                continue
            smap, latest = sheet_map[t]
            pairs, chart = pick_chart(data['charts'], smap, latest)
            if not pairs:
                print(f'  {t}: no usable chart among {len(data["charts"])}')
                continue
            shared = sum(1 for d, _ in pairs if d in smap)
            print(f'  {t}: {len(data["charts"])} charts -> {len(pairs)} points '
                  f'({shared} shared, latest {pairs[-1][0]}={pairs[-1][1]}) '
                  f'label={(chart.get("label") or "")[:50]!r}')
            for iso, price in pairs:
                fresh[t].append(to_fresh(iso, price, keys[t]))
        save_echemi_cookies(browser)
        if _MY_TAB is not None:
            try:
                _MY_TAB.close()
            except Exception:
                pass
            _MY_TAB = None
    finally:
        shutdown_echemi(browser, pw, proc, profile=PROFILE)

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
        if fresh[t]:
            print(f'  {t}: +{len(fresh[t])} fetched, rows {old_n} -> {new_n}')
        if new_n != old_n or fresh[t]:
            blocks[t] = built
            first_row[t] = metas[t]['first']
            old_end[t] = metas[t]['first'] + old_n - 1
    if not blocks:
        print('nothing new')
        print('DONE raw_echemi')
        return
    if '--dry' in sys.argv:
        print(f'[dry] would write {len(blocks)} tabs: '
              + ', '.join(f'{t}:{len(v)}' for t, v in sorted(blocks.items())))
        print('DONE raw_echemi')
        return
    n = RL.write_all(sh, blocks, first_row, old_end=old_end)
    print(f'wrote {n} tabs in 1 call')
    print('DONE raw_echemi')


if __name__ == '__main__':
    main()
