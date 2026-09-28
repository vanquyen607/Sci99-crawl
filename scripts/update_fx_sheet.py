# -*- coding: utf-8 -*-
"""Update 汇率 sheet from shibor CcprHisNew (all 25 pairs, 历史数据)."""
import re, time
from datetime import datetime, timedelta

import ssl
import requests
import gspread
from google.oauth2.service_account import Credentials

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.options |= 0x4
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE
try:
    _SSL_CTX.options |= getattr(ssl, 'OP_LEGACY_SERVER_CONNECT', 0)
except Exception:
    pass
_requests_kwargs = {}
try:
    import urllib3
    urllib3.disable_warnings()
    _requests_kwargs['verify'] = False
except Exception:
    pass

CREDS = r'C:\Users\DELL\.openclaw\workspace\secrets\service_account.json'
SID = '1kuN8rT9shOellupamis9iyb6CpZFaWpao4VLdzZnQQU'
SHEET = '汇率'
API = 'https://www.shibor.net.cn/ags/ms/cm-u-bk-ccpr/CcprHisNew'
DATE_RE = re.compile(r'^\d{1,2}/\d{1,2}/\d{4}$')
MAX_DAYS_PER_CALL = 180
APPLY = True


class _LegacyAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.options |= 0x4
        if hasattr(ssl, 'OP_LEGACY_SERVER_CONNECT'):
            ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
        pool_kwargs['ssl_context'] = ctx
        pool_kwargs.setdefault('cert_reqs', 'CERT_NONE')
        self.poolmanager = requests.adapters.PoolManager(
            num_pools=maxsize, maxsize=maxsize, block=block, **pool_kwargs)


def parse_mdY(s):
    try:
        return datetime.strptime(str(s).strip(), '%m/%d/%Y')
    except Exception:
        return None


def iso(d):
    return d.strftime('%Y-%m-%d')


def mdY(d):
    return f'{d.month}/{d.day}/{d.year}'


def fmt_eu(v):
    """API '6.7489' -> sheet '6,7489' (4dp, EU comma)."""
    try:
        return f'{float(v):.4f}'.replace('.', ',')
    except Exception:
        return str(v)


