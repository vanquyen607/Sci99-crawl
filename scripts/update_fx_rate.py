# -*- coding: utf-8 -*-
"""Fill/repair 汇率 USD (USD/CNY) columns across ALL sheets from shibor 历史数据.

- FX-USD columns are discovered from each sheet's header row (cells containing
  '汇率'); each FX column uses its own block's 日期 column.
- A cell is rewritten when it is empty, an error value (#N/A, #REF!, ...), or
  not a sane USD/CNY rate (outside 4.0-10.0). Written values are plain text
  with a dot decimal, matching the 色氨酸 convention.
- The 汇率 source sheet itself is never modified.
"""
import re
import ssl
import time
from datetime import datetime, timedelta

import requests
import gspread
from google.oauth2.service_account import Credentials

# shibor/chinamoney uses legacy TLS renegotiation
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

CREDS = r'C:\Users\DELL\.openclaw\workspace\secrets\service_account.json'
SID = '1kuN8rT9shOellupamis9iyb6CpZFaWpao4VLdzZnQQU'
DATE_RE = re.compile(r'^\d{1,2}/\d{1,2}/\d{4}$')
API = 'https://www.shibor.net.cn/ags/ms/cm-u-bk-ccpr/CcprHisNew'
APPLY = True
MAX_DAYS_PER_CALL = 180
HEADER_SCAN_ROWS = 4
BATCH = 500          # ranges per batch_update call
SLEEP = 0.35         # between API calls
RETRY_WAITS = (25, 60)  # seconds to wait on 429/quota
# legacy phantom header (vitamins cols 0-18 block has header but no data)
EXCLUDE = {('维生素', 11)}


class _LegacyAdapter(requests.adapters.HTTPAdapter):
    """HTTPAdapter that allows unsafe legacy renegotiation (shibor TLS)."""

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.options |= 0x4
        if hasattr(ssl, 'OP_LEGACY_SERVER_CONNECT'):
            ctx.options |= getattr(ssl, 'OP_LEGACY_SERVER_CONNECT', 0)
        pool_kwargs['ssl_context'] = ctx
        pool_kwargs.setdefault('cert_reqs', 'CERT_NONE')
        self.poolmanager = requests.adapters.PoolManager(
            num_pools=connections, maxsize=maxsize, block=block, **pool_kwargs)


def parse_mdY(s):
    try:
        return datetime.strptime(str(s).strip(), '%m/%d/%Y')
    except Exception:
        return None


def iso(d):
    return d.strftime('%Y-%m-%d')


def mdY(d):
    return f'{d.month}/{d.day}/{d.year}'


def fetch_usd(start, end, session):
    params = {
        'startDate': iso(start),
        'endDate': iso(end),
        'currency': 'USD/CNY',
        'pageNum': 1,
        'pageSize': 500,
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Referer': 'https://www.shibor.net.cn/chinese/bkccpr/',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
    }
    urls = [
        API,
        API.replace('www.shibor.net.cn', 'www.chinamoney.com.cn'),
        'https://www.chinamoney.com.cn/ags/ms/cm-u-bk-ccpr/CcprHisNew',
    ]
    r = None
    last_err = None
    for u in urls:
        try:
            r = session.get(u, params=params, headers=headers, timeout=30, verify=False)
            r.raise_for_status()
            break
        except Exception as e:
            last_err = e
            r = None
    if r is None:
        raise last_err
    r.raise_for_status()
    data = r.json()
    records = data.get('records') or []
    out = {}
    for rec in records:
        d = rec.get('date')
        vals = rec.get('values') or []
        if d and vals and vals[0] not in (None, ''):
            try:
                out[d] = float(vals[0])
            except ValueError:
                pass
    return out


def needs_fill(v):
    """Empty / error / not a sane USD/CNY rate. Strict 4-decimal matching was
    abandoned: write_tab round-trips K through USER_ENTERED, Sheets stores it
    as a number and FORMATTED drops trailing zeros ('6.7580' -> '6.758'),
    which re-flagged correct cells on every run (daily rewrite churn)."""
    s = str(v or '').strip()
    if not s:
        return True
    if s.startswith('#'):
        return True
    try:
        f = float(s.replace(',', '.'))   # legacy EU '6,7489' -> repaired
    except ValueError:
        return True
    return not (4.0 <= f <= 10.0)


def retry_call(fn, *args, **kwargs):
    waits = list(RETRY_WAITS)
    while True:
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            msg = str(e)
            if ('429' in msg or 'Quota' in msg or 'quota' in msg) and waits:
                w = waits.pop(0)
                print(f'    quota hit, waiting {w}s...', flush=True)
                time.sleep(w)
                continue
            raise


def find_header(vals):
    for i, row in enumerate(vals[:HEADER_SCAN_ROWS]):
        cells = [str(v).strip() for v in row]
        if '日期' in cells:
            return i, cells
    return None, None


def rate_for(pd, by_mdY):
    rate = by_mdY.get(mdY(pd))
    if rate is not None:
        return rate
    for delta in range(1, 22):  # nearest previous trading day (holidays)
        prev = pd - timedelta(days=delta)
        rate = by_mdY.get(mdY(prev))
        if rate is not None:
            return rate
    return None


