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
always challenged). Cookies are re-saved after every successful run.

Quota: one values_batch_get for all 15 tabs + one values_batch_update.
"""
import io
import json
import os
import random
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

if __name__ == '__main__' and __package__ is None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import newsheet_lib as NS
import raw_lib as RL

HERE = os.path.dirname(os.path.abspath(__file__))
COOKIES = os.path.join(HERE, 'echemi_cookies.json')
PROFILE = os.path.join(HERE, '.echemi_profile')
CDP_PORT = 9335
CHROME_EXE = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
if not os.path.exists(CHROME_EXE):
    CHROME_EXE = r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'

# Attach to the USER's own Chrome (start it via scripts\my_chrome.bat, then run
# with --my-chrome): his echemi session is already verified => no Aliyun slider.
MY_CDP = os.environ.get('SCI99_MY_CDP', 'http://127.0.0.1:9222')
MY_MODE = False


def my_chrome_requested():
    return '--my-chrome' in sys.argv or os.environ.get('SCI99_MY_CHROME') == '1'


def my_chrome_ready():
    try:
        urllib.request.urlopen(MY_CDP + '/json/version', timeout=2)
        return True
    except Exception:
        return False


DOMESTIC = ['text=China Domestic Price', 'text=China Domestic', 'text=国内价格']

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


def kill_profile_chrome():
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
          f"Where-Object {{$_.CommandLine -like '*{PROFILE}*'}} | "
          "ForEach-Object {Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue}")
    try:
        subprocess.run(['powershell', '-NoProfile', '-Command', ps], timeout=20, capture_output=True)
    except Exception:
        pass


def is_blocked(page):
    try:
        t = (page.title() or '').strip()
        body = page.evaluate('() => (document.body.innerText || "").slice(0, 400)')
    except Exception:
        return False, '', ''
    body = body or ''
    bl = body.lower()
    blocked = (('验证' in t) or ('slide' in bl) or ('滑动' in body) or ('verification' in bl)
               or ('access verification' in bl))
    return blocked, t, body


def human_drag(page):
    """Aliyun slider with human-like physics on the clean Chrome."""
    box = track = None
    for sel in ['#aliyunCaptcha-sliding-slider', '[id*="sliding-slider"]']:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible(timeout=600):
                box = loc.bounding_box()
                if box:
                    try:
                        pb = loc.locator('..').bounding_box()
                        if pb and pb['width'] > box['width'] + 30:
                            track = pb
                    except Exception:
                        pass
                break
        except Exception:
            pass
    if not box:
        return False
    cx = box['x'] + box['width'] / 2
    cy = box['y'] + box['height'] / 2
    if track:
        dist = track['x'] + track['width'] - box['width'] / 2 - 3 - cx
        dist = max(60, min(340, dist))
    else:
        dist = random.randint(240, 300)
    dist += random.uniform(-2, 2)
    page.mouse.move(cx + random.uniform(-4, 0), cy + random.uniform(-3, 3), steps=4)
    time.sleep(random.uniform(0.08, 0.18))
    page.mouse.down()
    time.sleep(random.uniform(0.06, 0.14))
    steps = random.randint(40, 65)
    x = 0.0
    for i in range(steps):
        t = (i + 1) / steps
        if t < 0.3:
            eased = (t / 0.3) ** 1.4 * 0.35
        elif t < 0.85:
            eased = 0.35 + (t - 0.3) / 0.55 * 0.55
        else:
            eased = 0.90 + (1 - (t - 0.85) / 0.15) ** 2 * 0.10
        x = dist * eased
        jy = max(-2.0, min(2.0, random.gauss(0, 0.6)))
        page.mouse.move(cx + x, cy + jy, steps=1)
        if t > 0.9:
            time.sleep(random.uniform(0.04, 0.09))
        elif t > 0.6:
            time.sleep(random.uniform(0.015, 0.04))
        else:
            time.sleep(random.uniform(0.008, 0.025))
    page.mouse.move(cx + x + random.uniform(1.5, 4), cy + random.uniform(-1, 1), steps=2)
    time.sleep(random.uniform(0.06, 0.12))
    page.mouse.move(cx + x - random.uniform(0.5, 2.5), cy, steps=2)
    time.sleep(random.uniform(0.05, 0.1))
    page.mouse.up()
    time.sleep(random.uniform(0.9, 1.6))
    return True


def unblock(page, url, label, manual_wait=0):
    """Bring a challenged page back; returns True when the page is usable."""
    for attempt in range(1, 4):
        blocked, t, body = is_blocked(page)
        if not blocked:
            return True
        print(f'    {label}: verification (title={t!r}) - slider attempt {attempt}')
        page.wait_for_timeout(2500)
        if not human_drag(page):
            print(f'    {label}: slider widget not found')
            page.goto(url, wait_until='domcontentloaded', timeout=45000)
            page.wait_for_timeout(4000)
            continue
        page.wait_for_timeout(3500)
        blocked, t, body = is_blocked(page)
        if not blocked:
            print(f'    {label}: slider PASSED')
            return True
        try:
            rf = page.locator('[class*=refresh], [id*=refresh]').first
            if rf.count() and rf.is_visible(timeout=800):
                rf.click()
                page.wait_for_timeout(2500)
        except Exception:
            pass
    if manual_wait:
        print(f'    {label}: slide MANUALLY in the Chrome window (waiting {manual_wait}s)')
        for _ in range(manual_wait // 3):
            page.wait_for_timeout(3000)
            blocked, _, _ = is_blocked(page)
            if not blocked:
                print(f'    {label}: manual slide PASSED')
                return True
    blocked, t, _ = is_blocked(page)
    print(f'    {label}: SKIP, still on verification ({t!r})')
    return False


def save_cookies(browser):
    try:
        cks = browser.contexts[0].cookies()
        keep = [{k: c[k] for k in ('name', 'value', 'domain', 'path', 'expires',
                                   'httpOnly', 'secure', 'sameSite')
                 if k in c and c[k] not in (None, '')}
                for c in cks if 'echemi' in str(c.get('domain', ''))]
        if keep:
            json.dump(keep, open(COOKIES, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
            print(f'refreshed {len(keep)} echemi cookies')
    except Exception as e:
        print('cookie save err', e)


def launch():
    from playwright.sync_api import sync_playwright
    global MY_MODE
    if my_chrome_requested():
        if my_chrome_ready():
            MY_MODE = True
            try:
                from cdp_browser import connect as cdp_connect
                browser = cdp_connect(MY_CDP)
                print(f'my-chrome: attached to {MY_CDP} (your profile, no slider)')
                return None, browser
            except Exception as e:
                print(f'my-chrome: CDP attach failed ({str(e)[:70]}) - profile chrome')
        else:
            print(f'my-chrome: {MY_CDP} not open (run scripts\\my_chrome.bat) - profile chrome')
    kill_profile_chrome()
    time.sleep(1)
    os.makedirs(PROFILE, exist_ok=True)
    for lf in ('lockfile', 'SingletonLock', 'SingletonCookie'):
        try:
            os.remove(os.path.join(PROFILE, lf))
        except OSError:
            pass
    args = [CHROME_EXE, f'--user-data-dir={PROFILE}',
            f'--remote-debugging-port={CDP_PORT}', '--remote-allow-origins=*',
            '--no-first-run', '--no-default-browser-check']
    try:
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f'SKIP cannot launch chrome: {e}')
        return None, None
    for _ in range(40):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{CDP_PORT}/json/version', timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    else:
        print('SKIP chrome CDP port not ready')
        try:
            proc.kill()
        except Exception:
            pass
        return None, None
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.connect_over_cdp(f'http://127.0.0.1:{CDP_PORT}')
        try:
            browser.contexts[0].add_cookies(json.load(open(COOKIES, encoding='utf-8')))
        except Exception as e:
            print('cookie inject err', e)
        return (proc, pw), browser
    except Exception as e:
        print(f'SKIP CDP connect failed: {e}')
        try:
            proc.kill()
        except Exception:
            pass
        return None, None


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
    for sel in DOMESTIC:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible(timeout=1200):
                loc.click(timeout=3000)
                page.wait_for_timeout(3500)
                break
        except Exception:
            pass
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


def _iso(v):
    s = str(v or '').strip()
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
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
        proc, browser = launch()
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
        save_cookies(browser)
        if _MY_TAB is not None:
            try:
                _MY_TAB.close()
            except Exception:
                pass
            _MY_TAB = None
    finally:
        try:
            if browser:
                browser.close()
        except Exception:
            pass
        try:
            if pw:
                pw.stop()
        except Exception:
            pass
        try:
            if proc:
                proc.kill()
        except Exception:
            pass
        time.sleep(1)
        kill_profile_chrome()

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
