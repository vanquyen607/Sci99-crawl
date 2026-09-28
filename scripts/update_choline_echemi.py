# -*- coding: utf-8 -*-
"""Daily: fetch China Domestic choline chloride 60% from echemi (real-Chrome profile +
injected verification cookies) and append new dates into sheet 氯化胆碱 block2 (col T/19).
Non-core step: SKIP (exit 0) when blocked or no new data.
"""
import sys, io, os, re, json, time, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
CREDS = r'C:\Users\DELL\.openclaw\workspace\secrets\service_account.json'
SID = '1kuN8rT9shOellupamis9iyb6CpZFaWpao4VLdzZnQQU'
SHEET = '氯化胆碱_echemi'
URL = 'https://www.echemi.com/productsInformation/pid_Rock3892-cholinechloride.html'
COOKIES = os.path.join(HERE, 'echemi_cookies.json')
PROFILE = os.path.join(HERE, '.echemi_profile')
START = 0
WIDTH = 17
HEADER_ROWS = 2

import newsheet_lib

EXTRACT_JS = '''() => {
    const out = {echarts: null, title: document.title, bodyLen: 0};
    try {
        document.querySelectorAll('[_echarts_instance_]').forEach(el => {
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


def fmt_change(v):
    a = f'{abs(v):.2f}'.replace('.', ',')
    if v < 0:
        return f'-{a} '
    if v == 0:
        return ' 0,00 '
    return f' {a} '


def fmt_pct(cur, prev):
    if not prev:
        return '0,00%'
    p = (cur - prev) / prev * 100
    a = f'{abs(p):.2f}'.replace('.', ',')
    return f'-{a}%' if p < 0 else f'{a}%'


CHROME_EXE = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
if not os.path.exists(CHROME_EXE):
    CHROME_EXE = r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'
CDP_PORT = 9333


def is_blocked(page):
    try:
        t = (page.title() or '').strip()
        body = page.evaluate('() => (document.body.innerText || "").slice(0, 400)')
    except Exception:
        return False, '', ''
    bl = body.lower()
    blocked = (('验证' in t) or ('slide' in bl) or ('滑动' in body) or ('verification' in bl)
               or ('access verification' in bl))
    return blocked, t, body


def human_drag(page):
    """Aliyun slider drag with human-like physics on a CLEAN Chrome (no automation flags)."""
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
        dist = max(60, min(dist, 340))
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
            eased = 0.90 + (1 - (1 - (t - 0.85) / 0.15) ** 2) * 0.10
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


def save_cookies(browser):
    try:
        cks = browser.contexts[0].cookies()
        keep = [c for c in cks if 'echemi' in c['domain']]
        if keep:
            json.dump(keep, open(COOKIES, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
            print(f'refreshed {len(keep)} echemi cookies -> {os.path.basename(COOKIES)}')
    except Exception as e:
        print('cookie save err', e)


def kill_profile_chrome():
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
          f"Where-Object {{$_.CommandLine -like '*{PROFILE}*'}} | "
          "ForEach-Object {{Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue}}")
    try:
        import subprocess
        subprocess.run(['powershell', '-NoProfile', '-Command', ps], timeout=20,
                       capture_output=True)
    except Exception:
        pass


def fetch_echemi():
    from playwright.sync_api import sync_playwright
    import subprocess
    import urllib.request

    kill_profile_chrome()  # stale instance from a crashed run
    time.sleep(1)
    os.makedirs(PROFILE, exist_ok=True)
    for lf in ('lockfile', 'SingletonLock', 'SingletonCookie'):
        try:
            os.remove(os.path.join(PROFILE, lf))
        except OSError:
            pass

    # launch CLEAN Chrome (subprocess — no playwright flags, navigator.webdriver=false)
    args = [CHROME_EXE, f'--user-data-dir={PROFILE}',
            f'--remote-debugging-port={CDP_PORT}', '--remote-allow-origins=*',
            '--no-first-run', '--no-default-browser-check', URL]
    try:
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f'SKIP: cannot launch chrome: {e}')
        return None
    port_ok = False
    for _ in range(40):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{CDP_PORT}/json/version', timeout=2)
            port_ok = True
            break
        except Exception:
            time.sleep(0.5)
    if not port_ok:
        print('SKIP: chrome CDP port not ready')
        try:
            proc.kill()
        except Exception:
            pass
        return None

    data = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f'http://127.0.0.1:{CDP_PORT}')
            ctx = browser.contexts[0]
            page = None
            for pg in ctx.pages:
                if 'echemi.com' in pg.url:
                    page = pg
                    break
            if page is None:
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
            # belt-and-braces: inject saved cookies (profile already has them too)
            try:
                saved = json.load(open(COOKIES, encoding='utf-8'))
                ctx.add_cookies(saved)
            except Exception as ce:
                print('cookie inject err', ce)
            page.goto(URL, wait_until='domcontentloaded', timeout=45000)

            blocked, t, body = False, '', ''
            for _ in range(12):
                page.wait_for_timeout(2000)
                blocked, t, body = is_blocked(page)
                if blocked or len(body) > 400:
                    break
            print(f'page title={t!r} blocked={blocked}')

            if blocked:
                page.wait_for_timeout(3000)
                for attempt in range(1, 4):
                    print(f'slider attempt {attempt}')
                    if not human_drag(page):
                        print('slider not found')
                        break
                    page.wait_for_timeout(4000)
                    blocked, t, body = is_blocked(page)
                    if not blocked:
                        print('slider PASSED')
                        break
                    # refresh widget for next attempt
                    try:
                        rf = page.locator('[class*=refresh], [id*=refresh]').first
                        if rf.count() and rf.is_visible(timeout=800):
                            rf.click()
                            page.wait_for_timeout(2500)
                    except Exception:
                        page.goto(URL, wait_until='domcontentloaded', timeout=45000)
                        page.wait_for_timeout(5000)

            blocked, t, body = is_blocked(page)
            if blocked:
                print('>>> auto slider failed — slide MANUALLY in the Chrome window (waiting 75s) <<<')
                for _ in range(25):
                    page.wait_for_timeout(3000)
                    blocked, t, body = is_blocked(page)
                    if not blocked:
                        print('manual slide PASSED')
                        break
            blocked, t, body = is_blocked(page)
            if blocked:
                print(f'SKIP: verification not passed (title={t!r}) — open echemi in your real Chrome once, '
                      f'then re-export echemi_cookies.json (see SKILL.md Troubleshooting)')
                try:
                    browser.close()
                except Exception:
                    pass
                return None

            save_cookies(browser)  # auto-refresh: store new acw_tc etc.

            for sel in ['text=China Domestic Price', 'text=China Domestic', 'text=国内价格']:
                try:
                    loc = page.locator(sel).first
                    if loc.count() and loc.is_visible(timeout=1200):
                        loc.click(timeout=3000)
                        page.wait_for_timeout(4000)
                        break
                except Exception:
                    pass
            page.wait_for_timeout(2500)
            data = page.evaluate(EXTRACT_JS)
            if not data.get('echarts'):
                print(f'no echarts data (bodyLen={data.get("bodyLen")})')
                data = None
            try:
                browser.close()
            except Exception:
                pass
    except Exception as e:
        print(f'fetch error: {e}')
    finally:
        try:
            proc.kill()
        except Exception:
            pass
        time.sleep(1)
        kill_profile_chrome()
    return data


def main():
    data = fetch_echemi()
    if not data:
        print('SKIP: could not extract echemi chart (captcha or empty)')
        return 0

    # pick domestic series: values in 5000..8000, closest to sheet's latest price
    creds = Credentials.from_service_account_file(CREDS, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    sh = gspread.authorize(creds).open_by_key(SID)
    ws = sh.worksheet(SHEET)
    block_rows = newsheet_lib.read_formula_rows(ws, HEADER_ROWS + 1, WIDTH)

    sheet_latest_price = None
    for blk in block_rows:
        if not str(blk[0]).strip():
            continue
        if sheet_latest_price is None:
            try:
                sheet_latest_price = float(str(blk[7]).replace(',', ''))
            except Exception:
                pass
    block_rows = [blk for blk in block_rows if str(blk[0]).strip()]
    if not block_rows:
        print('SKIP: no existing rows in block')
        return 0
    print('block rows', len(block_rows), 'latest', block_rows[0][0], 'latest price', sheet_latest_price)

    domestic = None
    best_diff = None
    for ch in data.get('echarts') or []:
        xs = ch.get('xAxis') or []
        series = ch.get('series') or []
        if not xs or not series:
            continue
        vals2 = []
        for d in series[0].get('data') or []:
            try:
                vals2.append(float(str(d).replace(',', '')))
            except Exception:
                pass
        if not vals2 or not all(5000 <= v <= 8000 for v in vals2):
            continue
        diff = abs(vals2[-1] - (sheet_latest_price or vals2[-1]))
        if best_diff is None or diff < best_diff:
            best_diff = diff
            domestic = list(zip(xs, vals2))
    if not domestic:
        print('SKIP: domestic series not found in charts')
        return 0
    print('domestic:', domestic)

    existing = {}
    for blk in block_rows:
        d = parse_date(blk[0])
        if d:
            existing[d.strftime('%Y-%m-%d')] = blk

    adds = []
    for ds, price in domestic:
        d = parse_date(ds)
        if not d:
            continue
        iso = d.strftime('%Y-%m-%d')
        if iso in existing:
            print('exists', iso)
            continue
        adds.append((d, iso, price))
    if not adds:
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