def main():
    creds = Credentials.from_service_account_file(
        CREDS, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    sh = gspread.authorize(creds).open_by_key(SID)

    # 1) plan: discover FX cols + cells needing fill
    plan = {}   # title -> (worksheet, [(fx_col, date_col)], [(ri, fx_col, pd)])
    min_d = max_d = None
    total_need = 0
    for ws in sh.worksheets():
        title = ws.title
        if title == '汇率':
            continue
        vals = retry_call(ws.get_all_values)
        hi, cells = find_header(vals)
        if hi is None:
            print(f'{title}: SKIP (no header row found)')
            continue
        date_cols = [j for j, c in enumerate(cells) if c == '日期']
        fx_cols = [j for j, c in enumerate(cells)
                   if '汇率' in c and (title, j) not in EXCLUDE]
        mapping = []
        for fc in fx_cols:
            dcs = [dc for dc in date_cols if dc <= fc]
            if dcs:
                mapping.append((fc, max(dcs)))
        if not mapping or not date_cols:
            print(f'{title}: SKIP (date_cols={date_cols} fx_cols={fx_cols})')
            time.sleep(SLEEP)
            continue
        targets = []
        for ri in range(hi + 1, len(vals)):
            row = vals[ri]
            for fc, dc in mapping:
                if dc >= len(row):
                    continue
                d = str(row[dc]).strip()
                if not DATE_RE.match(d):
                    continue
                pd = parse_mdY(d)
                if not pd:
                    continue
                cur = row[fc] if fc < len(row) else ''
                if not needs_fill(cur):
                    continue
                targets.append((ri, fc, pd))
                min_d = pd if min_d is None or pd < min_d else min_d
                max_d = pd if max_d is None or pd > max_d else max_d
        plan[title] = (ws, mapping, targets)
        total_need += len(targets)
        print(f'{title}: header r{hi+1} fx={mapping} need={len(targets)}', flush=True)
        time.sleep(SLEEP)

    if not total_need:
        print('nothing to fill')
        return
    print(f'TOTAL need={total_need} range: {min_d:%Y-%m-%d} .. {max_d:%Y-%m-%d}')

    # 2) fetch USD/CNY history once for the whole range
    fetch_lo = min_d - timedelta(days=30)
    session = requests.Session()
    session.mount('https://', _LegacyAdapter())
    by_mdY = {}
    cur_d = fetch_lo
    while cur_d <= max_d:
        chunk_end = min(cur_d + timedelta(days=MAX_DAYS_PER_CALL - 1), max_d)
        try:
            got = fetch_usd(cur_d, chunk_end, session)
            for iso_d, rate in got.items():
                try:
                    by_mdY[mdY(datetime.strptime(iso_d, '%Y-%m-%d'))] = rate
                except ValueError:
                    pass
            print(f'  fetched {iso(cur_d)}..{iso(chunk_end)}: {len(got)} rows (total {len(by_mdY)})', flush=True)
        except Exception as e:
            print(f'  ERR {iso(cur_d)}..{iso(chunk_end)}: {e}', flush=True)
        cur_d = chunk_end + timedelta(days=1)
        time.sleep(0.4)
    print(f'fx map size: {len(by_mdY)}')
    if not by_mdY:
        print('no FX data fetched, aborting')
        return

    # 3) write per sheet
    grand_wrote = 0
    grand_missed = []
    for title, (ws, mapping, targets) in plan.items():
        if not targets:
            continue
        updates = []
        missed = 0
        for ri, fc, pd in targets:
            rate = rate_for(pd, by_mdY)
            if rate is None:
                missed += 1
                grand_missed.append((title, mdY(pd)))
                continue
            cell = gspread.utils.rowcol_to_a1(ri + 1, fc + 1)
            updates.append({'range': cell, 'values': [[f'{rate:.4f}']]})
        wrote = 0
        for i in range(0, len(updates), BATCH):
            chunk = updates[i:i + BATCH]
            retry_call(ws.batch_update, chunk, value_input_option='RAW')
            wrote += len(chunk)
            time.sleep(SLEEP)
        grand_wrote += wrote
        # verify: recount remaining needs
        left = 0
        if wrote:
            vals2 = retry_call(ws.get_all_values)
            hi2, cells2 = find_header(vals2)
            if hi2 is not None:
                date_cols = [j for j, c in enumerate(cells2) if c == '日期']
                fx_cols = [j for j, c in enumerate(cells2)
                           if '汇率' in c and (title, j) not in EXCLUDE]
                for fc in fx_cols:
                    dcs = [dc for dc in date_cols if dc <= fc]
                    if not dcs:
                        continue
                    dc = max(dcs)
                    for ri in range(hi2 + 1, len(vals2)):
                        row = vals2[ri]
                        if dc >= len(row) or not DATE_RE.match(str(row[dc]).strip()):
                            continue
                        cur = row[fc] if fc < len(row) else ''
                        if needs_fill(cur):
                            left += 1
            time.sleep(SLEEP)
        print(f'{title}: wrote={wrote} missed={missed} remaining_need={left}', flush=True)

    print(f'DONE wrote_total={grand_wrote} missed_total={len(grand_missed)}')
    if grand_missed:
        print('missed sample:', grand_missed[:15])


if __name__ == '__main__':
    main()
