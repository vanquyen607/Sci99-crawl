# -*- coding: utf-8 -*-
"""Daily: fetch China Domestic choline chloride 60% from echemi (real-Chrome profile +
injected verification cookies) and append new dates into sheet 氯化胆碱 block2 (col T/19).
Slider: 3 auto-drags to the full right end, then wait up to 75s for a manual drag.
Non-core step: SKIP (exit 0) when blocked or no new data.
"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

HERE = os.path.dirname(os.path.abspath(__file__))
CREDS = r'C:\Users\DELL\.openclaw\workspace\secrets\service_account.json'
SID = '1kuN8rT9shOellupamis9iyb6CpZFaWpao4VLdzZnQQU'
SHEET = '氯化胆碱_echemi'
URL = 'https://www.echemi.com/productsInformation/pid_Rock3892-cholinechloride.html'
PROFILE = os.path.join(HERE, '.echemi_profile')
CDP_PORT = 9333
START = 0
WIDTH = 17
HEADER_ROWS = 2

import newsheet_lib
from cdp_browser import (is_blocked, launch_echemi,
                         save_echemi_cookies, shutdown_echemi, unblock)

EXTRACT_JS = '''() => {
    const out = {echarts: null, title: document.title, bodyLen: 0};
    try {
        const els = [...document.querySelectorAll('[_echarts_instance_]')];
        els.sort((a, b) => {
            const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
            return ((ra.top + window.scrollY) - (rb.top + window.scrollY)) ||
                   (ra.left - rb.left);
        });
        els.forEach(el => {
            try {
                const inst = (window.echarts && echarts.getInstanceByDom(el)) || null;
                if (inst) {
                    const opt = inst.getOption();
                    out.echarts = out.echarts || [];
                    out.echarts.push({
                        xAxis: opt.xAxis && opt.xAxis[0] && (opt.xAxis[0].data || opt.xAxis[0].categories),
                        series: opt.series && opt.series.map(s => ({name: s.name, data: s.data}))
                    });
                }
            } catch (e) {}
        });
    } catch (e) { out.err = String(e); }
    out.bodyLen = (document.body.innerText || '').length;
    return out;
}'''


def parse_date(s):
    s = str(s or '').strip()
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def date_key(s):
    return parse_date(s) or datetime(1900, 1, 1)


def fetch_echemi():
    browser, proc, pw = launch_echemi(PROFILE, CDP_PORT, url=URL)
    if not browser:
        print('SKIP: no browser')
        return None
    data = None
    try:
        ctx = browser.contexts[0]
        page = None
        for pg in ctx.pages:
            if 'echemi.com' in pg.url:
                page = pg
                break
        if page is None:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            data = _grab(page, browser)
        except Exception as e:
            print(f'fetch error: {e}')
    finally:
        shutdown_echemi(browser, pw, proc, profile=PROFILE)
    return data


def _grab(page, browser):
    """Navigate, pass the slider if any, extract the domestic chart. None on failure."""
    page.goto(URL, wait_until='domcontentloaded', timeout=45000)

    blocked, t, body = False, '', ''
    for _ in range(12):
        page.wait_for_timeout(2000)
        blocked, t, body = is_blocked(page)
        if blocked or len(body) > 400:
            break
    print(f'page title={t!r} blocked={blocked}')
    if not unblock(page, URL, 'choline', manual_wait=75 if blocked else 0):
        print('>>> verification failed - drag the slider by hand in the Chrome '
              'window and run this script again (session/cookies are kept)')
        return None

    save_echemi_cookies(browser)  # auto-refresh: store new acw_tc etc.
    page.wait_for_timeout(2500)
    data = page.evaluate(EXTRACT_JS)
    if not data.get('echarts'):
        print(f'no echarts data (bodyLen={data.get("bodyLen")})')
        data = None
    return data


def main():
    data = fetch_echemi()
    if not data:
        print('SKIP: could not extract echemi chart (captcha or empty)')
        return 0

    # chart #0 (đầu trang, sort theo y) = widget Market Price với tab
    # China Domestic Price active sẵn từ URL A1 — không cần click tab.
    domestic = None
    for ch in data.get('echarts') or []:
        xs = ch.get('xAxis') or []
        series = ch.get('series') or []
        if not xs or not series:
            continue
        best = None
        for s in series:
            vals2 = []
            for d in s.get('data') or []:
                try:
                    vals2.append(float(str(d).replace(',', '')))
                except Exception:
                    vals2.append(None)
            n = sum(1 for v in vals2 if v is not None)
            if n and (best is None or n > best[0]):
                best = (n, vals2)
        if not best:
            continue
        domestic = [(x, v) for x, v in zip(xs, best[1]) if v is not None]
        break
    if not domestic:
        print('SKIP: domestic series not found in charts')
        return 0
    print('domestic:', domestic)

    creds = Credentials.from_service_account_file(CREDS, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    sh = gspread.authorize(creds).open_by_key(SID)
    ws = sh.worksheet(SHEET)
    block_rows = newsheet_lib.read_formula_rows(ws, HEADER_ROWS + 1, WIDTH)
    block_rows = [blk for blk in block_rows if str(blk[0]).strip()]
    if not block_rows:
        print('SKIP: no existing rows in block')
        return 0
    print('block rows', len(block_rows), 'latest', block_rows[0][0])

    existing = {}
    for blk in block_rows:
        d = parse_date(blk[0])
        if d:
            existing[d.strftime('%Y-%m-%d')] = blk

    adds, replaces = [], []
    for ds, price in domestic:
        d = parse_date(ds)
        if not d:
            continue
        iso = d.strftime('%Y-%m-%d')
        blk = existing.get(iso)
        if blk is not None:
            try:
                old_p = float(str(blk[7]).replace(',', ''))
            except Exception:
                old_p = None
            if old_p is not None and abs(old_p - price) > 1e-9:
                replaces.append((iso, old_p, price))
                blk[7] = str(int(price)) if float(price) == int(price) else str(price)
            continue
        adds.append((d, iso, price))
    if replaces:
        print('REPLACE (giá domestic khác sheet):',
              [(i, o, n) for i, o, n in replaces])
    if not adds and not replaces:
        print('SKIP: no new dates (chart dates already in sheet)')
        return 0
    print('adds:', [(i, p) for _, i, p in adds])

    for d, iso, price in adds:
        row = [''] * WIDTH
        row[0] = f'{d.month}/{d.day}/{d.year}'
        row[1] = '氯化胆碱'
        row[2] = '60%'
        row[3] = '国产'
        row[4] = '市场价'
        row[7] = str(int(price)) if float(price) == int(price) else str(price)
        # chg/pct (col8/9) left empty — write_tab regenerates them as formulas
        block_rows.append(row)
        print('ADD', row[:11])

    block_rows.sort(key=lambda r: date_key(r[0]), reverse=True)

    newsheet_lib.write_tab(ws, block_rows, HEADER_ROWS + 1, WIDTH)
    print('update n', len(block_rows))

    vals2 = ws.get_all_values()
    for i in range(2, 5):
        print(f'R{i+1}', vals2[i][START:START + 11])
    print('DONE (FX col left empty — update_fx_rate fills it)')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