def fetch_all(start: datetime, end: datetime, session: requests.Session):
    """No currency param → all 25 pairs. Returns (head, {iso_date: [eu_vals]})."""
    params = {
        'startDate': iso(start),
        'endDate': iso(end),
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
            r = session.get(u, params=params, headers=headers, timeout=30,
                            **_requests_kwargs)
            r.raise_for_status()
            break
        except Exception as e:
            last_err = e
            r = None
    if r is None:
        raise last_err
    r.raise_for_status()
    data = r.json()
    head = (data.get('data') or {}).get('head') or []
    out = {}
    for rec in data.get('records') or []:
        d = rec.get('date')
        vals = rec.get('values') or []
        if d and vals:
            out[d] = [fmt_eu(v) for v in vals]
    return head, out


def main():
    creds = Credentials.from_service_account_file(
        CREDS, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    sh = gspread.authorize(creds).open_by_key(SID)
    ws = sh.worksheet(SHEET)
    vals = ws.get_all_values()
    print(f'rows={len(vals)}')

    header = vals[0]
    ncols = len(header)
    print(f'header_cols={ncols} first={header[0]!r} c1={header[1]!r}')

    # split date rows vs footer/blank (keep order for footer)
    date_rows = []  # (mdY_str, datetime, row_list)
    footer = []
    max_d = None
    existing = {}
    for r in vals[1:]:
        d0 = str(r[0]).strip() if r else ''
        if DATE_RE.match(d0):
            pd = parse_mdY(d0)
            if pd:
                # normalize col0 display
                norm = mdY(pd)
                row = list(r[:ncols]) + [''] * (ncols - len(r))
                row[0] = norm
                date_rows.append((norm, pd, row))
                existing[norm] = row
                if max_d is None or pd > max_d:
                    max_d = pd
        else:
            # keep trailing footer rows (数据来源 etc.)
            if any(str(c).strip() for c in r) or footer:
                footer.append(list(r[:ncols]) + [''] * (ncols - len(r)))

    print(f'date_rows={len(date_rows)} max={mdY(max_d) if max_d else None} footer={len(footer)}')

    if max_d is None:
        print('no date rows found')
        return

    # fetch from max_d (inclusive, for overlap/corrections) → today
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    fetch_start = max_d  # include max for boundary update
    fetch_end = today
    if fetch_end < fetch_start:
        print('sheet already ahead of today')
        return

    session = requests.Session()
    session.mount('https://', _LegacyAdapter())
    fx = {}  # iso -> [eu]
    head = []
    cur = fetch_start
    while cur <= fetch_end:
        chunk_end = min(cur + timedelta(days=MAX_DAYS_PER_CALL - 1), fetch_end)
        h, got = fetch_all(cur, chunk_end, session)
        if h:
            head = h
        fx.update(got)
        print(f'  fetched {iso(cur)}..{iso(chunk_end)}: {len(got)} rows (total {len(fx)})')
        cur = chunk_end + timedelta(days=1)
        time.sleep(0.3)

    if head:
        # verify head matches sheet cols 1..
        sheet_pairs = header[1:1 + len(head)]
        if list(head) != list(sheet_pairs):
            print('WARN head mismatch:')
            print('  api :', head)
            print('  sheet:', sheet_pairs)

    print(f'fx dates={len(fx)} range={min(fx) if fx else None}..{max(fx) if fx else None}')

    # build updates: new dates + changed existing
    new_rows = []  # (pd, row)
    changed = []  # (mdY, new_row)
    api_by_mdY = {}
    for iso_d, eu_vals in fx.items():
        try:
            pd = datetime.strptime(iso_d, '%Y-%m-%d')
        except ValueError:
            continue
        norm = mdY(pd)
        row = [norm] + list(eu_vals)
        # pad/truncate to ncols
        row = (row + [''] * ncols)[:ncols]
        api_by_mdY[norm] = (pd, row)

    for norm, (pd, row) in api_by_mdY.items():
        if norm not in existing:
            new_rows.append((pd, row))
        else:
            old = existing[norm]
            # compare value cols (ignore col0 formatting)
            if old[1:] != row[1:]:
                changed.append((norm, row))

    new_rows.sort(key=lambda x: x[0], reverse=True)  # desc
    print(f'new_dates={len(new_rows)} changed={len(changed)}')
    if new_rows[:5]:
        print('  new sample:', [mdY(p) for p, _ in new_rows[:5]])
    if changed[:5]:
        print('  changed sample:', [c[0] for c in changed[:5]])

    if not new_rows and not changed:
        print('nothing to update')
        return

    if not APPLY:
        print('DRY-RUN')
        for p, r in new_rows[:10]:
            print('  NEW', r[:4])
        for n, r in changed[:10]:
            print('  CHG', n, r[:4])
        return

    # rebuild full sheet: header + merged date rows (desc) + footer
    merged = {}
    for norm, pd, row in date_rows:
        merged[norm] = (pd, row)
    for norm, row in changed:
        # keep original pd from key
        pd = parse_mdY(norm)
        merged[norm] = (pd, row)
    for pd, row in new_rows:
        merged[mdY(pd)] = (pd, row)

    sorted_dates = sorted(merged.values(), key=lambda x: x[0], reverse=True)
    all_rows = [header] + [r for _, r in sorted_dates] + footer
    # ensure uniform ncols
    all_rows = [(list(r) + [''] * ncols)[:ncols] for r in all_rows]
    total = len(all_rows)
    print(f'writing total_rows={total} (dates={len(sorted_dates)} footer={len(footer)})')

    # clear old range beyond new total if shrunk (shouldn't shrink here)
    # write A1:Z{total}
    last_col = 'Z' if ncols <= 26 else 'AA'
    rng = f'A1:{last_col}{total}'
    ws.update(values=all_rows, range_name=rng, value_input_option='RAW')
    print(f'WROTE {rng}')

    # verify top
    vals2 = ws.get_all_values()
    print('TOP 8:')
    for r in vals2[:8]:
        print(' ', r[:5])
    print('TAIL 3:')
    for r in vals2[-3:]:
        print(' ', r[:5])


if __name__ == '__main__':
    main()
