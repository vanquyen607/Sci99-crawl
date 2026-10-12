# -*- coding: utf-8 -*-
"""Echemi browser layer: CDP driver, my-chrome mode, profile fallback, Aliyun slider.

Playwright's connect_over_cdp dies on Chrome 136+ with
"Browser.setDownloadBehavior: Browser context management is not supported",
so the driver talks raw DevTools Protocol over websocket (websockets lazily
imported). Only the subset the echemi scripts need is implemented:
new tab, goto, evaluate JS, locator, mouse drag, cookies, close.

Shared by update_raw_echemi.py / update_choline_echemi.py / daily_sync.py:
  - my-chrome mode: attach to the user's real Chrome on MY_CDP (port 9222,
    started by scripts/my_chrome.bat or ensure_scratch_chrome) - session is
    already verified => no Aliyun slider.
  - profile fallback: clean Chrome on scripts/.echemi_profile + its own CDP
    port, cookies injected from echemi_cookies.json.
  - Aliyun slider helpers (is_blocked/human_drag/unblock) work on both
    playwright pages and the raw cdp Tab.

Usage:
    from cdp_browser import connect, launch_echemi, unblock
"""
import io
import json
import os
import random
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ECHEMI_COOKIES = os.path.join(HERE, 'echemi_cookies.json')
SCRATCH_PROFILE = os.path.join(HERE, '.mychrome_profile')
MY_CDP = os.environ.get('SCI99_MY_CDP', 'http://127.0.0.1:9222')

CHROME_EXE = next((c for c in (
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Google\Chrome\Application\chrome.exe'),
) if os.path.exists(c)), None)

REAL_PROFILES = [
    os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Google\Chrome\User Data'),
]


# --------------------------------------------------------------------------
# raw CDP driver (playwright-free)
# --------------------------------------------------------------------------

class _Mouse:
    def __init__(self, tab):
        self.tab = tab
        self._down = False

    def move(self, x, y, steps=1):
        self.tab._mx, self.tab._my = float(x), float(y)
        self.tab.send('Input.dispatchMouseEvent', type='mouseMoved',
                      x=self.tab._mx, y=self.tab._my, button='none',
                      buttons=1 if self._down else 0)

    def down(self):
        self._down = True
        self.tab.send('Input.dispatchMouseEvent', type='mousePressed',
                      x=self.tab._mx, y=self.tab._my, button='left',
                      buttons=1, clickCount=1)

    def up(self):
        self.tab.send('Input.dispatchMouseEvent', type='mouseReleased',
                      x=self.tab._mx, y=self.tab._my, button='left',
                      buttons=0, clickCount=1)
        self._down = False


class _Locator:
    """Resolves itself inside the page via a JS snippet; .first is a no-op."""

    def __init__(self, tab, kind, value):
        self.tab = tab
        self.kind = kind          # 'css' | 'text' | 'parent'
        self.value = value

    @property
    def first(self):
        return self

    def locator(self, sub):
        if sub.strip() == '..':
            return _Locator(self.tab, 'parent', self)
        return _Locator(self.tab, 'css', sub)

    def _js(self):
        if self.kind == 'css':
            return f'document.querySelector({json.dumps(self.value)})'
        if self.kind == 'text':
            t = json.dumps(self.value)
            return ('(() => { for (const el of document.querySelectorAll('
                    "'a,button,span,div,li,td,th,em,strong,p,tab,i,b,label')) {"
                    f' if (((el.innerText || "").indexOf({t}) !== -1) && '
                    'el.getClientRects().length) return el; } return null; })()')
        # parent
        return f'(()=>{{ const e = {self.value._js()}; return e ? e.parentElement : null; }})()'

    def _with_el(self, body):
        return self.tab.evaluate(f'() => {{ const el = {self._js()}; if (!el) return null; {body} }}')

    def count(self):
        try:
            return 1 if self._with_el('return true;') else 0
        except Exception:
            return 0

    def is_visible(self, timeout=None):
        deadline = time.time() + ((timeout or 0) / 1000.0)
        while True:
            try:
                if self._with_el('return !!(el.getClientRects().length && '
                                 '(el.offsetWidth || el.offsetHeight || el.getClientRects().length));'):
                    return True
            except Exception:
                pass
            if time.time() >= deadline:
                return False
            time.sleep(0.2)

    def bounding_box(self):
        try:
            return self._with_el('const r = el.getBoundingClientRect();'
                                 'return {x: r.x, y: r.y, width: r.width, height: r.height};')
        except Exception:
            return None

    def click(self, timeout=None):
        self._with_el('el.click(); return true;')


