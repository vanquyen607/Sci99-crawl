# -*- coding: utf-8 -*-
"""Minimal CDP driver for the user's real Chrome.

Playwright's connect_over_cdp dies on Chrome 136+ with
"Browser.setDownloadBehavior: Browser context management is not supported",
so we talk raw DevTools Protocol over websocket. Only the tiny subset the
echemi scripts need is implemented: new tab, goto, evaluate JS, locator
(count/is_visible/bounding_box/click), mouse drag, cookies, close.

Usage:
    from cdp_browser import connect
    browser = connect('http://127.0.0.1:9222')
    page = browser.new_tab()
    page.goto('https://www.echemi.com/...')
"""
import json
import time
import urllib.request

from websockets.sync.client import connect as _ws_connect


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
        self.ws = _ws_connect(ws_url, max_size=64 * 1024 * 1024)
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