class Tab:
    def __init__(self, ws, session_id, target_id, browser):
        self.ws = ws
        self.session_id = session_id
        self.target_id = target_id
        self.browser = browser
        self._id = 0
        self._mx = self._my = 0.0
        self.mouse = _Mouse(self)

    def send(self, method, **params):
        self._id += 1
        mid = self._id
        msg = {'id': mid, 'method': method, 'params': params}
        if self.session_id:
            msg['sessionId'] = self.session_id
        self.ws.send(json.dumps(msg))
        while True:
            raw = self.ws.recv(timeout=60)
            data = json.loads(raw)
            if data.get('id') == mid:
                if 'error' in data:
                    raise RuntimeError(f'{method}: {data["error"]}')
                return data.get('result') or {}

    def evaluate(self, expr):
        """expr is a "() => {...}" string (playwright style)."""
        r = self.send('Runtime.evaluate', expression=f'({expr})()',
                      returnByValue=True, awaitPromise=True)
        if r.get('exceptionDetails'):
            raise RuntimeError(str(r['exceptionDetails'].get('text')))
        return (r.get('result') or {}).get('value')

    def goto(self, url, wait_until=None, timeout=45000):
        self.send('Page.navigate', url=url)
        deadline = time.time() + (timeout or 45000) / 1000.0
        while time.time() < deadline:
            try:
                if self.evaluate('() => document.readyState') == 'complete':
                    return
            except Exception:
                pass
            time.sleep(0.3)

    def title(self):
        return self.evaluate('() => document.title')

    def wait_for_timeout(self, ms):
        time.sleep(max(0, ms) / 1000.0)

    def locator(self, sel):
        if sel.startswith('text='):
            return _Locator(self, 'text', sel[len('text='):])
        return _Locator(self, 'css', sel)

    def close(self):
        try:
            self.browser._close_target(self.target_id)
        except Exception:
            pass


class _Context:
    def __init__(self, browser):
        self.browser = browser

    @property
    def pages(self):
        return []

    def new_page(self, url='about:blank'):
        return self.browser.new_tab(url)

    def cookies(self):
        tab = self.browser._utility_tab()
        r = tab.send('Network.getAllCookies')
        return r.get('cookies') or []


class Browser:
    def __init__(self, ws_url):
        from websockets.sync.client import connect as ws_connect  # lazy: optional dep
        self.ws = ws_connect(ws_url, max_size=64 * 1024 * 1024)
        self._id = 0
        self._utility = None
        self.contexts = [_Context(self)]

    def send(self, method, **params):
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({'id': mid, 'method': method, 'params': params}))
        while True:
            data = json.loads(self.ws.recv(timeout=60))
            if data.get('id') == mid:
                if 'error' in data:
                    raise RuntimeError(f'{method}: {data["error"]}')
                return data.get('result') or {}

    def _utility_tab(self):
        if self._utility is None:
            self._utility = self.new_tab()
        return self._utility

    def new_tab(self, url='about:blank'):
        r = self.send('Target.createTarget', url=url, newWindow=False, background=False)
        target_id = r['targetId']
        a = self.send('Target.attachToTarget', targetId=target_id, flatten=True)
        tab = Tab(self.ws, a['sessionId'], target_id, self)
        for m in ('Page.enable', 'Runtime.enable', 'Network.enable'):
            try:
                tab.send(m)
            except Exception:
                pass
        if url and url != 'about:blank':
            tab.goto(url)
        return tab

    def _close_target(self, target_id):
        self.send('Target.closeTarget', targetId=target_id)

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def connect(cdp_url='http://127.0.0.1:9222'):
    ver = json.loads(urllib.request.urlopen(cdp_url + '/json/version', timeout=5).read())
    return Browser(ver['webSocketDebuggerUrl'])


# --------------------------------------------------------------------------
# my-chrome mode (user's real Chrome on port 9222, no slider)
# --------------------------------------------------------------------------

def my_chrome_requested(argv=None):
    argv = sys.argv if argv is None else argv
    return '--my-chrome' in argv or os.environ.get('SCI99_MY_CHROME') == '1'


def cdp_up(cdp_url=MY_CDP, timeout=2):
    try:
        urllib.request.urlopen(cdp_url + '/json/version', timeout=timeout)
        return True
    except Exception:
        return False


def _bootstrap_scratch_profile(log=print):
    """First run: copy Local State/Cookies/Preferences from the real Chrome
    profile into .mychrome_profile so the session passes echemi's slider."""
    if os.path.exists(os.path.join(SCRATCH_PROFILE, 'Local State')):
        return True  # already bootstrapped, its cookies persist + refresh
    real = next((p for p in REAL_PROFILES if os.path.exists(p)), None)
    if not real:
        return False
    try:
        os.makedirs(os.path.join(SCRATCH_PROFILE, 'Default', 'Network'), exist_ok=True)
        shutil.copy2(os.path.join(real, 'Local State'), os.path.join(SCRATCH_PROFILE, 'Local State'))
        for rel in (r'Default\Network\Cookies', r'Default\Preferences'):
            src = os.path.join(real, rel)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(SCRATCH_PROFILE, rel))
        return True
    except Exception as e:
        log(f'my-chrome: profile bootstrap failed: {e}')
        return False


def ensure_scratch_chrome(log=print):
    """Bootstrap + launch the scratch Chrome if needed (daily_sync hook).
    True when the echemi steps should run with --my-chrome."""
    if os.environ.get('SCI99_MY_CHROME') == '0':
        return False
    if cdp_up():
        log(f'my-chrome: attach to scratch Chrome at {MY_CDP}')
        return True
    if not CHROME_EXE or not _bootstrap_scratch_profile(log):
        log('my-chrome: no Chrome/profile found - echemi falls back to profile mode')
        return False
    subprocess.Popen(
        [CHROME_EXE,
         f'--user-data-dir={SCRATCH_PROFILE}',
         '--remote-debugging-port=9222',
         '--remote-allow-origins=*',
         '--no-first-run', '--no-default-browser-check',
         'https://www.echemi.com/'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    for _ in range(15):
        time.sleep(1)
        if cdp_up():
            log(f'my-chrome: scratch Chrome ready at {MY_CDP}')
            return True
    log('my-chrome: scratch Chrome did not come up - echemi falls back to profile mode')
    return False


# --------------------------------------------------------------------------
# profile-mode fallback (clean Chrome + saved cookies, own CDP port)
# --------------------------------------------------------------------------

def kill_profile_chrome(profile):
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
          f"Where-Object {{$_.CommandLine -like '*{profile}*'}} | "
          "ForEach-Object {Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue}")
    try:
        subprocess.run(['powershell', '-NoProfile', '-Command', ps], timeout=20,
                       capture_output=True)
    except Exception:
        pass


def launch_profile_cdp(profile, port, url=None, log=print):
    """Clean Chrome (no automation flags) on `profile`, CDP on `port`.
    Returns the Popen or None."""
    kill_profile_chrome(profile)  # stale instance from a crashed run
    time.sleep(1)
    os.makedirs(profile, exist_ok=True)
    for lf in ('lockfile', 'SingletonLock', 'SingletonCookie'):
        try:
            os.remove(os.path.join(profile, lf))
        except OSError:
            pass
    if not CHROME_EXE:
        log('SKIP: chrome.exe not found')
        return None
    args = [CHROME_EXE, f'--user-data-dir={profile}',
            f'--remote-debugging-port={port}', '--remote-allow-origins=*',
            '--no-first-run', '--no-default-browser-check']
    if url:
        args.append(url)
    try:
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        log(f'SKIP cannot launch chrome: {e}')
        return None
    for _ in range(40):
        if cdp_up(f'http://127.0.0.1:{port}'):
            return proc
        time.sleep(0.5)
    log('SKIP chrome CDP port not ready')
    try:
        proc.kill()
    except Exception:
        pass
    return None


def launch_echemi(profile, port, want_my, url=None, log=print):
    """Unified start for the echemi updaters.
    Returns (my_ok, browser, proc, pw): proc/pw are set in profile mode only."""
    if want_my:
        if cdp_up():
            try:
                browser = connect(MY_CDP)
                log(f'my-chrome: attached to {MY_CDP} (no slider)')
                return True, browser, None, None
            except Exception as e:
                log(f'my-chrome: CDP attach failed ({str(e)[:70]}) - profile chrome')
        else:
            log(f'my-chrome: {MY_CDP} not open (run scripts\\my_chrome.bat) - profile chrome')
    proc = launch_profile_cdp(profile, port, url=url, log=log)
    if proc is None:
        return False, None, None, None
    from playwright.sync_api import sync_playwright
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.connect_over_cdp(f'http://127.0.0.1:{port}')
        try:
            browser.contexts[0].add_cookies(json.load(open(ECHEMI_COOKIES, encoding='utf-8')))
        except Exception as e:
            log('cookie inject err', e)
        return False, browser, proc, pw
    except Exception as e:
        log(f'SKIP CDP connect failed: {e}')
        try:
            proc.kill()
        except Exception:
            pass
        return False, None, None, None


def shutdown_echemi(browser, pw, proc, profile=None, log=print):
    """Best-effort teardown; also kills the profile Chrome when profile given."""
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
    if profile:
        time.sleep(1)
        kill_profile_chrome(profile)


# --------------------------------------------------------------------------
# Aliyun slider (works on playwright pages and the raw cdp Tab)
# --------------------------------------------------------------------------

def is_blocked(page):
    try:
        t = (page.title() or '').strip()
        body = page.evaluate('() => (document.body.innerText || "").slice(0, 400)') or ''
    except Exception:
        return False, '', ''
    bl = body.lower()
    blocked = (('验证' in t) or ('slide' in bl) or ('滑动' in body) or ('verification' in bl))
    return blocked, t, body


def human_drag(page):
    """Aliyun slider with human-like physics (works headless and headed)."""
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


def unblock(page, url, label='', manual_wait=0, log=print):
    """Bring a challenged page back (up to 3 auto slides + optional manual wait).
    True when the page is usable."""
    pre = f'    {label}: ' if label else ''
    for attempt in range(1, 4):
        blocked, t, body = is_blocked(page)
        if not blocked:
            return True
        log(f'{pre}verification (title={t!r}) - slider attempt {attempt}')
        page.wait_for_timeout(2500)
        if not human_drag(page):
            log(f'{pre}slider widget not found')
            page.goto(url, wait_until='domcontentloaded', timeout=45000)
            page.wait_for_timeout(4000)
            continue
        page.wait_for_timeout(3500)
        blocked, t, body = is_blocked(page)
        if not blocked:
            log(f'{pre}slider PASSED')
            return True
        try:
            rf = page.locator('[class*=refresh], [id*=refresh]').first
            if rf.count() and rf.is_visible(timeout=800):
                rf.click()
                page.wait_for_timeout(2500)
        except Exception:
            pass
    if manual_wait:
        log(f'{pre}slide MANUALLY in the Chrome window (waiting {manual_wait}s)')
        for _ in range(manual_wait // 3):
            page.wait_for_timeout(3000)
            blocked, _, _ = is_blocked(page)
            if not blocked:
                log(f'{pre}manual slide PASSED')
                return True
    blocked, t, _ = is_blocked(page)
    log(f'{pre}SKIP, still on verification ({t!r})')
    return False


def save_echemi_cookies(browser, log=print):
    try:
        cks = browser.contexts[0].cookies()
        keep = [{k: c[k] for k in ('name', 'value', 'domain', 'path', 'expires',
                                   'httpOnly', 'secure', 'sameSite')
                 if k in c and c[k] not in (None, '')}
                for c in cks if 'echemi' in str(c.get('domain', ''))]
        if keep:
            json.dump(keep, open(ECHEMI_COOKIES, 'w', encoding='utf-8'),
                      ensure_ascii=False, indent=1)
            log(f'refreshed {len(keep)} echemi cookies')
    except Exception as e:
        log('cookie save err', e)


def open_domestic(page):
    """Click the China Domestic Price tab of the chart widget."""
    for sel in ('text=China Domestic Price', 'text=China Domestic', 'text=国内价格'):
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible(timeout=1200):
                loc.click(timeout=3000)
                page.wait_for_timeout(4000)
                return True
        except Exception:
            pass
    return False


def _iso(v):
    s = str(v or '').strip()
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


if __name__ == '__main__':
    # entry point of scripts/my_chrome.bat: bootstrap + open the scratch Chrome
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    ok = ensure_scratch_chrome()
    print('my-chrome ready' if ok else 'my-chrome FAILED')
    sys.exit(0 if ok else 1)
